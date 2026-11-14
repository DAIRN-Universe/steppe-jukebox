"""SVS 5544 frames, their own color scale, and a persistent source-specific cache."""
from __future__ import annotations

import hashlib
import io
import json
import math
import os
import re
import threading
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

import numpy as np
from PIL import Image

from .gibs import PALETTES, user_cache_directory
from .nasa_grid import UNKNOWN_COLOR, rgba_color
from .sound import MISSING_COLOR, SCALE

BASE = "https://svs.gsfc.nasa.gov/vis/a000000/a005500/a005544/frames/8640x4320_2x1_30p/equirectangular/"
VARIANT = "ndvi_w_snow.oceanblue"
FRAME_PATTERN = re.compile(r"SNPP_VIIRS\.(\d{8})\.ndvi_w_snow\.oceanblue\.png")
WRITE_LOCK = threading.RLock()


def cache_directory():
    return user_cache_directory().parent / "nasa-eic"


def frame_name(day):
    return f"SNPP_VIIRS.{date.fromisoformat(day):%Y%m%d}.{VARIANT}.png"


def identity(day):
    return f"NASA-EIC/SVS5544/SNPP-VIIRS/{day}/equirectangular/8640x4320/{VARIANT}"


def validate_frame(raw):
    with Image.open(io.BytesIO(raw)) as image:
        if image.format != "PNG" or image.size != (8640, 4320):
            raise ValueError("Expected the native 8640×4320 equirectangular EIC PNG")
        image.verify()
    with Image.open(io.BytesIO(raw)) as image:
        image.load()


@dataclass
class FrameResult:
    day: str
    status: str
    raw: bytes | None = None
    metadata: dict | None = None
    from_cache: bool = False


class FrameClient:
    def __init__(self, directory=None, fetcher=None):
        self.directory = Path(directory) if directory is not None else cache_directory()
        self.fetcher = fetcher or self._request
        self.network_requests = 0

    @staticmethod
    def _request(url):
        with urlopen(Request(url, headers={"User-Agent": "Steppe-Jukebox/local-EIC"}), timeout=60) as response:
            raw = response.read(160 * 1024 * 1024 + 1)
            if len(raw) > 160 * 1024 * 1024:
                raise ValueError("Oversized EIC response")
            if response.status != 200 or response.geturl() != url:
                raise ValueError("Unexpected EIC status or redirected date/variant")
            return raw

    def _write(self, path, raw):
        self.directory.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
        try:
            temporary.write_bytes(raw)
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)

    def clear(self):
        removed = 0
        with WRITE_LOCK:
            if self.directory.exists():
                for path in self.directory.iterdir():
                    if path.is_file() and (path.name in {"catalog.json", "catalog.html"} or re.fullmatch(r"[a-f0-9]{64}\.(?:png|json)", path.name)):
                        path.unlink()
                        removed += 1
        return removed

    def catalog(self, refresh=False, cancel=None):
        """A cached, hash-verified catalog works offline; no fabricated dates."""
        path = self.directory / "catalog.json"
        if not refresh:
            try:
                manifest = json.loads(path.read_text())
                raw = (self.directory / "catalog.html").read_bytes()
                if manifest["url"] == BASE and hashlib.sha256(raw).hexdigest() == manifest["sha256"]:
                    return self._dates(raw)
            except (OSError, ValueError, KeyError, TypeError):
                pass
        self.network_requests += 1
        raw = self.fetcher(BASE)
        days = self._dates(raw)
        with WRITE_LOCK:
            if cancel is None or not cancel.is_set():
                self._write(self.directory / "catalog.html", raw)
                self._write(path, json.dumps({"url": BASE, "sha256": hashlib.sha256(raw).hexdigest(),
                                             "checked_at": datetime.now(timezone.utc).isoformat()}).encode())
        return days

    @staticmethod
    def _dates(raw):
        days = set()
        for value in FRAME_PATTERN.findall(raw.decode("utf-8")):
            days.add(date.fromisoformat(f"{value[:4]}-{value[4:6]}-{value[6:]}").isoformat())
        if not days:
            raise ValueError("EIC catalog contains no supported native frames")
        return sorted(days)

    def cached(self, day):
        key = hashlib.sha256(identity(day).encode()).hexdigest()
        try:
            meta = json.loads((self.directory / (key + ".json")).read_text())
            if (meta["identity"] != identity(day) or meta["actual_date"] != day or meta["filename"] != frame_name(day)
                    or meta.get("url") != BASE + frame_name(day)):
                return None
            digest = meta["sha256"]
            if not re.fullmatch(r"[a-f0-9]{64}", digest):
                return None
            raw = (self.directory / (digest + ".png")).read_bytes()
            if hashlib.sha256(raw).hexdigest() != digest:
                return None
            validate_frame(raw)
            return FrameResult(day, "ok", raw, meta, True)
        except (OSError, ValueError, SyntaxError, TypeError, KeyError):
            return None

    def fetch(self, day, days=None, use_cache=True, cancel=None):
        date.fromisoformat(day)
        # Confirm catalog membership even when an untrusted cache file exists.
        days = self.catalog() if days is None else days
        if day not in days:
            return FrameResult(day, "unavailable_date", metadata={"requested_date": day})
        if cancel is not None and cancel.is_set():
            return FrameResult(day, "cancelled")
        if use_cache and (cached := self.cached(day)) is not None:
            return cached
        url = BASE + frame_name(day)
        self.network_requests += 1
        try:
            raw = self.fetcher(url)
        except (OSError, ValueError) as error:
            return FrameResult(day, "request_error", metadata={"url": url, "error": str(error)})
        try:
            validate_frame(raw)
        except (OSError, ValueError, SyntaxError) as error:
            return FrameResult(day, "invalid_image", metadata={"url": url, "error": str(error)})
        meta = {"identity": identity(day), "requested_date": day, "actual_date": day,
                "filename": frame_name(day), "url": url, "sha256": hashlib.sha256(raw).hexdigest(),
                "date_evidence": "Exact filename in NASA SVS catalog; exact URL, no redirect", "bytes": len(raw)}
        with WRITE_LOCK:
            if cancel is None or not cancel.is_set():
                self._write(self.directory / (meta["sha256"] + ".png"), raw)
                self._write(self.directory / (hashlib.sha256(identity(day).encode()).hexdigest() + ".json"), json.dumps(meta).encode())
        return FrameResult(day, "ok", raw, meta)


class EicPalette:
    """Five sections along EIC's own Low–High colorbar, never a GIBS palette."""
    def __init__(self):
        with Image.open(PALETTES / "eic-colorbar.png") as image:
            self.ramp = np.array(image.convert("RGB"))[125, 102:798].astype(np.int32)

    def classify(self, pixels):
        shape = pixels.shape[:-1]
        rgb = pixels[..., :3].reshape(-1, 3)
        colors, inverse = np.unique(rgb, axis=0, return_inverse=True)
        values = np.full(len(colors), -1, dtype=np.int8)  # Unknown opaque color.
        for offset in range(0, len(colors), 512):
            part = colors[offset:offset+512].astype(np.int32)
            distances = ((part[:, None, :] - self.ramp[None, :, :]) ** 2).sum(axis=2)
            nearest = distances.argmin(axis=1)
            accepted = distances.min(axis=1) <= 45**2
            values[offset:offset+len(part)][accepted] = np.minimum(5, 1 + nearest[accepted] * 5 // len(self.ramp))
        # Source variant explicitly includes snow/blue-water masks: no displayed NDVI.
        white = (colors == [255, 255, 255]).all(axis=1)
        blue = (colors == [8, 123, 176]).all(axis=1)
        values[white | blue] = 0
        result = values[inverse].reshape(shape)
        if pixels.shape[-1] == 4:
            result = result.copy()
            result[pixels[..., 3] == 0] = 0
            result[(pixels[..., 3] != 0) & (pixels[..., 3] != 255)] = -1
        return result

    def sample(self, image, lat, lon):
        x = min(8639, max(0, math.floor((lon + 180) / 360 * 8640)))
        y = min(4319, max(0, math.floor((90 - lat) / 180 * 4320)))
        rgba = np.array(image.getpixel((x, y)), dtype=np.uint8)
        value = int(self.classify(rgba[None, :])[0])
        return {"status": "classified" if value > 0 else "no_data" if value == 0 else "unknown_color",
                "ndvi_class": value if value > 0 else None, "rgba": rgba.tolist(), "pixel_x": x, "pixel_y": y}

    def crop(self, image, bounds):
        west, south, east, north = bounds
        left, right = max(0, math.floor((west+180)*24)), min(8640, math.ceil((east+180)*24))
        top, bottom = max(0, math.floor((90-north)*24)), min(4320, math.ceil((90-south)*24))
        pixels = np.array(image.crop((left, top, right, bottom)))
        values = self.classify(pixels)
        output = np.empty((*values.shape, 4), dtype=np.uint8)
        output[:] = rgba_color(UNKNOWN_COLOR)
        output[values == 0] = rgba_color(MISSING_COLOR)
        for index, note in enumerate(SCALE, 1):
            output[values == index] = rgba_color(note.color)
        return output, [-180+left/24, 90-bottom/24, -180+right/24, 90-top/24]
