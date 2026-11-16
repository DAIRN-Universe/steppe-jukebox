"""Regional presets stay inside the same grid used for custom routes."""
import pytest
from steppe_jukebox.live import load_live_regions
from steppe_jukebox.nasa_grid import display_grid
from steppe_jukebox.routing import build_path

NEW = ['north-kazakhstan', 'pavlodar', 'west-kazakhstan', 'aktobe', 'karaganda', 'abai']

@pytest.mark.parametrize('key', NEW)
def test_preset_uses_connected_interior_cells(key):
    region = load_live_regions()[key]
    config = display_grid(region.grid, region.route)
    assert not config['hidden_route_points']
    cells = config['cells']
    keys = config['point_keys']
    assert all(build_path(cells, [a, b]) == [a, b] for a, b in zip(keys, keys[1:]))
    assert 1 <= len(region.landmarks) <= 5
    assert len(region.intervals(['2026-04-15'] * len(keys))) == len(keys)
    assert region.intervals(['2026-04-15'] * len(keys))[-1]['end_s'] == len(keys) * .5
    for count in range(1, 6):
        points = [keys[round(i * (len(keys) - 1) / max(1, count - 1))] for i in range(count)]
        assert build_path(cells, points)
