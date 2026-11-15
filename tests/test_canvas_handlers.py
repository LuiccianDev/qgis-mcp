"""render_map_base64 against a stubbed qgis (no QGIS needed)."""

from unittest.mock import MagicMock

import pytest


class FakeSignal:
    def __init__(self):
        self.slots = []

    def connect(self, slot):
        self.slots.append(slot)

    def emit(self):
        for slot in list(self.slots):
            slot()


class FakeLoop:
    exec_calls = 0

    def __init__(self):
        pass

    def quit(self):
        pass

    def exec(self):
        FakeLoop.exec_calls += 1


class SyncFinishJob:
    """A render job whose `finished` fires inside start(), as for a trivial project."""

    def __init__(self, settings):
        self.finished = FakeSignal()

    def start(self):
        self.finished.emit()

    def renderedImage(self):
        return MagicMock()

    def errors(self):
        return []


@pytest.fixture
def canvas_module(plugin_handlers, monkeypatch):
    import qgis_listener.handlers.canvas as canvas

    FakeLoop.exec_calls = 0
    monkeypatch.setattr(canvas, "QEventLoop", FakeLoop)
    monkeypatch.setattr(canvas, "QTimer", MagicMock())
    monkeypatch.setattr(canvas, "QgsMapSettings", MagicMock())
    monkeypatch.setattr(canvas, "QgsVectorSimplifyMethod", MagicMock())
    monkeypatch.setattr(canvas, "QByteArray", bytearray)
    monkeypatch.setattr(canvas, "QBuffer", MagicMock())
    return canvas


def test_render_does_not_wait_when_finished_fires_inside_start(
    canvas_module, plugin_handlers, monkeypatch
):
    monkeypatch.setattr(canvas_module, "QgsMapRendererParallelJob", SyncFinishJob)

    class Server(canvas_module.CanvasHandlers, plugin_handlers.base.HandlerBase):
        iface = MagicMock()

    result = Server().render_map_base64(width=10, height=10)

    assert result["mime_type"] == "image/png"
    assert FakeLoop.exec_calls == 0, "waiting on an already-finished job blocks until the timeout"


def test_canvas_handlers_raise_command_error_when_iface_is_none(canvas_module, plugin_handlers):
    class Server(canvas_module.CanvasHandlers, plugin_handlers.base.HandlerBase):
        iface = None

    with pytest.raises(plugin_handlers.base.CommandError, match="Map canvas is not available"):
        Server().get_canvas_extent()


def test_transform_coordinates_rejects_malformed_point(canvas_module, plugin_handlers, monkeypatch):
    monkeypatch.setattr(canvas_module, "QgsProject", MagicMock())

    class Server(canvas_module.CanvasHandlers, plugin_handlers.base.HandlerBase):
        pass

    with pytest.raises(plugin_handlers.base.CommandError, match="Invalid point"):
        Server().transform_coordinates("EPSG:4326", "EPSG:3857", point={"x": 0.0})


def test_finish_job_marks_cancelled_without_recording_when_server_stopped(plugin_handlers):
    import qgis_listener.server as server_mod

    srv = server_mod.QgisMCPServer()
    srv.running = True
    srv._record = MagicMock()
    job = {
        "id": "job1",
        "algorithm": "native:buffer",
        "state": "running",
        "started": 0.0,
        "parameters": {},
        "load_results": False,
        "ellipsoid": None,
        "existing": {},
        "task": MagicMock(),
        "feedback": MagicMock(),
    }
    srv._jobs["job1"] = job

    srv.stop()
    srv._finish_job(job, True, {"OUTPUT": "out"})

    assert job["state"] == "cancelled"
    assert job["error"] == "Server stopped"
    srv._record.assert_not_called()


def test_server_stop_cancels_only_running_background_jobs(plugin_handlers):
    import qgis_listener.server as server_mod

    srv = server_mod.QgisMCPServer()
    running_task = MagicMock()
    finished_task = MagicMock()
    srv._jobs = {
        "job1": {"state": "running", "task": running_task},
        "job2": {"state": "succeeded", "task": finished_task},
    }

    srv.stop()

    assert srv.running is False
    running_task.cancel.assert_called_once_with()
    finished_task.cancel.assert_not_called()


def test_export_3d_layout_png_deletes_layout_on_early_error(plugin_handlers, monkeypatch):
    import sys
    import types

    canvas_mod = plugin_handlers.canvas
    fake_layout = MagicMock()
    monkeypatch.setattr(canvas_mod, "QgsPrintLayout", lambda _proj: fake_layout)
    monkeypatch.setattr(canvas_mod, "QgsProject", MagicMock())
    monkeypatch.setattr(canvas_mod, "QgsLayoutSize", MagicMock())

    fake_3d = types.ModuleType("qgis._3d")

    def _boom(_layout):
        raise RuntimeError("3d init failed")

    fake_3d.QgsLayoutItem3DMap = _boom
    monkeypatch.setitem(sys.modules, "qgis._3d", fake_3d)

    with pytest.raises(RuntimeError, match="3d init failed"):
        canvas_mod.CanvasHandlers._export_3d_layout_png(MagicMock(), MagicMock(), 100, 100, 96)

    fake_layout.deleteLater.assert_called_once()


def test_create_layout_deletes_layout_when_add_fails(plugin_handlers, monkeypatch):
    layout_mod = plugin_handlers.layout
    base_mod = plugin_handlers.base

    fake_layout = MagicMock()
    fake_project = MagicMock()
    fake_project.layoutManager.return_value.addLayout.return_value = False
    monkeypatch.setattr(layout_mod, "QgsPrintLayout", lambda _proj: fake_layout)
    monkeypatch.setattr(layout_mod, "QgsProject", MagicMock(instance=lambda: fake_project))
    monkeypatch.setattr(layout_mod, "QgsLayoutItemPage", MagicMock())

    class Server(layout_mod.LayoutHandlers, base_mod.HandlerBase):
        pass

    with pytest.raises(base_mod.CommandError, match="Could not add layout"):
        Server().create_layout("Dup")

    fake_layout.deleteLater.assert_called_once()


def test_add_layout_scalebar_applies_width_and_height(plugin_handlers, monkeypatch):
    import sys

    layout_mod = plugin_handlers.layout
    base_mod = plugin_handlers.base

    fake_bar = MagicMock()
    monkeypatch.setattr(
        sys.modules["qgis.core"], "QgsLayoutItemScaleBar", lambda _layout: fake_bar, raising=False
    )
    monkeypatch.setattr(layout_mod, "QgsLayoutPoint", lambda x, y: (x, y))
    monkeypatch.setattr(layout_mod, "QgsLayoutSize", lambda w, h: ("size", w, h))

    class Server(layout_mod.LayoutHandlers, base_mod.HandlerBase):
        def _get_layout(self, _name):
            return MagicMock()

        def _find_layout_map(self, _layout, _id):
            return None

    Server().add_layout_scalebar("Map1", x=10, y=20, width=95, height=25)
    fake_bar.attemptResize.assert_called_once_with(("size", 95, 25))
