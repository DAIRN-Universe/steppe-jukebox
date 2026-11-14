import json
import shutil
from pathlib import Path

import pytest

from steppe_jukebox.data import DataError, load_dataset


SYNTHETIC = Path(__file__).resolve().parents[1] / "data" / "synthetic"


@pytest.fixture
def data_dir(tmp_path):
    shutil.copytree(SYNTHETIC, tmp_path / "data")
    return tmp_path / "data"


def test_loads_shared_route_and_both_seasons():
    dataset = load_dataset(SYNTHETIC)
    assert dataset.is_test
    assert [cell.cell_id for cell in dataset.route] == [f"cell-{i:02}" for i in range(1, 13)]
    assert [season.name for season in dataset.seasons] == ["Весна", "Лето"]
    assert dataset.seasons[0].classes == (1, 2, 3, 4, 5, None, 5, 4, 3, 2, 1, 3)
    assert dataset.seasons[1].classes == (3, 4, 5, 5, 4, None, 3, 2, 1, None, 4, 5)


@pytest.mark.parametrize("filename", ["spring.csv", "summer.csv"])
@pytest.mark.parametrize("mutation", ["reorder", "missing_row", "extra_row", "duplicate_id", "wrong_id"])
def test_rejects_misaligned_seasons(data_dir, filename, mutation):
    path = data_dir / filename
    lines = path.read_text().splitlines()
    if mutation == "reorder":
        lines[1], lines[2] = lines[2], lines[1]
    elif mutation == "missing_row":
        lines.pop(6)
    elif mutation == "extra_row":
        lines.append("extra,1")
    elif mutation == "duplicate_id":
        lines[2] = lines[1]
    else:
        lines[1] = "unknown,1"
    path.write_text("\n".join(lines) + "\n")
    with pytest.raises(DataError, match="ID|cell_id"):
        load_dataset(data_dir)


@pytest.mark.parametrize("value", ["0", "6", "-1", "1.0", "NaN", "null", "3,extra"])
def test_rejects_invalid_classes(data_dir, value):
    path = data_dir / "spring.csv"
    path.write_text(path.read_text().replace("cell-01,1", f"cell-01,{value}"))
    with pytest.raises(DataError):
        load_dataset(data_dir)


@pytest.mark.parametrize("coordinates", ["nan,64", "inf,64", "91,64", "51,-181", "north,64", ",64"])
def test_rejects_invalid_coordinates(data_dir, coordinates):
    path = data_dir / "route.csv"
    path.write_text(path.read_text().replace("51.60,64.00", coordinates))
    with pytest.raises(DataError, match="координаты"):
        load_dataset(data_dir)


@pytest.mark.parametrize("contents", ["cell_id,lon,lat\na,64,51\n", "cell_id,lat,lon\n", "cell_id,lat,lon\na,51,64\na,52,65\n"])
def test_rejects_invalid_route_structure(data_dir, contents):
    (data_dir / "route.csv").write_text(contents)
    with pytest.raises(DataError):
        load_dataset(data_dir)


def test_replacement_csv_and_metadata_need_no_code_changes(data_dir):
    (data_dir / "route.csv").write_text("cell_id,lat,lon\nnew-a,50,64\nnew-b,51,65\n", encoding="utf-8-sig")
    (data_dir / "spring.csv").write_text("cell_id,ndvi_class\nnew-a,5\nnew-b,\n")
    (data_dir / "summer.csv").write_text("cell_id,ndvi_class\nnew-a,\nnew-b,1\n")
    (data_dir / "metadata.json").write_text(json.dumps({"is_test": False, "seasons": {
        "spring": {"date": "2026-04-01", "source_url": "https://example.org/frame"},
    }}))
    dataset = load_dataset(data_dir)
    assert not dataset.is_test
    assert dataset.route[0].cell_id == "new-a"
    assert dataset.seasons[0].classes == (5, None)
    assert dataset.seasons[1].classes == (None, 1)
    assert dataset.seasons[0].date == "2026-04-01"


def test_missing_metadata_defaults_to_test_mode(data_dir):
    (data_dir / "metadata.json").unlink()
    assert load_dataset(data_dir).is_test


@pytest.mark.parametrize("metadata", [{"is_test": "false"}, {"seasons": []}, {"seasons": {"spring": {"source_url": "javascript:alert(1)"}}}])
def test_rejects_invalid_metadata(data_dir, metadata):
    (data_dir / "metadata.json").write_text(json.dumps(metadata))
    with pytest.raises(DataError, match="metadata.json"):
        load_dataset(data_dir)
