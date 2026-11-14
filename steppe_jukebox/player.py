"""Prepare a frontend-only transport so season changes stop audio immediately."""

import base64
import hashlib
import json
import math
from dataclasses import asdict
from pathlib import Path

from .data import DataError, Dataset
from .sound import BPM, MISSING_COLOR, SAMPLE_RATE, SCALE, STEP_SECONDS, build_track


def _with_translations(payload: dict) -> dict:
    payload["translations"] = json.loads((Path(__file__).parent / "frontend" / "locales.json").read_text(encoding="utf-8"))
    payload["revision"] = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    return payload


def error_payload(error: DataError) -> dict:
    return _with_translations({"error": {"code": error.code, "context": error.context}})


def _track_payload(route, classes) -> dict:
    track = build_track(route, classes)
    return {
        "audio_src": "data:audio/wav;base64," + base64.b64encode(track.wav).decode("ascii"),
        "duration_s": track.duration_s,
        "intervals": [dict(asdict(slot), start_s=slot.start_s, end_s=slot.end_s) for slot in track.intervals],
    }


def _route_distances(route) -> list[float]:
    distances = [0.0]
    for first, second in zip(route, route[1:]):
        lat1, lat2 = math.radians(first.lat), math.radians(second.lat)
        dlat, dlon = lat2 - lat1, math.radians(second.lon - first.lon)
        a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
        distances.append(distances[-1] + 6371 * 2 * math.atan2(math.sqrt(a), math.sqrt(max(0, 1 - a))))
    return distances


def player_payload(dataset: Dataset) -> dict:
    payload = {
        "route": [asdict(cell) for cell in dataset.route],
        "bpm": BPM,
        "sample_rate": SAMPLE_RATE,
        "step_seconds": STEP_SECONDS,
        "is_test": dataset.is_test,
        "description": dataset.description,
        "description_i18n": dict(dataset.description_i18n),
        "missing_color": MISSING_COLOR,
        "scale": [dict(asdict(note), frequency=note.frequency) for note in SCALE],
        "seasons": [],
        "journey": None,
    }
    for season in dataset.seasons:
        payload["seasons"].append({
            "key": season.key,
            "name": season.name,
            "date": season.date,
            "source_url": season.source_url,
            **_track_payload(dataset.route, season.classes),
        })
    if dataset.journey is not None:
        journey = dataset.journey
        item = _track_payload(dataset.route, tuple(step.ndvi_class for step in journey.steps))
        landmarks = dict(journey.landmarks)
        distances = _route_distances(dataset.route)
        item.update(key="journey", source_url=journey.source_url, distance_km=distances[-1])
        for index, (step, slot) in enumerate(zip(journey.steps, item["intervals"], strict=True)):
            slot.update(date=step.date, landmark=landmarks.get(step.cell_id), distance_km=distances[index])
        payload["journey"] = item
    return _with_translations(payload)


def regions_payload(regions) -> dict:
    items = []
    for region in regions:
        item = player_payload(region.dataset)
        item.pop("translations")
        item.pop("revision")
        item.update(region_key=region.key, boundary=region.boundary, map_source_url=region.source_url)
        items.append(item)
    return _with_translations({"regions": items})
