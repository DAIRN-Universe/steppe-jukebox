"""Interior-grid routing without a water mask, and the existing audio loaders."""
import base64
import io
from pathlib import Path

from PIL import Image
import pytest

from steppe_jukebox.gibs import TileCache, TileClient, PALETTES, Palette
from steppe_jukebox.live import LiveJob, load_live_regions
from steppe_jukebox.routing import RouteError, build_path, route_region, route_definition
from steppe_jukebox.nasa_grid import display_grid
from steppe_jukebox.sound import build_track


def cells(rows=5, cols=5):
    return [{'key':f'{r}/{c}', 'row':r,'col':c,'bounds':[c,10-r-1,c+1,10-r]}
            for r in range(rows) for c in range(cols)]


def test_one_cell_waypoint_order_and_return_visits_without_water_restrictions():
    grid=cells()
    assert build_path(grid,['2/1'])==['2/1']
    # These cells were previously water/unknown. Neither classification is needed.
    assert build_path(grid,['2/1','2/3','2/1'])==['2/1','2/2','2/3','2/2','2/1']
    assert build_path(grid,['1/1','1/1','1/2'])==['1/1','1/2']


def test_diagonal_never_cuts_a_boundary_corner():
    grid=[c for c in cells(2,2) if c['key'] not in ['0/1','1/0']]
    with pytest.raises(RouteError,match='no_path'):build_path(grid,['0/0','1/1'])


@pytest.mark.parametrize('points,code', [([], 'points_limit'),(['0/0']*6,'points_limit'),
    (['99/99'],'outside'),([{'row':0}],'outside')])
def test_server_rejects_invalid_waypoints(points,code):
    with pytest.raises(RouteError) as error:build_path(cells(2,2),points)
    assert error.value.code==code


def test_geometry_ids_and_original_presets_are_unchanged_and_revisits_survive():
    for base in load_live_regions().values():
        grid=display_grid(base.grid,base.route)['cells'];a,b=grid[:2]
        custom=route_region(base,grid,[a['key'],b['key'],a['key']])
        assert len({c.cell_id for c in custom.route})==3
        assert custom.route[0].lat==custom.route[-1].lat
        assert custom.route[0].lon==custom.route[-1].lon
        if base.key in {'kostanay', 'akmola'}:
            assert len(base.route)==(48 if base.key=='kostanay' else 56)
        definition=route_definition(custom,grid,[a['key'],b['key'],a['key']])
        assert definition['map_config']['point_keys']==[a['key'],b['key'],a['key']]
        assert len(definition['intervals'])==3


@pytest.mark.parametrize('provider',['gibs','eic'])
def test_custom_geometry_uses_existing_audio_loader_order_and_exact_date(tmp_path,provider):
    from steppe_jukebox.eic import EicPalette, FrameClient, BASE, frame_name
    base=load_live_regions()['kostanay'];grid=display_grid(base.grid,())['cells']
    custom=route_region(base,grid,[grid[0]['key'],grid[1]['key'],grid[0]['key']])
    if provider=='gibs':
        palette=Palette(PALETTES/'ndvi.xml');color=next(c for c in palette.entries if palette.ndvi((*c,255)).get('ndvi_class')==2)
        stream=io.BytesIO();Image.new('RGBA',(512,512),(*color,255)).save(stream,format='PNG')
        gibs=TileClient(TileCache(tmp_path),lambda key:(stream.getvalue(),{'actual_date':key.date}));options={'gibs':gibs}
    else:
        palette=EicPalette();color=tuple(map(int,palette.ramp[int(len(palette.ramp)*.3)]))
        stream=io.BytesIO();Image.new('RGB',(8640,4320),color).save(stream,format='PNG')
        eic=FrameClient(tmp_path,lambda url:frame_name('2026-04-20').encode() if url==BASE else stream.getvalue());options={'eic':eic}
    job=LiveJob('custom',custom,provider,'fixed','2026-04-20',**options).start();job.thread.join(20)
    result=job.payload();assert result['state']=='ready',getattr(job,'detail',None)
    assert [s['cell_id'] for s in result['track']['intervals']]==[c.cell_id for c in custom.route]
    assert {s['date'] for s in result['track']['intervals']}=={'2026-04-20'}
    assert result['track']['duration_s']==1.5
    assert base64.b64decode(result['track']['audio_src'].split(',')[1])==build_track(custom.route,(2,)*3).wav


@pytest.mark.parametrize('region_key',['kostanay','akmola'])
def test_formerly_blocked_water_cells_are_usable_without_any_mask(region_key):
    import json
    root=Path(__file__).resolve().parents[1]/'data/route-fixtures'
    example=json.loads((root/f'{region_key}-detour.json').read_text())
    grid=display_grid(load_live_regions()[region_key].grid,())['cells']
    path=build_path(grid,example['waypoints'])
    assert path==[f"{example['waypoints'][0].split('/')[0]}/{col}" for col in
                  range(int(example['waypoints'][0].split('/')[1]),int(example['waypoints'][1].split('/')[1])+1)]
    assert any(key in path for key,state in example['blocked'].items() if state=='water')
