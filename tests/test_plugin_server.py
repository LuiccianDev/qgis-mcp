"""QgisMCPServer's read loop against a stubbed qgis, driven over a socketpair.

Covers the paths that never reach a handler: the auth lockout, batch shape checks,
and a handler result json cannot encode. Each used to drop the connection or leak
a traceback instead of answering.
"""

import json
import socket

import pytest

from conftest import FakeQVariant
from qgis_mcp.protocol import HEADER_STRUCT


@pytest.fixture
def server_module(plugin_handlers):
    import qgis_listener.server as mod

    return mod


@pytest.fixture
def server(server_module):
    srv = server_module.QgisMCPServer()
    srv.running = True
    return srv


@pytest.fixture
def peer(server):
    """The client end of a connected pair; the server end is registered as a client."""
    ours, theirs = socket.socketpair()
    ours.setblocking(False)
    theirs.settimeout(1)
    server.clients[ours] = bytearray()
    yield theirs
    ours.close()
    theirs.close()


def _frame(obj):
    data = json.dumps(obj).encode("utf-8")
    return HEADER_STRUCT.pack(len(data)) + data


def _read_frame(sock):
    (length,) = HEADER_STRUCT.unpack(sock.recv(4))
    return json.loads(sock.recv(length))


def test_repeated_bad_tokens_disconnect_the_client(server, server_module, peer, monkeypatch):
    monkeypatch.setenv("QGIS_MCP_TOKEN", "right")
    peer.sendall(_frame({"type": "ping", "token": "wrong"}) * server.MAX_AUTH_FAILURES)

    server.process_server()

    assert server.clients == {} and server._auth_failures == {}
    for _ in range(server.MAX_AUTH_FAILURES - 1):
        assert _read_frame(peer)["message"] == server_module.AUTH_FAILED_MESSAGE
    assert peer.recv(4) == b"", "the server closed its end"


def test_accepted_command_resets_the_failure_count(server, peer, monkeypatch):
    monkeypatch.setenv("QGIS_MCP_TOKEN", "right")
    bad = _frame({"type": "ping", "token": "wrong"})
    good = _frame({"type": "ping", "token": "right"})
    peer.sendall(bad * (server.MAX_AUTH_FAILURES - 1) + good + bad)

    server.process_server()

    assert len(server.clients) == 1
    assert list(server._auth_failures.values()) == [1]


def test_batch_rejects_malformed_shapes(server, server_module):
    with pytest.raises(server_module.CommandError):
        server.batch("ping")

    results = server.batch([42, {"type": "batch", "params": {"commands": []}}])

    assert [r["status"] for r in results] == ["error", "error"]
    assert "object" in results[0]["message"]
    assert "'batch'" in results[1]["message"]


def test_unserializable_result_is_answered_not_dropped(server, peer):
    (ours,) = server.clients

    server._send_response(ours, {"status": "success", "result": {1, 2}})

    reply = _read_frame(peer)
    assert reply["status"] == "error" and reply["internal"] is True
    assert "serializable" in reply["message"]
    assert ours in server.clients


def test_misspelled_parameter_is_rejected_not_silently_ignored(server):
    """Nearly every handler ends in **kwargs, which swallows a typo otherwise."""
    response = server._dispatch({"type": "get_layers", "params": {"limits": 5}})

    assert response["status"] == "error"
    assert "limits" in response["message"]
    assert "limit, offset" in response["message"], "the accepted names are the hint"
    assert "internal" not in response, "a caller mistake, not a plugin defect"


def test_known_parameters_still_reach_the_handler(server):
    assert server._dispatch({"type": "ping", "params": {}}) == {
        "status": "success",
        "result": {"pong": True},
    }
    assert server._dispatch({"type": "ping"})["status"] == "success"


def test_frames_split_across_recv_chunks_are_reassembled(server, peer):
    """One request arriving in pieces must be answered once, not dropped."""
    (ours,) = server.clients
    payload = _frame({"type": "ping"})
    peer.sendall(payload[:3])

    server.process_server()
    assert bytes(server.clients[ours]) == payload[:3], "held until the frame completes"

    peer.sendall(payload[3:] + _frame({"type": "ping"}))
    server.process_server()

    assert _read_frame(peer)["result"] == {"pong": True}
    assert _read_frame(peer)["result"] == {"pong": True}
    assert bytes(server.clients[ours]) == b"", "consumed bytes are dropped"


def test_convert_attribute_turns_qt_dates_into_iso_strings(server):
    import datetime

    class FakeQDate:
        def toPyDate(self):
            return datetime.date(2020, 1, 2)

    class FakeQDateTime:
        def toPyDateTime(self):
            return datetime.datetime(2021, 3, 4, 5, 6, 7)

    class NullVariant(FakeQVariant):
        def isNull(self):
            return True

    assert server._convert_attribute(NullVariant()) is None
    assert server._convert_attribute(FakeQDate()) == "2020-01-02"
    assert server._convert_attribute(FakeQDateTime()) == "2021-03-04T05:06:07"
    assert server._convert_attribute(datetime.date(2020, 1, 2)) == "2020-01-02"
    assert server._convert_attribute(3.5) == 3.5


def test_set_layer_style_validates_and_applies_opacity(server, monkeypatch):
    from unittest.mock import MagicMock

    from qgis_listener.errors import CommandError

    layer = MagicMock()
    layer.id.return_value = "L1"
    monkeypatch.setattr(server, "iface", MagicMock())
    monkeypatch.setattr(server, "_get_vector_layer", lambda lid: layer)
    monkeypatch.setattr(server, "_style_single", lambda *a: MagicMock())

    for bad in (-0.1, 1.5):
        with pytest.raises(CommandError, match="opacity"):
            server.set_layer_style(layer_id="L1", style_type="single", opacity=bad)

    res = server.set_layer_style(layer_id="L1", style_type="single", opacity=0.6)
    assert res == {"ok": True}
    layer.setOpacity.assert_called_once_with(0.6)


def test_create_layout_validates_page_size_and_orientation(server, monkeypatch):
    from unittest.mock import MagicMock

    import qgis_listener.handlers.layout as layout_mod
    from qgis_listener.errors import CommandError

    project = MagicMock()
    monkeypatch.setattr(layout_mod, "QgsProject", MagicMock(**{"instance.return_value": project}))
    monkeypatch.setattr(
        layout_mod, "QgsLayoutItemPage", MagicMock(Portrait=0, Landscape=1), raising=False
    )

    with pytest.raises(CommandError, match="orientation"):
        server.create_layout(name="L", orientation="diagonal")
    project.layoutManager().addLayout.assert_not_called()

    layout_instance = MagicMock()
    page = MagicMock()
    page.setPageSize.return_value = False
    layout_instance.pageCollection.return_value.page.return_value = page
    monkeypatch.setattr(layout_mod, "QgsPrintLayout", lambda p: layout_instance)

    with pytest.raises(CommandError, match="page_size"):
        server.create_layout(name="L", page_size="B99")
    project.layoutManager().addLayout.assert_not_called()


def test_add_layout_legend_filters_layers_and_rejects_unknown(server, monkeypatch):
    from unittest.mock import MagicMock

    import qgis_listener.handlers.layout as layout_mod
    from qgis_listener.errors import CommandError

    layout = MagicMock()
    legend = MagicMock()
    monkeypatch.setattr(server, "_get_layout", lambda name: layout)
    monkeypatch.setattr(server, "_find_layout_map", lambda _l, mid=None: None)
    monkeypatch.setattr(layout_mod, "QgsLayoutItemLegend", lambda _l: legend, raising=False)

    def fake_layer(lid):
        if lid == "L1":
            return "layer_obj_1"
        raise CommandError(f"Layer not found: {lid}")

    monkeypatch.setattr(server, "_layer", fake_layer)

    with pytest.raises(CommandError, match="Layer not found"):
        server.add_layout_legend(layout_name="L", layer_ids=["nonexistent"])

    res = server.add_layout_legend(layout_name="L", layer_ids=["L1"])
    assert res["ok"] is True
    legend.setAutoUpdateModel.assert_called_once_with(False)
    legend.model().rootGroup().removeAllChildren.assert_called_once_with()
    legend.model().rootGroup().addLayer.assert_called_once_with("layer_obj_1")


def test_add_layout_map_validates_extent_and_scale(server, monkeypatch):
    from unittest.mock import MagicMock

    import qgis_listener.handlers.layout as layout_mod
    from qgis_listener.errors import CommandError

    layout = MagicMock()
    map_item = MagicMock()
    monkeypatch.setattr(server, "_get_layout", lambda name: layout)
    monkeypatch.setattr(layout_mod, "QgsLayoutItemMap", lambda _l: map_item)
    monkeypatch.setattr(layout_mod, "QgsRectangle", lambda *a: ("rect", a), raising=False)

    for bad_extent in ([0, 0, 1], [10, 0, 5, 10], [0, 10, 5, 5]):
        with pytest.raises(CommandError, match="extent"):
            server.add_layout_map(
                layout_name="L", x=0, y=0, width=100, height=100, extent=bad_extent
            )

    for bad_scale in (0, -500):
        with pytest.raises(CommandError, match="scale"):
            server.add_layout_map(layout_name="L", x=0, y=0, width=100, height=100, scale=bad_scale)

    layout.addLayoutItem.assert_not_called()

    res = server.add_layout_map(
        layout_name="L",
        x=0,
        y=0,
        width=100,
        height=100,
        extent=[1.0, 2.0, 3.0, 4.0],
        scale=5000.0,
    )
    assert res == {"ok": True}
    map_item.zoomToExtent.assert_called_once_with(("rect", (1.0, 2.0, 3.0, 4.0)))
    map_item.setScale.assert_called_once_with(5000.0)


def test_non_loopback_server_rejects_commands_once_the_token_is_revoked(
    server, server_module, monkeypatch
):
    # start() demanded a token to bind 0.0.0.0; revoking it afterwards must not
    # silently turn the network endpoint into an unauthenticated execute_code.
    server.host = "0.0.0.0"
    monkeypatch.setattr(server_module, "read_token", lambda: None)

    response = server.execute_command({"type": "ping"})

    assert response["status"] == "error"
    assert "token" in response["message"].lower()


def test_loopback_server_still_accepts_commands_without_a_token(server, server_module, monkeypatch):
    server.host = "localhost"
    monkeypatch.setattr(server_module, "read_token", lambda: None)

    assert server.execute_command({"type": "ping"})["status"] == "success"


def test_address_family_follows_the_host(server_module):
    assert server_module.address_family("::1") == socket.AF_INET6
    assert server_module.address_family("localhost") == socket.AF_INET
    assert server_module.address_family("127.0.0.1") == socket.AF_INET


def test_a_large_frame_is_read_in_one_tick(server, peer, monkeypatch):
    # One 64 KB recv per 25 ms tick made a multi-MB request take seconds.
    monkeypatch.setattr(server, "_in_dispatch", False)
    # 150 KB (> 2 * 64 KB RECV_CHUNK_SIZE) fits Linux socketpair buffers while
    # still proving multiple chunks are drained in a single tick.
    peer.sendall(_frame({"type": "ping", "padding": "x" * 150_000}))
    import time

    time.sleep(0.01)

    server.process_server()

    assert "status" in _read_frame(peer)
