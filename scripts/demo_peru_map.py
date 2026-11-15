#!/usr/bin/env python3
"""End-to-end Peru thematic map demo exercising QGIS MCP commands.

Connects to a running QGIS listener on localhost:9878 (or QGIS_MCP_HOST/PORT),
builds a multi-layer thematic map of Peru (natural regions, road corridors,
major cities, and 50 km influence buffers), styles and labels the layers,
composes an A4 print layout, and saves all outputs to ~/Documents/QGIS_MCP_Peru_Map/.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from qgis_mcp.client import QgisMCPClient

OUTPUT_DIR = Path.home() / "Documents" / "QGIS_MCP_Peru_Map"

PERU_REGIONS = [
    {
        "geometry_wkt": (
            "POLYGON((-81.3 -3.5, -80.2 -3.5, -78.8 -6.0, -77.5 -9.5, "
            "-76.5 -12.2, -74.8 -14.8, -71.8 -16.8, -70.3 -18.3, "
            "-71.2 -17.9, -73.8 -16.2, -76.3 -13.9, -77.2 -12.0, "
            "-79.1 -8.1, -81.1 -5.2, -81.3 -3.5))"
        ),
        "attributes": {
            "nombre": "Costa Peruana",
            "macroregion": "Costa",
            "area_aprox_km2": 136232,
        },
    },
    {
        "geometry_wkt": (
            "POLYGON((-80.2 -3.5, -78.5 -4.5, -76.8 -7.0, -75.0 -10.5, "
            "-72.5 -12.5, -69.5 -14.5, -68.9 -17.5, -70.3 -18.3, "
            "-71.8 -16.8, -74.8 -14.8, -76.5 -12.2, -77.5 -9.5, "
            "-78.8 -6.0, -80.2 -3.5))"
        ),
        "attributes": {
            "nombre": "Sierra Andina",
            "macroregion": "Sierra",
            "area_aprox_km2": 391991,
        },
    },
    {
        "geometry_wkt": (
            "POLYGON((-78.5 -4.5, -75.5 -1.5, -72.5 -0.2, -69.9 -4.2, "
            "-70.5 -8.5, -68.7 -12.5, -69.5 -14.5, -72.5 -12.5, "
            "-75.0 -10.5, -76.8 -7.0, -78.5 -4.5))"
        ),
        "attributes": {
            "nombre": "Selva Amazónica",
            "macroregion": "Selva",
            "area_aprox_km2": 756993,
        },
    },
]

PERU_CORRIDORS = [
    {
        "geometry_wkt": (
            "LINESTRING(-80.45 -3.56, -80.63 -5.19, -79.03 -8.11, "
            "-77.04 -12.05, -75.73 -14.07, -71.54 -16.41, -70.25 -18.01)"
        ),
        "attributes": {"nombre": "Corredor Panamericana", "tipo": "Longitudinal Costa"},
    },
    {
        "geometry_wkt": (
            "LINESTRING(-77.04 -12.05, -75.90 -11.52, -75.20 -12.07, -76.24 -9.93, -74.53 -8.38)"
        ),
        "attributes": {"nombre": "Carretera Central - Ucayali", "tipo": "Transversal Centro"},
    },
    {
        "geometry_wkt": (
            "LINESTRING(-74.94 -14.83, -72.88 -13.63, -71.97 -13.53, -69.19 -12.59, -69.57 -10.95)"
        ),
        "attributes": {"nombre": "Interoceánica Sur", "tipo": "Transversal Sur"},
    },
]

PERU_CITIES = [
    ("Lima", "Lima", 10092000, "Metrópoli", -77.0428, -12.0464),
    ("Arequipa", "Arequipa", 1177000, "Gran Ciudad", -71.5375, -16.4090),
    ("Trujillo", "La Libertad", 1020000, "Gran Ciudad", -79.0288, -8.1116),
    ("Piura", "Piura", 560000, "Ciudad Regional", -80.6328, -5.1945),
    ("Cusco", "Cusco", 470000, "Ciudad Regional", -71.9675, -13.5319),
    ("Iquitos", "Loreto", 470000, "Ciudad Amazónica", -73.2516, -3.7437),
    ("Huancayo", "Junín", 456000, "Ciudad Andina", -75.2049, -12.0651),
    ("Tacna", "Tacna", 325000, "Ciudad Fronteriza", -70.2536, -18.0146),
    ("Tarapoto", "San Martín", 180000, "Ciudad Amazónica", -76.3649, -6.4825),
    ("Puno", "Puno", 145000, "Ciudad Altiplánica", -70.0219, -15.8402),
    ("Huaraz", "Áncash", 130000, "Ciudad Andina", -77.5278, -9.5278),
    ("Puerto Maldonado", "Madre de Dios", 95000, "Ciudad Amazónica", -69.1891, -12.5933),
]


def call(client: QgisMCPClient, command: str, params: dict[str, Any] | None = None) -> Any:
    """Send a command to QGIS MCP and raise a clear error on failure."""
    resp = client.send_command(command, params or {})
    if resp.get("status") != "success":
        raise RuntimeError(f"Command '{command}' failed: {resp}")
    return resp.get("result")


def build_peru_map(client: QgisMCPClient, out_dir: Path) -> dict[str, Path]:
    """Run the full Peru map creation workflow and return generated file paths."""
    out_dir.mkdir(parents=True, exist_ok=True)
    project_path = out_dir / "peru_mapa.qgz"
    reproj_path = out_dir / "ciudades_utm18s.gpkg"
    buffer_path = out_dir / "areas_influencia_50km.gpkg"
    canvas_path = out_dir / "peru_canvas.png"
    pdf_path = out_dir / "peru_mapa.pdf"
    png_path = out_dir / "peru_mapa.png"
    session_path = out_dir / "peru_session.py"

    # 1. System & Project setup
    pong = call(client, "ping")
    if pong.get("pong") is not True:
        raise RuntimeError(f"Unexpected ping response: {pong}")
    qgis_info = call(client, "get_qgis_info")
    print(f"Connected to QGIS {qgis_info.get('qgis_version')} (pid={qgis_info.get('pid')})")

    call(client, "create_new_project", {"path": str(project_path)})
    call(client, "set_project_crs", {"crs": "EPSG:4326"})
    call(client, "set_project_variable", {"key": "pais", "value": "Perú"})
    call(client, "set_project_variable", {"key": "generado_por", "value": "qgis-mcp"})

    # 2. Layer tree groups & memory layers
    for group in ("Límites y Regiones", "Red Vial y Corredores", "Ciudades y Análisis"):
        call(client, "create_layer_group", {"name": group})

    regions_id = call(
        client,
        "create_memory_layer",
        {
            "name": "regiones_peru",
            "geometry_type": "Polygon",
            "crs": "EPSG:4326",
            "fields": [
                {"name": "nombre", "type": "string"},
                {"name": "macroregion", "type": "string"},
                {"name": "area_aprox_km2", "type": "integer"},
            ],
        },
    )["id"]
    call(
        client, "move_layer_to_group", {"layer_id": regions_id, "group_name": "Límites y Regiones"}
    )

    corridors_id = call(
        client,
        "create_memory_layer",
        {
            "name": "corredores_peru",
            "geometry_type": "LineString",
            "crs": "EPSG:4326",
            "fields": [
                {"name": "nombre", "type": "string"},
                {"name": "tipo", "type": "string"},
            ],
        },
    )["id"]
    call(
        client,
        "move_layer_to_group",
        {"layer_id": corridors_id, "group_name": "Red Vial y Corredores"},
    )

    cities_id = call(
        client,
        "create_memory_layer",
        {
            "name": "ciudades_peru",
            "geometry_type": "Point",
            "crs": "EPSG:4326",
            "fields": [
                {"name": "nombre", "type": "string"},
                {"name": "departamento", "type": "string"},
                {"name": "poblacion", "type": "integer"},
                {"name": "categoria", "type": "string"},
            ],
        },
    )["id"]
    call(
        client, "move_layer_to_group", {"layer_id": cities_id, "group_name": "Ciudades y Análisis"}
    )

    # 3. Edit sessions, feature CRUD, field calculator, stats & selection
    city_features = [
        {
            "geometry_wkt": f"POINT({lon} {lat})",
            "attributes": {
                "nombre": name,
                "departamento": dept,
                "poblacion": pop,
                "categoria": cat,
            },
        }
        for name, dept, pop, cat, lon, lat in PERU_CITIES
    ]
    for lid, feats in (
        (regions_id, PERU_REGIONS),
        (corridors_id, PERU_CORRIDORS),
        (cities_id, city_features),
    ):
        call(client, "start_editing", {"layer_id": lid})
        status = call(client, "get_edit_status", {"layer_id": lid})
        if status.get("editable") is not True:
            raise RuntimeError(f"Layer '{lid}' did not enter edit mode: {status}")
        call(client, "add_features", {"layer_id": lid, "features": feats})
        call(client, "commit_edits", {"layer_id": lid})

    call(
        client,
        "field_calculator",
        {
            "layer_id": cities_id,
            "field_name": "pob_millones",
            "expression": 'round("poblacion" / 1000000.0, 2)',
            "field_type": "double",
        },
    )
    stats = call(client, "get_field_statistics", {"layer_id": cities_id, "field_name": "poblacion"})
    print(
        f"Cities population stats: min={stats.get('min')}, max={stats.get('max')}, sum={stats.get('sum')}"
    )

    call(client, "select_features", {"layer_id": cities_id, "expression": '"poblacion" > 500000'})
    selected = call(client, "get_selection", {"layer_id": cities_id})
    print(f"Selected major cities (>500k): {selected.get('count')}")
    call(client, "clear_selection", {"layer_id": cities_id})

    # 4. Geoprocessing: reproject cities to UTM 18S & compute 50 km buffers
    call(
        client,
        "execute_processing",
        {
            "algorithm": "native:reprojectlayer",
            "parameters": {
                "INPUT": cities_id,
                "TARGET_CRS": "EPSG:32718",
                "OUTPUT": str(reproj_path),
            },
            "load_results": False,
        },
    )
    buf_res = call(
        client,
        "execute_processing",
        {
            "algorithm": "native:buffer",
            "parameters": {
                "INPUT": str(reproj_path),
                "DISTANCE": 50000,
                "SEGMENTS": 16,
                "DISSOLVE": False,
                "OUTPUT": str(buffer_path),
            },
            "load_results": True,
        },
    )
    loaded_buffers = buf_res.get("loaded_layers") or []
    if loaded_buffers:
        buf_id = loaded_buffers[0]["id"]
        call(
            client, "move_layer_to_group", {"layer_id": buf_id, "group_name": "Ciudades y Análisis"}
        )
        call(
            client,
            "set_layer_style",
            {
                "layer_id": buf_id,
                "style_type": "single",
                "opacity": 0.25,
            },
        )

    # 5. Symbology, labeling, bookmarks & map themes
    call(
        client,
        "set_layer_style",
        {
            "layer_id": regions_id,
            "style_type": "categorized",
            "field": "macroregion",
            "color_ramp": "Viridis",
            "opacity": 0.45,
        },
    )
    call(
        client,
        "set_layer_style",
        {
            "layer_id": corridors_id,
            "style_type": "single",
            "opacity": 0.9,
        },
    )
    call(
        client,
        "set_layer_style",
        {
            "layer_id": cities_id,
            "style_type": "graduated",
            "field": "poblacion",
            "classes": 4,
            "color_ramp": "YlOrRd",
            "opacity": 1.0,
        },
    )
    call(
        client,
        "set_layer_labeling",
        {
            "layer_id": cities_id,
            "enabled": True,
            "field_name": "nombre",
            "font_size": 9,
            "color": "#1a1a1a",
        },
    )

    call(
        client,
        "add_bookmark",
        {
            "name": "Perú Completo",
            "xmin": -82.0,
            "ymin": -18.8,
            "xmax": -68.0,
            "ymax": 0.2,
            "crs": "EPSG:4326",
            "group": "Perú",
        },
    )
    call(
        client,
        "add_bookmark",
        {
            "name": "Lima Metropolitana",
            "xmin": -77.6,
            "ymin": -12.5,
            "xmax": -76.5,
            "ymax": -11.6,
            "crs": "EPSG:4326",
            "group": "Perú",
        },
    )
    call(client, "add_map_theme", {"name": "Vista Completa Perú"})

    # 6. Canvas render, Print Layout & Exports
    call(client, "zoom_to_layer", {"layer_id": regions_id})
    call(client, "render_map_base64", {"width": 1200, "height": 1400, "path": str(canvas_path)})

    layout_name = "Mapa_Peru_A4"
    call(
        client,
        "create_layout",
        {"name": layout_name, "page_size": "A4", "orientation": "landscape"},
    )
    map_item = call(
        client,
        "add_layout_map",
        {
            "layout_name": layout_name,
            "x": 8,
            "y": 20,
            "width": 135,
            "height": 165,
            "extent": [-82.0, -18.8, -68.0, 0.2],
        },
    )
    map_item_id = map_item.get("item_id")

    call(
        client,
        "add_layout_label",
        {
            "layout_name": layout_name,
            "text": "MAPA TEMÁTICO DEL PERÚ — Regiones, Corredores Viales y Ciudades",
            "x": 8,
            "y": 6,
            "width": 281,
            "height": 12,
            "font_size": 16,
        },
    )
    call(
        client,
        "add_layout_legend",
        {
            "layout_name": layout_name,
            "map_item_id": map_item_id,
            "x": 146,
            "y": 20,
            "width": 58,
            "height": 165,
            "title": "Leyenda",
        },
    )
    call(
        client,
        "add_layout_table",
        {
            "layout_name": layout_name,
            "layer_id": cities_id,
            "x": 206,
            "y": 20,
            "width": 84,
            "height": 165,
            "max_rows": 12,
        },
    )
    call(
        client,
        "add_layout_scalebar",
        {
            "layout_name": layout_name,
            "map_item_id": map_item_id,
            "x": 12,
            "y": 188,
            "width": 120,
            "height": 14,
            "style": "Single Box",
        },
    )

    call(
        client,
        "export_layout",
        {"layout_name": layout_name, "path": str(pdf_path), "format": "pdf", "dpi": 300},
    )
    call(
        client,
        "export_layout",
        {"layout_name": layout_name, "path": str(png_path), "format": "png", "dpi": 200},
    )

    call(client, "save_project", {"path": str(project_path)})
    call(client, "export_session", {"path": str(session_path)})

    # Summary checks
    layers = call(client, "get_layers")
    tree = call(client, "get_layer_tree")
    layout_info = call(client, "get_layout_info", {"layout_name": layout_name})
    print(
        f"Layers in project: {len(layers.get('layers', []))}, tree nodes: {len(tree.get('tree', []))}"
    )
    print(f"Layout items in '{layout_name}': {len(layout_info.get('items', []))}")

    return {
        "project": project_path,
        "pdf": pdf_path,
        "png": png_path,
        "canvas": canvas_path,
        "buffers": buffer_path,
        "session": session_path,
    }


def main() -> None:
    host = os.environ.get("QGIS_MCP_HOST", "localhost")
    port = int(os.environ.get("QGIS_MCP_PORT", "9878"))
    client = QgisMCPClient(host=host, port=port)
    if not client.connect():
        raise SystemExit(f"Could not connect to QGIS MCP at {host}:{port}: {client.last_error}")
    try:
        outputs = build_peru_map(client, OUTPUT_DIR)
    finally:
        client.disconnect()

    print("\nGenerated files:")
    for label, path in outputs.items():
        size = path.stat().st_size if path.exists() else 0
        print(f"  - {label}: {path} ({size} bytes)")


if __name__ == "__main__":
    main()
