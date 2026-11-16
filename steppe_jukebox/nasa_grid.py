"""A class-colored view of verified pixels; the original NASA tiles stay intact."""
from __future__ import annotations

import math

import numpy as np

from .gibs import LAYERS, Palette, match_colors, png_bytes
from .sound import MISSING_COLOR, SCALE


UNKNOWN_COLOR = "#b56386"
GRID_X_PIXELS = 52
GRID_Y_PIXELS = 32


def _native(point):
    scale = LAYERS["ndvi"].world_pixels / 360
    lon, lat = point
    return (lon + 180) * scale, (90 - lat) * scale


def _cell_key(row, col):
    return f"{row}/{col}"


def _segment_entry(start, end, left, top, right, bottom):
    """Liang–Barsky clipping, including contact with an edge or corner."""
    x, y = start
    dx, dy = end[0] - x, end[1] - y
    entry, exit = 0.0, 1.0
    for p, q in ((-dx, x - left), (dx, right - x), (-dy, y - top), (dy, bottom - y)):
        if p == 0:
            if q < 0:
                return None
        elif p < 0:
            entry = max(entry, q / p)
        else:
            exit = min(exit, q / p)
        if entry > exit:
            return None
    return entry


def _crossed_cells(start, end):
    # Include both neighboring cells when the segment touches a grid edge.
    c0 = math.floor(math.nextafter(min(start[0], end[0]) / GRID_X_PIXELS, -math.inf))
    c1 = math.floor(max(start[0], end[0]) / GRID_X_PIXELS)
    r0 = math.floor(math.nextafter(min(start[1], end[1]) / GRID_Y_PIXELS, -math.inf))
    r1 = math.floor(max(start[1], end[1]) / GRID_Y_PIXELS)
    crossed = []
    for row in range(r0, r1 + 1):
        for col in range(c0, c1 + 1):
            entry = _segment_entry(start, end, col * GRID_X_PIXELS, row * GRID_Y_PIXELS,
                                   (col + 1) * GRID_X_PIXELS, (row + 1) * GRID_Y_PIXELS)
            if entry is not None:
                crossed.append((entry, row, col))
    return [(row, col) for _, row, col in sorted(crossed)]


def display_grid(region, route):
    """Whole interior display cells and a deduplicated trail over exact route points.

    Boundary segments reject a whole cell, including concavities and holes
    smaller than a raster pixel. The native mask identifies interior candidates.
    This changes presentation only; route coordinates and source samples stay put.
    """
    geometry = region.geometry
    polygons = [geometry["coordinates"]] if geometry["type"] == "Polygon" else geometry["coordinates"]
    boundary = set()
    for polygon in polygons:
        for ring in polygon:
            vertices = [_native(point) for point in ring]
            if vertices[0] != vertices[-1]:
                vertices.append(vertices[0])
            for start, end in zip(vertices, vertices[1:]):
                boundary.update(_crossed_cells(start, end))
    oy, ox = (value * 512 for value in region.origin)
    height, width = region.mask.shape
    scale = 360 / LAYERS["ndvi"].world_pixels
    cells = {}
    for row in range(math.ceil(oy / GRID_Y_PIXELS), (oy + height) // GRID_Y_PIXELS):
        for col in range(math.ceil(ox / GRID_X_PIXELS), (ox + width) // GRID_X_PIXELS):
            if (row, col) in boundary:
                continue
            x, y = col * GRID_X_PIXELS, row * GRID_Y_PIXELS
            if not region.mask[y - oy:y - oy + GRID_Y_PIXELS, x - ox:x - ox + GRID_X_PIXELS].all():
                continue
            key = _cell_key(row, col)
            cells[key] = {"key": key, "row": row, "col": col,
                          "bounds": [-180 + x * scale, 90 - (y + GRID_Y_PIXELS) * scale,
                                     -180 + (x + GRID_X_PIXELS) * scale, 90 - y * scale]}
    point_keys, trail = [], {}
    for index, point in enumerate(route):
        current = _native((point.lon, point.lat))
        key = _cell_key(math.floor(current[1] / GRID_Y_PIXELS), math.floor(current[0] / GRID_X_PIXELS))
        point_keys.append(key if key in cells else None)
        if key in cells and key not in trail:
            trail[key] = {"key": key, "first_step": index}
    return {"cells": list(cells.values()), "route_cells": list(trail.values()), "point_keys": point_keys,
            "hidden_route_points": [point.cell_id for point, key in zip(route, point_keys, strict=True) if key is None]}


def rgba_color(color: str) -> tuple[int, int, int, int]:
    return (*bytes.fromhex(color.lstrip("#")), 255)


def class_image(pixels: np.ndarray, palette: Palette) -> bytes:
    """Recolor every native pixel without averaging, resampling or filling gaps."""
    image = np.empty_like(pixels)
    image[:] = rgba_color(UNKNOWN_COLOR)
    image[pixels[:, :, 3] == 0] = rgba_color(MISSING_COLOR)
    for value, note in enumerate(SCALE, 1):
        colors = {rgb for rgb in palette.entries
                  if palette.ndvi((*rgb, 255)).get("ndvi_class") == value}
        selected = match_colors(pixels, colors) & (pixels[:, :, 3] == 255)
        image[selected] = rgba_color(note.color)
    return png_bytes(image)
