import json
import re
from pathlib import Path

import pytest

from steppe_jukebox.data import DataError, load_dataset
from steppe_jukebox.player import error_payload, player_payload


ROOT = Path(__file__).resolve().parents[1]


def test_catalogs_have_matching_keys_and_interpolation_fields():
    catalogs = json.loads((ROOT / "steppe_jukebox/frontend/locales.json").read_text())
    assert set(catalogs) == {"kk", "en", "ru"}
    reference = catalogs["en"]
    for locale, catalog in catalogs.items():
        assert catalog.keys() == reference.keys(), locale
        for key, value in catalog.items():
            assert value, (locale, key)
            if key == "note_names":
                assert len(value) == 5 and all(isinstance(note, str) and note for note in value)
            else:
                assert isinstance(value, str)
                assert set(re.findall(r"\{(\w+)\}", value)) == set(re.findall(r"\{(\w+)\}", reference[key])), (locale, key)


def test_test_dataset_description_has_all_three_translations():
    dataset = load_dataset(ROOT / "data/synthetic")
    payload = player_payload(dataset)
    assert set(payload["description_i18n"]) == {"kk", "en", "ru"}
    assert payload["description_i18n"]["ru"] == dataset.description


def test_structured_error_payload_does_not_embed_russian_ui_text(tmp_path):
    (tmp_path / "route.csv").write_text("wrong,header\n")
    with pytest.raises(DataError) as failure:
        load_dataset(tmp_path)
    payload = error_payload(failure.value)
    assert payload["error"] == {"code": "headers", "context": {"file": "route.csv", "columns": "cell_id,lat,lon"}}
    assert "expected header" in payload["translations"]["en"]["error_headers"]
    assert "күтілетін тақырып" in payload["translations"]["kk"]["error_headers"]
