"""Bounded concurrent map requests and progressive snapshots for the NASA view."""
from __future__ import annotations

import base64
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from .gibs import LAYERS, PALETTES, WATER_DATE, Palette, TileClient, TileKey, TileResult, overlays, pixel_coordinate
from .nasa_grid import class_image
from .sound import STEP_SECONDS, build_track


def image_url(raw):
    return "data:image/png;base64," + base64.b64encode(raw).decode() if raw is not None else None


class MapJob:
    def __init__(self, request_id, day, grid, route, expected=None, client=None, use_cache=True,
                 snow=False, temperature=False, water=False, workers=4):
        self.request_id, self.day, self.grid, self.route = request_id, day, grid, route
        self.expected = expected if day == "2026-04-15" else None
        self.client = client if client is not None else TileClient()
        self.use_cache = use_cache
        self.enabled = {"ndvi": True, "snow": snow, "temperature": temperature and snow, "water": water}
        self.workers = min(8, max(1, workers))
        self.started = time.monotonic()
        self.first_ready = self.full_ready = None
        self.done = False
        self.cancelled = False
        self.cancel_event = threading.Event()
        self.results = {}
        self.images = {}
        self.arrays = {}
        self.decorations = {}
        self.playback = None
        self.lock = threading.RLock()
        self.thread = None
        self._palettes = {key: Palette(PALETTES / f"{key}.xml") for key in LAYERS}
        self.keys = [TileKey("ndvi", day, r, c) for r, c in grid.positions]
        if snow:
            self.keys += [TileKey("snow", day, r, c) for r, c in grid.positions]
        if temperature and snow:
            self.keys += [TileKey("temperature", day, r, c) for r, c in sorted({(r // 2, c // 2) for r, c in grid.positions})]
        if water:
            self.keys += [TileKey("water", WATER_DATE, r, c) for r, c in grid.positions]

    def start(self):
        self.thread = threading.Thread(target=self._run, name="steppe-nasa-map", daemon=True)
        self.thread.start()
        return self

    def cancel(self):
        with self.lock:
            self.cancelled = True
            self.cancel_event.set()
            self.done = True

    def _get(self, layer, row, col):
        return self.results.get((layer, row, col))

    def _run(self):
        executor = ThreadPoolExecutor(max_workers=self.workers, thread_name_prefix="gibs-tile")
        futures = {executor.submit(self.client.fetch, key, self.use_cache, self.cancel_event): key for key in self.keys}
        try:
            for future in as_completed(futures):
                if self.cancelled:
                    break
                key = futures[future]
                try:
                    result = future.result()
                except Exception as error:
                    result = TileResult(key, "request_error", metadata={"url": key.url, "error": str(error)})
                with self.lock:
                    self.results[(key.layer, key.row, key.col)] = result
                    if result.status == "ok":
                        pixels = result.rgba()
                        if key.layer == "ndvi":
                            self.images[(key.layer, key.row, key.col)] = image_url(class_image(pixels, self._palettes["ndvi"]))
                        self.arrays[(key.layer, key.row, key.col)] = pixels
                    if key.layer == "ndvi":
                        if result.status == "ok" and self.first_ready is None:
                            self.first_ready = time.monotonic() - self.started
                        if all(self._get("ndvi", r, c) is not None for r, c in self.grid.positions):
                            self.full_ready = time.monotonic() - self.started
                    if self.enabled["snow"] or self.enabled["water"]:
                        affected = ([(key.row * 2 + dr, key.col * 2 + dc) for dr in (0, 1) for dc in (0, 1)]
                                    if key.layer == "temperature" else [(key.row, key.col)])
                        for row, col in affected:
                            ndvi = self._get("ndvi", row, col)
                            if (row, col) not in self.grid.positions or ndvi is None or ndvi.status != "ok":
                                continue
                            decoration = overlays(ndvi, self.grid.tile_mask(row, col), self._get("snow", row, col),
                                                  self._get("temperature", row // 2, col // 2), self._get("water", row, col), self._palettes)
                            self.decorations[(row, col)] = {"snow_src": image_url(decoration["snow_png"]),
                                                            "water_src": image_url(decoration["water_png"]), "counts": decoration["counts"]}
        finally:
            executor.shutdown(wait=False, cancel_futures=True)
            with self.lock:
                self.done = True

    def _sample(self, layer, lat, lon):
        row, col, y, x = pixel_coordinate(lat, lon, layer)
        result = self._get(layer, row, col)
        if result is None:
            return None, None
        if result.status != "ok":
            return result, None
        # Images are tiny; decode only the tile needed by the selected point.
        return result, self.arrays[(layer, row, col)][y, x]

    def pixel(self, lat, lon):
        with self.lock:
            result, rgba = self._sample("ndvi", lat, lon)
            base = {"lat": lat, "lon": lon, "requested_date": self.day}
            r, c, y, x = pixel_coordinate(lat, lon)
            if (r, c) not in self.grid.positions or not self.grid.tile_mask(r, c)[y, x]:
                return {**base, "status": "outside_region", "ndvi_class": None}
            if result is None:
                return {**base, "status": "waiting", "ndvi_class": None}
            if result.status != "ok":
                return {**base, "status": result.status, "ndvi_class": None, "actual_date": result.metadata.get("actual_date")}
            value = self._palettes["ndvi"].ndvi(rgba)
            value.update(base, rgba=list(map(int, rgba)), actual_date=result.metadata.get("actual_date"))
            snow, sr = self._sample("snow", lat, lon) if self.enabled["snow"] else (None, None)
            snow_detected = sr is not None and int(sr[3]) > 0 and tuple(map(int, sr[:3])) in self._palettes["snow"].snow_colors()
            value["snow"] = bool(value["status"] == "transparent" and snow_detected)
            value["snow_status"] = "snow_detected" if snow_detected else snow.status if snow is not None and snow.status != "ok" else "no_snow_evidence" if snow is not None else "waiting"
            temperature, tr = self._sample("temperature", lat, lon) if self.enabled["temperature"] else (None, None)
            value["temperature"] = self._palettes["temperature"].temperature(tr) if tr is not None else {"status": temperature.status if temperature is not None else "waiting"}
            water, wr = self._sample("water", lat, lon) if self.enabled["water"] else (None, None)
            value["water"] = bool(value["status"] == "transparent" and wr is not None and int(wr[3]) > 0 and tuple(map(int, wr[:3])) in self._palettes["water"].water_colors())
            value["water_date"] = WATER_DATE if water is not None else None
            if not self.enabled["snow"]: value["snow_status"] = "layer_off"
            if not self.enabled["temperature"]: value["temperature"] = {"status": "layer_off"}
            return value

    def snapshot(self, include_playback=True):
        with self.lock:
            # Decode each tile once for all 48 control samples.
            arrays = self.arrays
            points = []
            for index, cell in enumerate(self.route):
                row, col, y, x = pixel_coordinate(cell.lat, cell.lon)
                result = self._get("ndvi", row, col)
                value = ({"status": "waiting", "ndvi_class": None} if result is None else
                         {"status": result.status, "ndvi_class": None} if result.status != "ok" else
                         self._palettes["ndvi"].ndvi(arrays[("ndvi", row, col)][y, x]))
                value.update(cell_id=cell.cell_id, lat=cell.lat, lon=cell.lon, row=row, col=col)
                if self.expected is not None:
                    expected = self.expected[index]
                    value.update(expected=expected, matches=(value["status"] == "classified" and value["ndvi_class"] == expected) or
                                 (expected is None and value["status"] == "transparent"))
                points.append(value)
            # Use the same synthesizer and exact route samples as the saved player.
            # A failed/unknown sample must never silently become a musical rest.
            if include_playback and self.playback is None and self.done and not self.cancelled and points and all(
                    point["status"] in {"classified", "transparent"} for point in points):
                track = build_track(self.route, tuple(point["ndvi_class"] for point in points))
                self.playback = {"audio_src": "data:audio/wav;base64," + base64.b64encode(track.wav).decode("ascii"),
                                 "duration_s": track.duration_s, "step_seconds": STEP_SECONDS,
                                 "intervals": [{"cell_id": slot.cell_id, "ndvi_class": slot.ndvi_class,
                                                "note": slot.note, "start_s": slot.start_s, "end_s": slot.end_s}
                                               for slot in track.intervals]}
            tiles = []
            for key in self.keys:
                result = self.results.get((key.layer, key.row, key.col))
                tiles.append({"layer": key.layer, "row": key.row, "col": key.col, "date": key.date,
                              "status": result.status if result is not None else "waiting",
                              "from_cache": result.from_cache if result else False,
                              "metadata": result.metadata if result else {},
                              "src": self.images.get((key.layer, key.row, key.col)) if key.layer == "ndvi" else None,
                              "bounds": list(key.bounds)})
            decoration = [{"row": r, "col": c, **item} for (r, c), item in self.decorations.items()]
            counts = {key: sum(item["counts"][key] for item in self.decorations.values()) for key in
                      ["snow", "water", "temperature_cold", "temperature_warm", "temperature_ambiguous", "temperature_unknown"]}
            return {"request_id": self.request_id, "date": self.day, "done": self.done, "cancelled": self.cancelled,
                    "enabled": self.enabled, "tiles": tiles, "decorations": decoration, "points": points, "counts": counts,
                    "network_requests": self.client.network_requests, "first_ready_s": self.first_ready,
                    "full_ready_s": self.full_ready, "cache_directory": str(self.client.cache.directory),
                    "playback": self.playback}
