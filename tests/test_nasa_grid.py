"""Native-pixel grid colors and refusal to turn failed route samples into rests."""
import io
from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image

from steppe_jukebox.data import Cell
from pathlib import Path

from steppe_jukebox.data import load_route
from steppe_jukebox.gibs import LAYERS, PALETTES, Palette, RegionGrid, TileClient, TileKey, TileResult, pixel_coordinate
from steppe_jukebox.nasa_grid import GRID_X_PIXELS, GRID_Y_PIXELS, UNKNOWN_COLOR, class_image, display_grid, rgba_color
from steppe_jukebox.nasa_job import MapJob
from steppe_jukebox.regions import load_boundary
from steppe_jukebox.sound import MISSING_COLOR, SCALE


def test_grid_recolors_all_five_classes_without_changing_native_pixels():
    palette = Palette(PALETTES / "ndvi.xml")
    source = np.zeros((512, 512, 4), dtype=np.uint8)
    for value in range(1, 6):
        rgb = next(rgb for rgb in palette.entries if palette.ndvi((*rgb, 255)).get("ndvi_class") == value)
        source[0, value - 1] = (*rgb, 255)
    source[0, 6] = (1, 2, 3, 255)
    source[0, 7] = (*source[0, 0, :3], 128)
    before = source.copy()
    display = np.array(Image.open(io.BytesIO(class_image(source, palette))))
    assert np.array_equal(source, before)
    for index, note in enumerate(SCALE):
        assert tuple(display[0, index]) == rgba_color(note.color)
    assert tuple(display[0, 5]) == rgba_color(MISSING_COLOR)
    assert tuple(display[0, 6]) == tuple(display[0, 7]) == rgba_color(UNKNOWN_COLOR)


@pytest.mark.parametrize("status", ["request_error", "date_mismatch", "invalid_image", "unknown_color", "partial_alpha"])
def test_unknown_or_failed_route_never_produces_audio(status, tmp_path):
    from steppe_jukebox.gibs import TileCache

    cell = Cell("sample", 53, 64)
    row, col, y, x = pixel_coordinate(cell.lat, cell.lon)
    key = TileKey("ndvi", "2026-04-15", row, col)
    job = MapJob("bad-sample", key.date, SimpleNamespace(positions=((row, col),)), (cell,),
                 client=TileClient(TileCache(tmp_path)))
    if status in {"unknown_color", "partial_alpha"}:
        result = TileResult(key, "ok")
        pixels = np.zeros((512, 512, 4), dtype=np.uint8)
        pixels[y, x] = (1, 2, 3, 255 if status == "unknown_color" else 128)
        job.arrays[("ndvi", row, col)] = pixels
    else:
        result = TileResult(key, status)
    job.results[("ndvi", row, col)] = result
    job.done = True
    snapshot = job.snapshot()
    assert snapshot["points"][0]["status"] == status
    assert snapshot["playback"] is None


def _coordinate(col, row):
    scale = 360 / LAYERS["ndvi"].world_pixels
    return [-180 + (1100 + col) * GRID_X_PIXELS * scale,
            90 - (250 + row) * GRID_Y_PIXELS * scale]


def test_display_cells_reject_boundary_cuts_concavities_and_small_holes():
    outer = [(0.2, 0.2), (7.8, 0.2), (7.8, 7.8), (5.2, 7.8),
             (5.2, 3.2), (2.8, 3.2), (2.8, 7.8), (0.2, 7.8), (0.2, 0.2)]
    hole = [(1.49, 1.49), (1.51, 1.49), (1.51, 1.51), (1.49, 1.51), (1.49, 1.49)]
    region = RegionGrid({"type": "Polygon", "coordinates": [
        [_coordinate(*point) for point in ring] for ring in [outer, hole]]})
    view = display_grid(region, ())
    keys = {cell["key"] for cell in view["cells"]}
    assert "252/1101" in keys and "251/1106" in keys
    assert "250/1101" not in keys  # An edge is cut off by the outer boundary.
    assert "254/1102" not in keys  # A concave edge crosses the cell.
    assert "254/1103" not in keys  # Inside the notch.
    assert "251/1101" not in keys  # The entire hole fits inside this one cell.
    assert all(251 <= cell["row"] <= 256 and 1101 <= cell["col"] <= 1106 for cell in view["cells"])


def test_display_trail_includes_between_point_cells_and_deduplicates_return_path():
    ring = [_coordinate(*point) for point in [(0.2, 0.2), (7.8, 0.2), (7.8, 7.8), (0.2, 7.8), (0.2, 0.2)]]
    region = RegionGrid({"type": "Polygon", "coordinates": [ring]})
    route = tuple(Cell(str(index), *reversed(_coordinate(col, row)))
                  for index, (col, row) in enumerate([(1.5, 1.5), (5.5, 1.5), (5.5, 5.5), (1.5, 1.5)]))
    before = tuple((point.cell_id, point.lat, point.lon) for point in route)
    view = display_grid(region, route)
    path = {cell["key"]: cell["first_step"] for cell in view["route_cells"]}
    assert not view["hidden_route_points"]
    assert len(path) == len(view["route_cells"])
    assert path["251/1101"] == 0 and path["251/1103"] == 1 and path["253/1105"] == 2
    assert view["point_keys"][0] == view["point_keys"][-1]
    assert tuple((point.cell_id, point.lat, point.lon) for point in route) == before


def test_display_kostanay_route_keeps_all_48_points_on_one_connected_interior_trail():
    root = Path(__file__).resolve().parents[1]
    route = load_route(root / "data/real-test/noaa20-kostanay/route.csv")
    view = display_grid(RegionGrid(load_boundary(root / "data/maps/kostanay.geojson")), route)
    cells = {cell["key"] for cell in view["cells"]}
    path = {cell["key"] for cell in view["route_cells"]}
    assert len(view["cells"]) == 674
    assert len(view["point_keys"]) == 48 and len(set(view["point_keys"])) == 32
    assert len(path) == len(view["route_cells"]) == 37
    assert not view["hidden_route_points"]
    assert set(view["point_keys"]) <= path <= cells
    pending = [next(iter(path))]
    visited = set()
    while pending:
        key = pending.pop()
        if key in visited:
            continue
        visited.add(key)
        row, col = map(int, key.split("/"))
        pending.extend(neighbor for neighbor in [f"{row-1}/{col}", f"{row+1}/{col}",
                                                 f"{row}/{col-1}", f"{row}/{col+1}"]
                       if neighbor in path and neighbor not in visited)
    assert visited == path
