"""Geographic source integrity and region isolation before UI delivery."""

import hashlib
import io
import json
import wave
from datetime import date, timedelta
from pathlib import Path

import pytest

from steppe_jukebox.data import DataError, load_dataset, load_journey, load_route
from steppe_jukebox.player import regions_payload
from steppe_jukebox.regions import load_boundary, load_regions
from steppe_jukebox.sound import STEP_SAMPLES, build_track


ROOT = Path(__file__).resolve().parents[1]
AKMOLA = ROOT / "data/real-test/noaa20-akmola"


def test_geographic_boundaries_match_source_bytes_and_use_lon_lat():
    provenance = json.loads((ROOT / "data/maps/provenance.json").read_text())
    for key, source in provenance.items():
        path = ROOT / f"data/maps/{key}.geojson"
        assert hashlib.sha256(path.read_bytes()).hexdigest() == source["sha256"]
        assert source["source_url"].startswith("https://www.openstreetmap.org/relation/")
        assert source["license"] == "ODbL-1.0"
        geometry = load_boundary(path)
        assert geometry["type"] == "Polygon"
        points = [point for ring in geometry["coordinates"] for point in ring]
        assert all(59 < lon < 76 and 48 < lat < 55 for lon, lat in points)
    # Akmola includes internal rings: preserve them instead of painting over holes.
    assert len(load_boundary(ROOT / "data/maps/akmola.geojson")["coordinates"]) > 1


@pytest.mark.parametrize("geometry", [
    {"type": "Polygon", "coordinates": []},
    {"type": "Polygon", "coordinates": [[[60, 50], [61, 51], [62, 50], [60, 51]]]},
    {"type": "Polygon", "coordinates": [[[600, 500], [610, 510], [620, 500], [600, 500]]]},
    {"type": "Polygon", "coordinates": [[[60, 50], [61, float('nan')], [62, 50], [60, 50]]]},
    {"type": "LineString", "coordinates": [[60, 50], [61, 51]]},
    {"type": "FeatureCollection", "features": []},
    {"type": "FeatureCollection", "features": [{}, {}]},
    None,
])
def test_boundary_rejects_svg_coordinates_unclosed_rings_and_non_polygons(tmp_path, geometry):
    path = tmp_path / "region.geojson"
    path.write_text(json.dumps(geometry))
    with pytest.raises(DataError) as error:
        load_boundary(path)
    assert error.value.code == "boundary"


def test_catalog_keeps_map_route_dates_and_audio_in_one_region():
    regions = load_regions(ROOT / "data/regions.json")
    payload = regions_payload(regions)
    assert [region.key for region in regions][:2] == ["kostanay", "akmola"]
    assert [len(region.dataset.route) for region in regions[:2]] == [48, 56]
    assert len(payload["regions"]) == len(regions)
    assert set(payload["translations"]) == {"ru", "kk", "en"}
    for region, item in zip(regions, payload["regions"], strict=True):
        assert item["region_key"] == region.key
        assert item["boundary"] == region.boundary
        assert item["map_source_url"] == region.source_url
        assert [cell["cell_id"] for cell in item["route"]] == [cell.cell_id for cell in region.dataset.route]
        for track in [*item["seasons"], item["journey"]]:
            if track is not None:
                assert [slot["cell_id"] for slot in track["intervals"]] == [cell["cell_id"] for cell in item["route"]]
                assert track["duration_s"] == len(item["route"]) * .5


def test_akmola_issue_11_dates_samples_and_missing_interval_are_preserved():
    provenance = json.loads((AKMOLA / "journey_provenance.json").read_text())
    for name in ["route", "journey"]:
        assert hashlib.sha256((AKMOLA / f"{name}.csv").read_bytes()).hexdigest() == provenance[f"{name}_csv_sha256"]
    route = load_route(AKMOLA / "route.csv")
    journey = load_journey(AKMOLA, route)
    assert len(route) == len(journey.steps) == 56
    assert [step.date for step in journey.steps] == [(date(2026, 4, 15) + timedelta(days=round(i * 212 / 55))).isoformat() for i in range(56)]
    assert [i for i, step in enumerate(journey.steps) if step.ndvi_class is None] == [26]
    assert journey.steps[26].cell_id == "AKM-027"
    assert journey.steps[26].date == "2026-07-24"
    assert dict(journey.landmarks) == {"AKM-001": "atbasar", "AKM-019": "kokshetau", "AKM-029": "burabay", "AKM-056": "buyratau"}
    track = build_track(route, tuple(step.ndvi_class for step in journey.steps))
    assert track.duration_s == 28
    assert (track.intervals[26].start_s, track.intervals[26].end_s) == (13, 13.5)
    with wave.open(io.BytesIO(track.wav)) as wav:
        assert wav.getnframes() == 56 * STEP_SAMPLES
        for slot in track.intervals:
            wav.setpos(slot.start_sample)
            pcm = wav.readframes(STEP_SAMPLES)
            assert bool(any(pcm)) == (slot.ndvi_class is not None)


def test_received_archive_files_and_reference_audio_are_exact():
    provenance = json.loads((AKMOLA / "journey_provenance.json").read_text())
    assert provenance["source_comment"].endswith("/issues/13#issuecomment-6876016651")
    for name, source in provenance["imported_files"].items():
        assert hashlib.sha256((AKMOLA / name).read_bytes()).hexdigest() == source["sha256"], name
    dataset = load_dataset(AKMOLA)
    assert not dataset.is_test
    assert set(dict(dataset.description_i18n)) == {"ru", "kk", "en"}
    reference = provenance["reference_wav"]
    track = build_track(dataset.route, tuple(step.ndvi_class for step in dataset.journey.steps))
    assert hashlib.sha256(track.wav).hexdigest() == reference["sha256"]
    with wave.open(io.BytesIO(track.wav)) as wav:
        pcm = wav.readframes(wav.getnframes())
        assert wav.getnframes() == reference["frames"]
    assert hashlib.sha256(pcm).hexdigest() == reference["pcm_sha256"]
    metadata = json.loads((AKMOLA / "metadata.json").read_text())
    assert hashlib.sha256((AKMOLA / "route.csv").read_bytes()).hexdigest() == metadata["route_sha256"]
    assert hashlib.sha256((AKMOLA / "palette.xml").read_bytes()).hexdigest() == metadata["palette_sha256"]
    prototype = json.loads((AKMOLA / "prototype-route.json").read_text())
    materials = json.loads((ROOT / "docs/ISSUE_13_MATERIALS.json").read_text())
    assert prototype["source_sha256"] == materials["prototype"]["sha256"]
    assert not materials["missing_archives"]
    assert len(materials["archives"]) == 3


@pytest.mark.parametrize("index,date_value,missing", [
    (0, "2026-04-15", ["AKM-005", "AKM-027"]),
    (1, "2026-07-16", ["AKM-027"]),
])
def test_akmola_fixed_slices_keep_dates_note_order_and_full_rests(index, date_value, missing):
    dataset = load_dataset(AKMOLA)
    season = dataset.seasons[index]
    assert season.date == date_value
    assert "t=" + date_value in season.source_url
    track = build_track(dataset.route, season.classes)
    assert track.duration_s == 28
    assert [slot.cell_id for slot in track.intervals if slot.ndvi_class is None] == missing
    with wave.open(io.BytesIO(track.wav)) as wav:
        for i, slot in enumerate(track.intervals):
            assert slot.cell_id == dataset.route[i].cell_id
            assert (slot.start_s, slot.end_s) == (i * .5, (i + 1) * .5)
            wav.setpos(slot.start_sample)
            assert bool(any(wav.readframes(STEP_SAMPLES))) == (slot.ndvi_class is not None)


def test_recorded_gibs_dates_and_audits_match_imported_journey():
    import csv

    dataset = load_dataset(AKMOLA)
    with (AKMOLA / "journey-audit.csv").open(newline="") as source:
        rows = list(csv.DictReader(source))
    assert len(rows) == 56
    for row, step, cell in zip(rows, dataset.journey.steps, dataset.route, strict=True):
        assert (row["cell_id"], row["date"], row["ndvi_class"]) == (step.cell_id, step.date, str(step.ndvi_class or ""))
        assert (float(row["lat"]), float(row["lon"])) == (cell.lat, cell.lon)
        assert row["status"] == ("transparent" if step.ndvi_class is None else "classified")
    provenance = json.loads((AKMOLA / "journey-provenance.json").read_text())
    assert len(provenance) == 56
    for item in provenance.values():
        assert item["actual_date"][:10] == item["requested_date"]
    fixed = json.loads((AKMOLA / "tile-provenance.json").read_text())
    assert len(fixed) == 10
    for item in fixed.values():
        headers = item["headers"]
        assert headers["layer-time-actual"][:10] == headers["layer-time-request"]
