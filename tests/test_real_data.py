"""Offline acceptance checks for the exact CSVs supplied in Issue #1."""

import hashlib
import io
import json
import wave
from collections import Counter
from pathlib import Path

import pytest

from steppe_jukebox.data import load_dataset
from steppe_jukebox.sound import SAMPLE_RATE, SCALE, STEP_SAMPLES, build_track


ROOT = Path(__file__).resolve().parents[1]
REAL = ROOT / "data" / "real-test"


def test_imported_files_match_issue_1_bytes():
    provenance = json.loads((REAL / "provenance.json").read_text())
    assert provenance["source_comment"] == "https://github.com/DAIRN-Universe/steppe-jukebox/issues/1#issuecomment-6873947119"
    assert len(provenance["files"]) == 8
    for relative_path, expected_sha256 in provenance["files"].items():
        assert hashlib.sha256((ROOT / relative_path).read_bytes()).hexdigest() == expected_sha256, relative_path


@pytest.mark.parametrize("name,count,dates,rests,changed,comparable", [
    ("noaa20-kostanay", 48, ("2026-04-15", "2026-07-16"), (1, 0), 36, 47),
    ("eic-kostanay", 137, ("2025-04-15", "2025-07-15"), (0, 46), 72, 91),
])
def test_real_dataset_contract_and_seasonal_contrast(name, count, dates, rests, changed, comparable):
    dataset = load_dataset(REAL / name)
    assert not dataset.is_test
    assert len(dataset.route) == count
    assert len({cell.cell_id for cell in dataset.route}) == count
    assert tuple(season.date for season in dataset.seasons) == dates
    assert tuple(season.classes.count(None) for season in dataset.seasons) == rests
    for season in dataset.seasons:
        assert len(season.classes) == count
        assert season.source_url.startswith("https://")
        assert "nasa.gov" in season.source_url
        assert set(Counter(season.classes)) <= {1, 2, 3, 4, 5, None}
    spring, summer = dataset.seasons
    pairs = [(a, b) for a, b in zip(spring.classes, summer.classes, strict=True) if a is not None and b is not None]
    assert len(pairs) == comparable
    assert sum(a != b for a, b in pairs) == changed


@pytest.mark.parametrize("name", ["noaa20-kostanay", "eic-kostanay"])
@pytest.mark.parametrize("season_index", [0, 1])
def test_real_audio_has_exact_timing_and_silent_missing_cells(name, season_index):
    dataset = load_dataset(REAL / name)
    season = dataset.seasons[season_index]
    track = build_track(dataset.route, season.classes)
    assert track.duration_s == len(dataset.route) * 0.5
    with wave.open(io.BytesIO(track.wav), "rb") as wav:
        assert wav.getframerate() == SAMPLE_RATE
        assert wav.getnframes() == len(dataset.route) * STEP_SAMPLES
        pcm = wav.readframes(wav.getnframes())
    for index, (cell, value, slot) in enumerate(zip(dataset.route, season.classes, track.intervals, strict=True)):
        assert slot.cell_id == cell.cell_id
        assert (slot.start_s, slot.end_s) == (index * 0.5, (index + 1) * 0.5)
        chunk = pcm[slot.start_sample * 2:slot.end_sample * 2]
        if value is None:
            assert slot.note is None
            assert chunk == bytes(STEP_SAMPLES * 2)
        else:
            assert slot.note == SCALE[value - 1].name
            assert any(chunk)
