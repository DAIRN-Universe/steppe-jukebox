"""Prepare a frontend-only transport so season changes stop audio immediately."""

import base64
import hashlib
import json
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
    }
    for season in dataset.seasons:
        track = build_track(dataset.route, season.classes)
        payload["seasons"].append({
            "key": season.key,
            "name": season.name,
            "date": season.date,
            "source_url": season.source_url,
            "audio_src": "data:audio/wav;base64," + base64.b64encode(track.wav).decode("ascii"),
            "duration_s": track.duration_s,
            "intervals": [dict(asdict(slot), start_s=slot.start_s, end_s=slot.end_s) for slot in track.intervals],
        })
    return _with_translations(payload)
