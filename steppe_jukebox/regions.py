"""Load region data and geographic boundaries independently of the player UI."""

import json
import math
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from .data import DataError, Dataset, load_dataset


@dataclass(frozen=True)
class Region:
    key: str
    dataset: Dataset
    boundary: dict
    source_url: str


def load_boundary(path: Path) -> dict:
    """Use geographic lon/lat rings, including holes; never SVG coordinates."""
    try:
        geometry = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise DataError(f"Cannot read {path}", "read_file", file=path.name) from exc
    try:
        if isinstance(geometry, dict) and geometry.get("type") == "FeatureCollection":
            features = geometry.get("features")
            if not isinstance(features, list) or len(features) != 1:
                raise ValueError("Expected exactly one region feature")
            geometry = features[0]
        if isinstance(geometry, dict) and geometry.get("type") == "Feature":
            geometry = geometry.get("geometry")
        if geometry["type"] not in {"Polygon", "MultiPolygon"}:
            raise ValueError("Expected geographic polygon")
        polygons = [geometry["coordinates"]] if geometry["type"] == "Polygon" else geometry["coordinates"]
        if not polygons or not isinstance(polygons, list):
            raise ValueError("Empty polygon")
        for polygon in polygons:
            if not polygon:
                raise ValueError("Empty rings")
            for ring in polygon:
                if len(ring) < 4 or ring[0] != ring[-1]:
                    raise ValueError("Unclosed ring")
                for point in ring:
                    if len(point) != 2:
                        raise ValueError("Expected longitude and latitude")
                    lon, lat = point
                    if any(type(value) not in {int, float} or not math.isfinite(value) for value in point) or not (-180 <= lon <= 180 and -90 <= lat <= 90):
                        raise ValueError("Invalid coordinates")
    except (KeyError, TypeError, ValueError) as exc:
        raise DataError(f"Invalid geographic boundary: {path}", "boundary", file=path.name) from exc
    return geometry


def load_regions(path: Path) -> tuple[Region, ...]:
    """Region CSV contracts are identical to a standalone STEPPE_DATA_DIR."""
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise DataError(f"Cannot read {path}", "read_file", file=path.name) from exc
    regions, seen = [], set()
    try:
        if not isinstance(manifest, list) or not manifest:
            raise ValueError("Expected a nonempty region list")
        for item in manifest:
            key = item["key"]
            if key not in {"kostanay", "akmola", "north-kazakhstan", "pavlodar", "west-kazakhstan", "aktobe", "karaganda", "abai"} or key in seen:
                raise ValueError("Unknown or duplicate region")
            seen.add(key)
            url = urlsplit(item["map_source_url"])
            if url.scheme not in {"http", "https"} or not url.netloc:
                raise ValueError("Expected a source URL")
            regions.append(Region(key, load_dataset(path.parent / item["dataset"]),
                                  load_boundary(path.parent / item["boundary"]), item["map_source_url"]))
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, DataError):
            raise
        raise DataError(f"Invalid region manifest: {path}", "region_catalog", file=path.name) from exc
    return tuple(regions)
