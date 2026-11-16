import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('modis_pilot', ROOT / 'scripts/modis_pilot.py')
pilot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pilot)

def test_numeric_thresholds_and_missing():
    assert [pilot.classify(x, 0, 0) for x in (-.2, 0, .1999, .2, .4, .6, .8, 1)] == [1, 1, 1, 2, 3, 4, 5, 5]
    assert all(pilot.classify(x, reliability, qa) is None for x, reliability, qa in [(None, 0, 0), (-.3, 0, 0), (1.1, 0, 0), (.3, 1, 0), (.3, 0, 1), (.3, 0, 65535)])

def test_known_modis_pixels():
    assert pilot.pixel(53.29027778, 63.77583333) == ('h21v03', 3220, 3898)
    assert pilot.pixel(51.29081782, 64.17485737) == ('h22v03', 4180, 63)
    assert pilot.pixel(49.337222, 65.535833) == ('h22v04', 318, 1297)
