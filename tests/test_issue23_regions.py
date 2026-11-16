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


def test_abai_diagonal_steps_do_not_reveal_corner_touching_cells():
    region = load_live_regions()['abai']
    config = display_grid(region.grid, region.route)
    for index, key in enumerate(config['point_keys']):
        revealed = {cell['key'] for cell in config['route_cells'] if cell['first_step'] == index}
        assert revealed == {key}


@pytest.mark.parametrize('key', ['kostanay', 'akmola', *NEW])
def test_custom_route_definition_reveals_only_the_current_cell(key):
    from steppe_jukebox.routing import route_definition, route_region
    region = load_live_regions()[key]
    grid = display_grid(region.grid, region.route)
    path = build_path(grid['cells'], [grid['point_keys'][0], grid['point_keys'][-1]])
    custom = route_region(region, grid['cells'], path)
    config = route_definition(custom, grid['cells'], path)['map_config']
    first = {entry['key']: entry['first_step'] for entry in config['route_cells']}
    for index, cell in enumerate(path):
        newly_visible = {key for key, step in first.items() if step == index}
        assert newly_visible in ({cell}, set())


@pytest.mark.parametrize('key', ['kostanay', 'akmola', *NEW])
def test_each_preset_step_reveals_at_most_its_own_cell(key):
    region = load_live_regions()[key]
    config = display_grid(region.grid, region.route)
    for index, cell in enumerate(config['point_keys']):
        revealed = {entry['key'] for entry in config['route_cells'] if entry['first_step'] == index}
        assert revealed in ({cell}, set())
