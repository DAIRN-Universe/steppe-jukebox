"""NASA GIBS tiles, verified persistent cache and exact display-color decoding.

Shared by the one-date map and future route sampling. No audio dependencies.
"""
from __future__ import annotations

import hashlib
import io
import json
import math
import os
import re
import sys
import threading
import time
import uuid
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import numpy as np
from PIL import Image, ImageDraw


PALETTES = Path(__file__).parent.parent / "data" / "nasa-palettes"
TILE_SIZE = 512
THRESHOLD_K = Decimal("274.15")
CACHE_WRITE_LOCK = threading.RLock()


@dataclass(frozen=True)
class Layer:
    key: str
    identifier: str
    matrix_set: str
    matrix: int
    world_pixels: int


LAYERS = {
    "ndvi": Layer("ndvi", "VIIRS_NOAA20_NDVI_8Day", "500m", 7, 81920),
    "snow": Layer("snow", "MODIS_Terra_NDSI_Snow_Cover", "500m", 7, 81920),
    "temperature": Layer("temperature", "MODIS_Terra_L3_Land_Surface_Temp_Daily_Day", "1km", 6, 40960),
    "water": Layer("water", "MODIS_Terra_L3_Land_Water_Mask", "250m", 7, 81920),
}
WATER_DATE = "2015-01-01"  # Last available annual mask in the inspected GIBS capabilities.


def user_cache_directory() -> Path:
    if sys.platform == "win32":
        root = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    elif sys.platform == "darwin":
        root = Path.home() / "Library" / "Caches"
    else:
        candidate = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
        root = candidate if candidate.is_absolute() else Path.home() / ".cache"
    return root / "steppe-jukebox" / "nasa-gibs"


@dataclass(frozen=True)
class TileKey:
    layer: str
    date: str
    row: int
    col: int

    def __post_init__(self):
        if self.layer not in LAYERS or date.fromisoformat(self.date).isoformat() != self.date:
            raise ValueError("Invalid layer or ISO date")
        info = LAYERS[self.layer]
        if not (0 <= self.row < info.world_pixels // 1024 and 0 <= self.col < info.world_pixels // 512):
            raise ValueError("Tile outside the EPSG:4326 matrix")

    @property
    def identity(self) -> str:
        layer = LAYERS[self.layer]
        return f"{layer.identifier}/{self.date}/EPSG4326/{layer.matrix_set}/{layer.matrix}/{self.row}/{self.col}"

    @property
    def url(self) -> str:
        layer = LAYERS[self.layer]
        return f"https://gibs.earthdata.nasa.gov/wmts/epsg4326/best/{layer.identifier}/default/{self.date}/{layer.matrix_set}/{layer.matrix}/{self.row}/{self.col}.png"

    @property
    def bounds(self) -> tuple[float, float, float, float]:
        span = 360 * TILE_SIZE / LAYERS[self.layer].world_pixels
        west, north = -180 + self.col * span, 90 - self.row * span
        return west, north - span, west + span, north


@dataclass
class TileResult:
    key: TileKey
    status: str
    png: bytes | None = field(default=None, repr=False)
    metadata: dict = field(default_factory=dict)
    from_cache: bool = False
    seconds: float = 0

    def rgba(self) -> np.ndarray:
        if self.status != "ok" or self.png is None:
            raise ValueError("An unverified tile has no usable pixels")
        with Image.open(io.BytesIO(self.png)) as image:
            return np.array(image.convert("RGBA"))


def validate_png(raw: bytes) -> None:
    with Image.open(io.BytesIO(raw)) as image:
        if image.format != "PNG" or image.size != (512, 512):
            raise ValueError("Expected a 512 x 512 PNG")
        image.verify()


class TileCache:
    """Only verified PNGs are admitted; metadata manifests are replaced atomically."""

    def __init__(self, directory: Path | None = None):
        self.directory = Path(directory) if directory is not None else user_cache_directory()

    def _manifest(self, key: TileKey) -> Path:
        return self.directory / (hashlib.sha256(key.identity.encode()).hexdigest() + ".json")

    def get(self, key: TileKey) -> TileResult | None:
        path = self._manifest(key)
        try:
            metadata = json.loads(path.read_text())
            if metadata["identity"] != key.identity or metadata["actual_date"][:10] != key.date:
                return None
            digest = metadata["sha256"]
            if not re.fullmatch(r"[0-9a-f]{64}", digest):
                return None
            raw = (self.directory / (digest + ".png")).read_bytes()
            if hashlib.sha256(raw).hexdigest() != digest:
                return None
            validate_png(raw)
            return TileResult(key, "ok", raw, metadata, True)
        except (OSError, ValueError, KeyError, TypeError, SyntaxError):
            return None

    def put(self, result: TileResult) -> None:
        if result.status != "ok" or result.png is None or result.metadata.get("actual_date", "")[:10] != result.key.date:
            raise ValueError("Only verified successful tiles may enter the cache")
        validate_png(result.png)
        digest = hashlib.sha256(result.png).hexdigest()
        self.directory.mkdir(parents=True, exist_ok=True)
        metadata = {**result.metadata, "identity": result.key.identity, "sha256": digest}
        for target, raw in [(self.directory / (digest + ".png"), result.png),
                            (self._manifest(result.key), json.dumps(metadata, sort_keys=True).encode())]:
            temporary = target.with_name(target.name + "." + uuid.uuid4().hex + ".tmp")
            try:
                temporary.write_bytes(raw)
                os.replace(temporary, target)
            finally:
                temporary.unlink(missing_ok=True)

    def clear(self) -> int:
        # Restrict deletion to the cache's own manifest/blob format.
        removed = 0
        with CACHE_WRITE_LOCK:
            if self.directory.exists():
                for path in self.directory.iterdir():
                    if path.is_file() and re.fullmatch(r"[0-9a-f]{64}\.(?:json|png)", path.name):
                        path.unlink()
                        removed += 1
        return removed


class TileClient:
    def __init__(self, cache: TileCache | None = None, fetcher=None, timeout: float = 20):
        self.cache = cache if cache is not None else TileCache()
        self.fetcher = fetcher or self._request
        self.timeout = timeout
        self.network_requests = 0
        self._counter_lock = threading.Lock()

    def _request(self, key: TileKey) -> tuple[bytes, dict]:
        request = Request(key.url, headers={"User-Agent": "Steppe-Jukebox/0.3.0-local-NASA"})
        with urlopen(request, timeout=self.timeout) as response:
            raw = response.read(8 * 1024 * 1024 + 1)
            if len(raw) > 8 * 1024 * 1024:
                raise ValueError("Oversized tile response")
            return raw, {"http_status": response.status,
                         "actual_date": response.headers.get("layer-time-actual", ""),
                         "actual_layer": response.headers.get("layer-identifier-actual", ""),
                         "etag": response.headers.get("ETag", ""), "url": key.url}

    def fetch(self, key: TileKey, use_cache: bool = True, cancel_event=None) -> TileResult:
        start = time.monotonic()
        if cancel_event is not None and cancel_event.is_set():
            return TileResult(key, "cancelled")
        if use_cache and (cached := self.cache.get(key)) is not None:
            cached.seconds = time.monotonic() - start
            return cached
        with self._counter_lock:
            self.network_requests += 1
        try:
            raw, metadata = self.fetcher(key)
        except (HTTPError, URLError, TimeoutError, OSError) as error:
            return TileResult(key, "request_error", metadata={"url": key.url, "error": str(error)}, seconds=time.monotonic() - start)
        except ValueError as error:
            return TileResult(key, "invalid_image", metadata={"url": key.url, "error": str(error)}, seconds=time.monotonic() - start)
        metadata = {**metadata, "url": key.url, "requested_date": key.date,
                    "saved_at": datetime.now(timezone.utc).isoformat(), "bytes": len(raw)}
        if str(metadata.get("actual_date") or "")[:10] != key.date:
            return TileResult(key, "date_mismatch", metadata=metadata, seconds=time.monotonic() - start)
        try:
            validate_png(raw)
        except (OSError, ValueError, SyntaxError) as error:
            return TileResult(key, "invalid_image", metadata={**metadata, "error": str(error)}, seconds=time.monotonic() - start)
        metadata["sha256"] = hashlib.sha256(raw).hexdigest()
        result = TileResult(key, "ok", raw, metadata, seconds=time.monotonic() - start)
        try:
            with CACHE_WRITE_LOCK:
                if cancel_event is None or not cancel_event.is_set():
                    self.cache.put(result)
        except OSError as error:
            result.metadata["cache_write_error"] = str(error)
        return result



def pixel_coordinate(lat: float, lon: float, layer: str = "ndvi") -> tuple[int, int, int, int]:
    world = LAYERS[layer].world_pixels
    x = min(world - 1, max(0, math.floor((lon + 180) * world / 360)))
    y = min(world // 2 - 1, max(0, math.floor((90 - lat) * world / 360)))
    return y // 512, x // 512, y % 512, x % 512


class RegionGrid:
    def __init__(self, geometry: dict):
        self.geometry = geometry
        polygons = [geometry["coordinates"]] if geometry["type"] == "Polygon" else geometry["coordinates"]
        points = [point for polygon in polygons for ring in polygon for point in ring]
        west, south = min(p[0] for p in points), min(p[1] for p in points)
        east, north = max(p[0] for p in points), max(p[1] for p in points)
        self.bounds = (west, south, east, north)
        r0, c0, _, _ = pixel_coordinate(north, west)
        r1, c1, _, _ = pixel_coordinate(south, east)
        self.origin = (r0, c0)
        mask = Image.new("L", ((c1 - c0 + 1) * 512, (r1 - r0 + 1) * 512))
        draw = ImageDraw.Draw(mask)
        scale = 81920 / 360
        def xy(point):
            return ((point[0] + 180) * scale - c0 * 512,
                    (90 - point[1]) * scale - r0 * 512)
        for polygon in polygons:
            draw.polygon([xy(point) for point in polygon[0]], fill=255)
            for ring in polygon[1:]:
                draw.polygon([xy(point) for point in ring], fill=0)
        self.mask = np.array(mask) > 0
        self.positions = tuple((r, c) for r in range(r0, r1 + 1) for c in range(c0, c1 + 1)
                               if self.tile_mask(r, c).any())

    def tile_mask(self, row, col):
        r0, c0 = self.origin
        return self.mask[(row - r0) * 512:(row - r0 + 1) * 512,
                         (col - c0) * 512:(col - c0 + 1) * 512]


class Palette:
    def __init__(self, path: Path):
        self.entries: dict[tuple[int, int, int], list[dict]] = {}
        for entry in ET.parse(path).iter("ColorMapEntry"):
            if entry.get("transparent") == "true":
                continue
            rgb = tuple(map(int, entry.attrib["rgb"].split(",")))
            value = entry.get("value", "")
            numbers = re.findall(r"[-+]?\d+(?:\.\d+)?", value)
            self.entries.setdefault(rgb, []).append({"value": value, "numbers": tuple(map(Decimal, numbers)),
                                                     "source_value": entry.get("sourceValue", "")})

    def ndvi(self, rgba) -> dict:
        alpha = int(rgba[3])
        if alpha == 0:
            return {"status": "transparent", "ndvi_class": None}
        if alpha != 255:
            return {"status": "partial_alpha", "ndvi_class": None}
        rows = self.entries.get(tuple(map(int, rgba[:3])), [])
        ranges = {row["numbers"] for row in rows if len(row["numbers"]) == 2}
        if len(ranges) != 1 or not rows or len(ranges) != len({row["numbers"] for row in rows}):
            return {"status": "unknown_color", "ndvi_class": None}
        low, high = next(iter(ranges))
        value = max(1, min(5, math.floor((low + high) / 2 * 5) + 1))
        return {"status": "classified", "ndvi_class": value, "interval": [str(low), str(high)]}

    def snow_colors(self):
        return {rgb for rgb, rows in self.entries.items() if all(len(row["numbers"]) == 1 and 1 <= row["numbers"][0] <= 100 for row in rows)}

    def temperature(self, rgba) -> dict:
        if int(rgba[3]) == 0:
            return {"status": "temperature_unknown"}
        rows = self.entries.get(tuple(map(int, rgba[:3])), [])
        ranges = [row["numbers"] for row in rows]
        if not ranges or any(len(pair) != 2 for pair in ranges):
            return {"status": "temperature_unknown"}
        state = ("temperature_cold" if all(high <= THRESHOLD_K for low, high in ranges) else
                 "temperature_warm" if all(low > THRESHOLD_K for low, high in ranges) else "temperature_ambiguous")
        return {"status": state, "interval_c": [[str(low - Decimal('273.15')), str(high - Decimal('273.15'))] for low, high in ranges]}

    def temperature_colors(self):
        return {state: {rgb for rgb in self.entries if self.temperature((*rgb, 255))["status"] == state}
                for state in ["temperature_cold", "temperature_warm", "temperature_ambiguous"]}

    def water_colors(self):
        return {rgb for rgb, rows in self.entries.items() if all(row["source_value"] == "1,253" for row in rows)}


def match_colors(rgba, colors):
    codes = rgba[:, :, 0].astype(np.uint32) * 65536 + rgba[:, :, 1].astype(np.uint32) * 256 + rgba[:, :, 2]
    return np.isin(codes, [r * 65536 + g * 256 + b for r, g, b in colors]) & (rgba[:, :, 3] > 0)


def upsample_temperature(result: TileResult | None, row: int, col: int):
    if result is None or result.status != "ok":
        return None
    data = result.rgba()
    crop = data[(row % 2) * 256:(row % 2 + 1) * 256, (col % 2) * 256:(col % 2 + 1) * 256]
    return np.repeat(np.repeat(crop, 2, axis=0), 2, axis=1)


def png_bytes(rgba) -> bytes:
    stream = io.BytesIO()
    Image.fromarray(rgba).save(stream, format="PNG")
    return stream.getvalue()


def overlays(ndvi: TileResult, mask, snow: TileResult | None = None, temperature: TileResult | None = None,
             water: TileResult | None = None, palettes: dict | None = None) -> dict:
    palettes = palettes or {key: Palette(PALETTES / f"{key}.xml") for key in ["ndvi", "snow", "temperature", "water"]}
    counts = dict(snow=0, temperature_cold=0, temperature_warm=0, temperature_ambiguous=0, temperature_unknown=0, water=0)
    if ndvi.status != "ok":
        return {"snow_png": None, "water_png": None, "counts": counts}
    n = ndvi.rgba()
    gap = (n[:, :, 3] == 0) & mask
    white = np.zeros((512, 512), dtype=bool)
    if snow is not None and snow.status == "ok" and snow.key.date == ndvi.key.date:
        white = gap & match_colors(snow.rgba(), palettes["snow"].snow_colors())
    counts["snow"] = int(white.sum())
    t = upsample_temperature(temperature, ndvi.key.row, ndvi.key.col) if temperature is not None and temperature.key.date == ndvi.key.date else None
    supported = np.zeros_like(white)
    if t is not None:
        for state, colors in palettes["temperature"].temperature_colors().items():
            selected = white & match_colors(t, colors)
            counts[state] = int(selected.sum())
            supported |= selected
    counts["temperature_unknown"] = int((white & ~supported).sum())
    blue = np.zeros_like(white)
    if water is not None and water.status == "ok":
        blue = gap & match_colors(water.rgba(), palettes["water"].water_colors())
    counts["water"] = int(blue.sum())
    white_image = np.zeros_like(n); white_image[white] = [255, 255, 255, 255]
    blue_image = np.zeros_like(n); blue_image[blue] = [100, 190, 230, 255]
    return {"snow_png": png_bytes(white_image), "water_png": png_bytes(blue_image), "counts": counts}
