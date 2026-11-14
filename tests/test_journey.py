import base64
import csv
import hashlib
import io
import json
import shutil
import subprocess
import sys
import wave
from datetime import date, timedelta
from pathlib import Path

import pytest

from steppe_jukebox.data import DataError, load_dataset
from steppe_jukebox.player import player_payload
from steppe_jukebox.sound import SAMPLE_RATE, SCALE, STEP_SAMPLES, build_track


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data" / "real-test" / "noaa20-kostanay"


@pytest.fixture
def journey_dir(tmp_path):
    directory = tmp_path / "journey"
    shutil.copytree(SOURCE, directory)
    return directory


def rewrite(directory, mutation):
    path = directory / "journey.csv"
    rows = list(csv.reader(io.StringIO(path.read_text())))
    mutation(rows)
    with path.open("w", newline="") as target:
        csv.writer(target).writerows(rows)


def test_source_journey_matches_issue_11_and_calendar_formula():
    provenance = json.loads((SOURCE / "journey_provenance.json").read_text())
    assert provenance["source_issue"].endswith("/issues/11")
    assert hashlib.sha256((SOURCE / "journey.csv").read_bytes()).hexdigest() == provenance["journey_csv_sha256"]
    assert hashlib.sha256((SOURCE / "route.csv").read_bytes()).hexdigest() == provenance["route_csv_sha256"]
    dataset = load_dataset(SOURCE)
    steps = dataset.journey.steps
    assert len(steps) == len(dataset.route) == 48
    assert [step.cell_id for step in steps] == [cell.cell_id for cell in dataset.route]
    assert all(step.ndvi_class is not None for step in steps)
    assert [step.date for step in steps] == [(date(2026, 4, 15) + timedelta(days=round(i * 212 / 47))).isoformat() for i in range(48)]
    assert (steps[0].date, steps[17].date, steps[-1].date) == ("2026-04-15", "2026-07-01", "2026-11-13")
    assert dict(dataset.journey.landmarks) == {"KST-001": "kamennoye_lake", "KST-018": "naurzum", "KST-048": "akkum"}


@pytest.mark.parametrize("mutation", ["headers", "reorder", "missing", "extra", "duplicate", "unknown"])
def test_journey_requires_exact_headers_and_route_alignment(journey_dir, mutation):
    def change(rows):
        if mutation == "headers":
            rows[0] = ["cell_id", "ndvi_class", "date"]
        elif mutation == "reorder":
            rows[1], rows[2] = rows[2], rows[1]
        elif mutation == "missing":
            rows.pop(4)
        elif mutation == "extra":
            rows.append(["extra", "2026-11-14", "2"])
        elif mutation == "duplicate":
            rows[2][0] = rows[1][0]
        else:
            rows[1][0] = "unknown"
    rewrite(journey_dir, change)
    with pytest.raises(DataError):
        load_dataset(journey_dir)


@pytest.mark.parametrize("value", ["", "20260415", "2026-4-15", "2026-02-29", "2026-13-01", "not-a-date"])
def test_journey_rejects_invalid_dates(journey_dir, value):
    rewrite(journey_dir, lambda rows: rows[1].__setitem__(1, value))
    with pytest.raises(DataError) as error:
        load_dataset(journey_dir)
    assert error.value.code == "journey_date"


@pytest.mark.parametrize("value", ["2026-04-15", "2026-04-14"])
def test_journey_rejects_equal_or_decreasing_dates(journey_dir, value):
    rewrite(journey_dir, lambda rows: rows[2].__setitem__(1, value))
    with pytest.raises(DataError) as error:
        load_dataset(journey_dir)
    assert error.value.code == "journey_date_order"


@pytest.mark.parametrize("value", ["0", "6", "1.0", "NaN", "null"])
def test_journey_rejects_invalid_classes(journey_dir, value):
    rewrite(journey_dir, lambda rows: rows[1].__setitem__(2, value))
    with pytest.raises(DataError):
        load_dataset(journey_dir)


@pytest.mark.parametrize("metadata", [[], {"source_url": "javascript:alert(1)"}, {"landmarks": {"unknown": "naurzum"}}, {"landmarks": {"KST-001": ""}}])
def test_journey_rejects_invalid_metadata(journey_dir, metadata):
    (journey_dir / "journey_metadata.json").write_text(json.dumps(metadata))
    with pytest.raises(DataError):
        load_dataset(journey_dir)


def test_missing_class_preserves_date_order_and_full_silent_interval(journey_dir):
    rewrite(journey_dir, lambda rows: rows[18].__setitem__(2, ""))
    dataset = load_dataset(journey_dir)
    steps = dataset.journey.steps
    assert steps[17].date == "2026-07-01" and steps[17].ndvi_class is None
    track = build_track(dataset.route, tuple(step.ndvi_class for step in steps))
    assert track.duration_s == 24
    assert (track.intervals[17].start_s, track.intervals[17].end_s) == (8.5, 9.0)
    with wave.open(io.BytesIO(track.wav), "rb") as wav:
        wav.setpos(17 * STEP_SAMPLES)
        assert wav.readframes(STEP_SAMPLES) == bytes(STEP_SAMPLES * 2)


def test_journey_and_fixed_slice_use_identical_note_samples_and_timing():
    dataset = load_dataset(SOURCE)
    classes = tuple(step.ndvi_class for step in dataset.journey.steps)
    tracks = [build_track(dataset.route, dataset.seasons[0].classes), build_track(dataset.route, classes)]
    seen = {}
    for track in tracks:
        assert track.duration_s == 24
        with wave.open(io.BytesIO(track.wav), "rb") as wav:
            assert wav.getnframes() == 48 * STEP_SAMPLES
            assert wav.getframerate() == SAMPLE_RATE
            pcm = wav.readframes(wav.getnframes())
        for slot in track.intervals:
            if slot.ndvi_class is None:
                continue
            chunk = pcm[slot.start_sample * 2:slot.end_sample * 2]
            assert slot.note == SCALE[slot.ndvi_class - 1].name
            if slot.ndvi_class in seen:
                assert chunk == seen[slot.ndvi_class]
            seen[slot.ndvi_class] = chunk
    assert set(seen) == {1, 2, 3, 4}


def test_payload_dates_landmarks_and_audio_follow_one_timeline():
    dataset = load_dataset(SOURCE)
    payload = player_payload(dataset)
    journey = payload["journey"]
    assert journey["duration_s"] == 24
    assert journey["distance_km"] == pytest.approx(466, abs=2)
    assert [(slot["cell_id"], slot["date"]) for slot in journey["intervals"]] == [(step.cell_id, step.date) for step in dataset.journey.steps]
    assert journey["intervals"][17]["start_s"] == 8.5
    assert journey["intervals"][17]["landmark"] == "naurzum"
    track = build_track(dataset.route, tuple(step.ndvi_class for step in dataset.journey.steps))
    assert base64.b64decode(journey["audio_src"].split(",", 1)[1]) == track.wav


def test_export_writes_journey_wav_and_dated_timing_csv(tmp_path):
    subprocess.run([sys.executable, "-m", "steppe_jukebox.export", "--data-dir", str(SOURCE), "--output-dir", str(tmp_path)], check=True, capture_output=True, cwd=ROOT)
    with (tmp_path / "journey_timing.csv").open() as source:
        rows = list(csv.DictReader(source))
    assert len(rows) == 48
    assert rows[0]["date"] == "2026-04-15"
    assert rows[17]["date"] == "2026-07-01"
    assert rows[-1]["date"] == "2026-11-13"
    assert rows[-1]["end_s"] == "24.0"
    with wave.open(str(tmp_path / "journey.wav"), "rb") as wav:
        assert wav.getnframes() / wav.getframerate() == 24


def test_dataset_without_journey_still_loads_fixed_modes_only():
    assert load_dataset(ROOT / "data" / "synthetic").journey is None
    assert load_dataset(ROOT / "data" / "real-test" / "eic-kostanay").journey is None
