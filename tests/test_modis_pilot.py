import importlib.util
from pathlib import Path
import pytest
from steppe_jukebox.data import Cell

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

def test_rejects_changed_sample_coordinates_even_with_same_pixel():
    cell = Cell('KST-001', 53.29027778, 63.77583333)
    sample = {'Latitude': str(cell.lat), 'Longitude': str(cell.lon), 'MODIS_Tile': 'h21v03',
              'MOD13Q1_061_Line_Y_250m': '3220.0', 'MOD13Q1_061_Sample_X_250m': '3898.0'}
    assert pilot.validate_sample_location(sample, cell) == ('h21v03', 3220, 3898)
    sample['Latitude'] = str(cell.lat + .000001)
    assert pilot.pixel(float(sample['Latitude']), cell.lon) == pilot.pixel(cell.lat, cell.lon)
    with pytest.raises(ValueError, match='Sample coordinates do not match'):
        pilot.validate_sample_location(sample, cell)
