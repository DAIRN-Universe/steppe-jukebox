"""Live source jobs for the existing player. CSVs supply geometry and dates only."""
from __future__ import annotations

import csv
import io
import json
import threading
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from PIL import Image

from .data import Cell, load_route
from .eic import BASE as EIC_BASE, EicPalette, FrameClient
from .gibs import RegionGrid, TileClient, png_bytes
from .nasa_grid import display_grid
from .nasa_job import MapJob, image_url
from .player import _route_distances, _track_payload, _with_translations
from .regions import load_boundary
from .sound import BPM, MISSING_COLOR, SAMPLE_RATE, SCALE, STEP_SECONDS

ROOT = Path(__file__).resolve().parents[1]
GIBS_SOURCE = "https://gibs.earthdata.nasa.gov/layer-metadata/v1.0/VIIRS_NOAA20_NDVI_8Day.json"


@dataclass
class LiveRegion:
    key: str
    route: tuple[Cell, ...]
    grid: RegionGrid
    dates: tuple[str, ...]
    landmarks: dict
    map_source: str

    def intervals(self, days):
        distances = _route_distances(self.route)
        return [{"cell_id": cell.cell_id, "ndvi_class": None, "note": None,
                 "start_s": i * STEP_SECONDS, "end_s": (i+1) * STEP_SECONDS,
                 "date": days[i], "landmark": self.landmarks.get(cell.cell_id), "distance_km": distances[i]}
                for i, cell in enumerate(self.route)]


def load_live_regions():
    result = {}
    for item in json.loads((ROOT / "data/regions.json").read_text()):
        folder = ROOT / "data" / item["dataset"]
        route = load_route(folder / "route.csv")
        with (folder / "journey.csv").open(newline="", encoding="utf-8-sig") as file:
            records = list(csv.DictReader(file))
        if [r["cell_id"] for r in records] != [c.cell_id for c in route]:
            raise ValueError("Journey date IDs must match route geometry")
        days = tuple(date.fromisoformat(r["date"]).isoformat() for r in records)
        if any(a >= b for a, b in zip(days, days[1:])):
            raise ValueError("Journey dates must increase")
        metadata = json.loads((folder / "journey_metadata.json").read_text())
        result[item["key"]] = LiveRegion(item["key"], route, RegionGrid(load_boundary(ROOT / "data" / item["boundary"])),
                                         days, metadata.get("landmarks", {}), item["map_source_url"])
    return result


def player_catalog(regions):
    items = []
    for region in regions.values():
        intervals = region.intervals(["2026-04-20"] * len(region.route))
        track = {"key": "selected_date", "name": "", "date": "2026-04-20", "duration_s": len(intervals)*STEP_SECONDS,
                 "audio_src": None, "intervals": intervals, "source_url": GIBS_SOURCE}
        journey = {**track, "key": "journey", "intervals": region.intervals(region.dates),
                   "distance_km": _route_distances(region.route)[-1]}
        items.append({"region_key": region.key, "route": [vars(cell) for cell in region.route],
                      "boundary": region.grid.geometry, "map_source_url": region.map_source,
                      "map_config": {"bounds": region.grid.bounds, "point_ids": [cell.cell_id for cell in region.route],
                                     **display_grid(region.grid, region.route)},
                      "bpm": BPM, "sample_rate": SAMPLE_RATE, "step_seconds": STEP_SECONDS,
                      "is_test": False, "description": "", "description_i18n": {}, "missing_color": MISSING_COLOR,
                      "scale": [{"name": n.name, "color": n.color} for n in SCALE], "seasons": [track], "journey": journey})
    return _with_translations({"regions": items, "live": True})


class LiveJob:
    def __init__(self, request_id, region, source, mode, day, gibs=None, eic=None, layers=None):
        if source not in {"gibs", "eic"} or mode not in {"fixed", "journey"}:
            raise ValueError("Unknown source or mode")
        if date.fromisoformat(day).isoformat() != day:
            raise ValueError("Invalid ISO date")
        self.request_id, self.region, self.source, self.mode, self.day = request_id, region, source, mode, day
        self.days = region.dates if mode == "journey" else tuple(day for _ in region.route)
        self.gibs = gibs if gibs is not None else TileClient()
        self.layers = layers or {}
        self.eic = eic if eic is not None else FrameClient()
        self.cancelled = threading.Event()
        self.lock = threading.RLock()
        self.maps, self.versions, self.track = {}, {}, None
        self.state, self.error, self.missing_dates = "loading", None, []
        self.available_dates = []
        self.started = time.monotonic()
        self.thread = None
        self.map_job = None

    def start(self):
        self.thread = threading.Thread(target=self._run, daemon=True, name="steppe-live-source")
        self.thread.start()
        return self

    def cancel(self):
        self.cancelled.set()
        if self.map_job is not None:
            self.map_job.cancel()

    def _publish(self, day, value):
        with self.lock:
            self.maps[day] = value
            self.versions[day] = self.versions.get(day, 0) + 1

    def _gibs_day(self, day):
        job = MapJob(self.request_id, day, self.region.grid, self.region.route, client=self.gibs,
                     snow=bool(self.layers.get("snow")), water=bool(self.layers.get("water")),
                     temperature=bool(self.layers.get("temperature")))
        self.map_job = job
        if self.cancelled.is_set():
            return
        job.start()
        previous = -1
        while True:
            if self.cancelled.is_set():
                job.cancel()
                return
            snapshot = job.snapshot(include_playback=False)
            completed = sum(t["status"] != "waiting" for t in snapshot["tiles"])
            if completed != previous or snapshot["done"]:
                images = [{"key": f'{t["row"]}/{t["col"]}', "src": t["src"], "bounds": t["bounds"]}
                          for t in snapshot["tiles"] if t["src"]]
                bounds = {(t["row"], t["col"]): t["bounds"] for t in snapshot["tiles"] if t["layer"] == "ndvi"}
                for kind in ["water", "snow"]:
                    images.extend({"key": f'{kind}/{d["row"]}/{d["col"]}', "src": d[kind+"_src"],
                                   "bounds": bounds[(d["row"], d["col"])]}
                                  for d in snapshot["decorations"] if d[kind+"_src"])
                self._publish(day, {"date": day, "source": "gibs", "done": snapshot["done"],
                                    "images": images,
                                    "tiles": [{k: v for k, v in t.items() if k != "src"} for t in snapshot["tiles"]],
                                    "points": snapshot["points"]})
                previous = completed
            if snapshot["done"]:
                return
            self.cancelled.wait(.2)

    def _eic_day(self, day, palette):
        result = self.eic.fetch(day, self.available_dates, cancel=self.cancelled)
        meta = result.metadata or {}
        tile = {"layer": "EIC", "date": day, "status": result.status, "from_cache": result.from_cache,
                "metadata": meta, "row": "—", "col": "—"}
        points, images = [], []
        if result.status == "ok":
            with Image.open(io.BytesIO(result.raw)) as file:
                image = file.convert("RGBA")
            for cell in self.region.route:
                points.append({"cell_id": cell.cell_id, "lat": cell.lat, "lon": cell.lon,
                               **palette.sample(image, cell.lat, cell.lon)})
            pixels, bounds = palette.crop(image, self.region.grid.bounds)
            images = [{"key": day, "src": image_url(png_bytes(pixels)), "bounds": bounds}]
        else:
            points = [{"cell_id": c.cell_id, "lat": c.lat, "lon": c.lon, "status": result.status, "ndvi_class": None}
                      for c in self.region.route]
        self._publish(day, {"date": day, "source": "eic", "done": True, "images": images, "tiles": [tile], "points": points})

    def _run(self):
        try:
            if self.source == "eic":
                self.available_dates = self.eic.catalog(cancel=self.cancelled)
                self.missing_dates = sorted(set(self.days) - set(self.available_dates))
                if self.missing_dates:
                    self.error, self.state = "unavailable_dates", "error"
                    return
            palette = EicPalette() if self.source == "eic" else None
            for day in dict.fromkeys(self.days):
                if self.cancelled.is_set():
                    return
                self._gibs_day(day) if self.source == "gibs" else self._eic_day(day, palette)
            if self.cancelled.is_set():
                return
            selected = [self.maps[day]["points"][i] for i, day in enumerate(self.days)]
            if any(p["status"] not in {"classified", "transparent", "no_data"} for p in selected):
                self.error, self.state = "route_data_error", "error"
                return
            track = _track_payload(self.region.route, tuple(p["ndvi_class"] for p in selected))
            metadata = self.region.intervals(self.days)
            for interval, info in zip(track["intervals"], metadata, strict=True):
                interval.update(date=info["date"], landmark=info["landmark"], distance_km=info["distance_km"])
            track.update(key="selected_date" if self.mode == "fixed" else "journey", name="", date=self.day,
                         source_url=GIBS_SOURCE if self.source == "gibs" else EIC_BASE,
                         distance_km=_route_distances(self.region.route)[-1])
            with self.lock:
                self.track, self.state = track, "ready"
        except Exception as error:
            with self.lock:
                self.error, self.state = "request_error", "error"
                self.detail = str(error)

    def payload(self, known=None):
        known = known or {}
        with self.lock:
            route_errors = []
            for index, day in enumerate(self.days):
                if day in self.maps:
                    point = self.maps[day]["points"][index]
                    if point["status"] not in {"classified", "transparent", "no_data", "waiting"}:
                        route_errors.append({"cell_id": point["cell_id"], "date": day, "status": point["status"]})
            return {"id": self.request_id, "source": self.source, "region": self.region.key, "mode": self.mode,
                    "date": self.day, "state": self.state, "error": self.error, "missing_dates": self.missing_dates,
                    "available_dates": self.available_dates, "elapsed_s": time.monotonic()-self.started,
                    "network_requests": self.gibs.network_requests if self.source == "gibs" else self.eic.network_requests,
                    "tile_errors": sum(t["status"] not in {"ok", "waiting"} for m in self.maps.values() for t in m["tiles"]),
                    "route_errors": route_errors,
                    "completed_dates": sum(v["done"] for v in self.maps.values()), "total_dates": len(set(self.days)),
                    "maps": [{**value, "version": self.versions[day]} for day, value in self.maps.items()
                             if known.get(day) != self.versions[day]], "track": self.track}
