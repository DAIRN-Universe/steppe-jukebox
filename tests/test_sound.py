import base64
import csv
import io
import subprocess
import sys
import wave
from array import array
from pathlib import Path

import pytest

from steppe_jukebox.data import Cell, load_dataset
from steppe_jukebox.player import player_payload
from steppe_jukebox.sound import BPM, SAMPLE_RATE, SCALE, STEP_SAMPLES, STEP_SECONDS, build_track


ROOT = Path(__file__).resolve().parents[1]


def pcm(wav):
    with wave.open(io.BytesIO(wav), "rb") as source:
        assert source.getnchannels() == 1
        assert source.getsampwidth() == 2
        assert source.getframerate() == SAMPLE_RATE
        assert source.getcomptype() == "NONE"
        samples = array("h", source.readframes(source.getnframes()))
        if sys.byteorder != "little":
            samples.byteswap()
        return samples


def frequency(samples):
    # Measure the produced waveform, independently of the returned note labels.
    middle = samples[1000:-1000]  # Ignore fades.
    crossings = [i for i in range(1, len(middle)) if middle[i - 1] <= 0 < middle[i]]
    return (len(crossings) - 1) * SAMPLE_RATE / (crossings[-1] - crossings[0])


def test_five_notes_and_rest_in_input_order_with_sample_exact_timing():
    classes = (5, None, 1, 4, 2, 3, None)
    route = tuple(Cell(str(i), 51, 64 + i / 10) for i in range(len(classes)))
    track = build_track(route, classes)
    samples = pcm(track.wav)
    assert BPM == 120
    assert [slot.note for slot in track.intervals] == ["A4", None, "C4", "G4", "D4", "E4", None]
    assert [slot.cell_id for slot in track.intervals] == [str(i) for i in range(len(classes))]
    assert len(samples) == len(classes) * STEP_SAMPLES
    assert track.duration_s == len(classes) * STEP_SECONDS
    expected_hz = {1: 261.625565, 2: 293.664768, 3: 329.627557, 4: 391.995436, 5: 440.0}
    for i, value in enumerate(classes):
        slot = track.intervals[i]
        assert (slot.start_sample, slot.end_sample) == (i * STEP_SAMPLES, (i + 1) * STEP_SAMPLES)
        assert (slot.start_s, slot.end_s) == (i * 0.5, (i + 1) * 0.5)
        chunk = samples[slot.start_sample:slot.end_sample]
        assert chunk[0] == chunk[-1] == 0
        if value is None:
            assert set(chunk) == {0}
        else:
            assert frequency(chunk) == pytest.approx(expected_hz[value], abs=0.15)
            assert 0 < max(chunk) <= 8192


def test_both_seasons_share_route_duration_scale_and_silence():
    dataset = load_dataset(ROOT / "data" / "synthetic")
    tracks = [build_track(dataset.route, season.classes) for season in dataset.seasons]
    assert tracks[0].duration_s == tracks[1].duration_s == 6
    assert [(t.start_sample, t.end_sample) for t in tracks[0].intervals] == [(t.start_sample, t.end_sample) for t in tracks[1].intervals]
    seen = {}
    for season, track in zip(dataset.seasons, tracks, strict=True):
        samples = pcm(track.wav)
        for slot in track.intervals:
            chunk = samples[slot.start_sample:slot.end_sample]
            if slot.ndvi_class is None:
                assert not any(chunk)
            elif slot.ndvi_class in seen:
                assert chunk == seen[slot.ndvi_class]
            else:
                seen[slot.ndvi_class] = chunk
    assert sorted(seen) == [1, 2, 3, 4, 5]


def test_all_missing_cells_are_silence_with_full_duration():
    route = (Cell("a", 51, 64), Cell("b", 51, 65))
    track = build_track(route, (None, None))
    assert track.duration_s == 1
    assert not any(pcm(track.wav))


@pytest.mark.parametrize("route,classes", [([], []), ([Cell("a", 51, 64)], []), ([Cell("a", 51, 64)], [0]), ([Cell("a", 51, 64)], [True])])
def test_invalid_input_cannot_be_silently_truncated(route, classes):
    with pytest.raises(ValueError):
        build_track(tuple(route), tuple(classes))


def test_payload_uses_the_exact_exported_audio_and_timeline():
    dataset = load_dataset(ROOT / "data" / "synthetic")
    payload = player_payload(dataset)
    assert payload["is_test"]
    assert [note["name"] for note in payload["scale"]] == [note.name for note in SCALE]
    for season, item in zip(dataset.seasons, payload["seasons"], strict=True):
        track = build_track(dataset.route, season.classes)
        assert base64.b64decode(item["audio_src"].split(",", 1)[1]) == track.wav
        assert [slot["cell_id"] for slot in item["intervals"]] == [cell.cell_id for cell in dataset.route]
        assert item["intervals"][-1]["end_s"] == item["duration_s"] == 6
    assert player_payload(dataset)["revision"] == payload["revision"]


def test_export_cli_produces_comparable_wav_and_timing_files(tmp_path):
    subprocess.run([sys.executable, "-m", "steppe_jukebox.export", "--data-dir", str(ROOT / "data" / "synthetic"),
                    "--output-dir", str(tmp_path)], check=True, cwd=ROOT, capture_output=True)
    for name in ("spring", "summer"):
        samples = pcm((tmp_path / f"{name}.wav").read_bytes())
        with (tmp_path / f"{name}_timing.csv").open() as source:
            slots = list(csv.DictReader(source))
        assert len(slots) == 12
        assert int(slots[-1]["end_sample"]) == len(samples) == 12 * STEP_SAMPLES
        assert slots[5]["ndvi_class"] == slots[5]["note"] == ""
        assert slots[5]["start_s"] == "2.5"
        assert slots[5]["end_s"] == "3.0"
