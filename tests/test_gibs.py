"""Deterministic cache, date, classification and overlay safety checks."""
import hashlib
import io
import json
import re
import struct
import threading
import time
from decimal import Decimal
from pathlib import Path
from urllib.error import URLError

import numpy as np
import pytest
from PIL import Image

from steppe_jukebox.gibs import (
    LAYERS, PALETTES, WATER_DATE, Palette, RegionGrid, TileCache, TileClient, TileKey,
    TileResult, overlays, pixel_coordinate, user_cache_directory,
)
from steppe_jukebox.data import Cell, load_route
from steppe_jukebox.nasa_job import MapJob
from steppe_jukebox.regions import load_boundary

ROOT = Path(__file__).resolve().parents[1]


def png(color, size=(512, 512)):
    output = io.BytesIO()
    Image.new('RGBA', size, color).save(output, format='PNG')
    return output.getvalue()


def result(layer='ndvi', color=(0, 0, 0, 0), status='ok', day='2026-04-15'):
    key = TileKey(layer, day, 16 if layer != 'temperature' else 8, 108 if layer != 'temperature' else 54)
    return TileResult(key, status, png(color) if status == 'ok' else None, {'actual_date': day})


def test_current_scale_covers_15_region_positions_not_just_route_tiles():
    grid = RegionGrid(load_boundary(ROOT / 'data/maps/kostanay.geojson'))
    assert grid.positions == ((15,107),(15,108),(15,109),(16,106),(16,107),(16,108),(16,109),
                              (17,106),(17,107),(17,108),(17,109),(17,110),(18,107),(18,108),(18,109))
    assert len({pixel_coordinate(cell.lat,cell.lon)[:2] for cell in load_route(ROOT/'data/real-test/noaa20-kostanay/route.csv')}) == 4


def test_disk_cache_survives_a_new_client_and_uses_full_matrix_identity(tmp_path):
    count = []
    def fetch(key):
        count.append(key)
        return png((169,137,110,255)), {'actual_date': key.date+'T00:00:00Z'}
    key = TileKey('ndvi','2026-04-15',16,108)
    a = TileClient(TileCache(tmp_path),fetch).fetch(key)
    bclient = TileClient(TileCache(tmp_path),lambda key: (_ for _ in ()).throw(AssertionError('network used')))
    b = bclient.fetch(key)
    assert not a.from_cache and b.from_cache and a.png == b.png
    assert bclient.network_requests == 0 and len(count) == 1
    assert '/EPSG4326/500m/7/16/108' in key.identity
    assert TileCache(tmp_path).get(TileKey('ndvi','2026-01-15',16,108)) is None
    assert TileCache(tmp_path).get(TileKey('snow','2026-04-15',16,108)) is None
    assert TileKey('water',WATER_DATE,16,108).identity != key.identity


@pytest.mark.parametrize('bad', ['wrong_date','missing_date','corrupt_image','wrong_size','network'])
def test_failures_are_not_cached_or_treated_as_transparent(tmp_path,bad):
    key=TileKey('ndvi','2026-04-15',16,108)
    def fetch(key):
        if bad=='network':raise URLError('offline')
        return (b'not PNG' if bad=='corrupt_image' else png((0,0,0,0),(10,10) if bad=='wrong_size' else (512,512))), {'actual_date': '2026-01-15' if bad=='wrong_date' else '' if bad=='missing_date' else key.date}
    client=TileClient(TileCache(tmp_path),fetch)
    actual=client.fetch(key)
    assert actual.status == ('request_error' if bad=='network' else 'date_mismatch' if bad in {'wrong_date','missing_date'} else 'invalid_image')
    assert actual.png is None and not actual.from_cache
    assert TileCache(tmp_path).get(key) is None
    assert not list(tmp_path.glob('*.json'))


@pytest.mark.parametrize('corruption',['png','png_checksum','metadata_date','metadata_identity','missing_png'])
def test_corrupt_cache_entries_force_a_new_request(tmp_path,corruption):
    key=TileKey('ndvi','2026-04-15',16,108);raw=png((0,0,0,0));cache=TileCache(tmp_path)
    cache.put(TileResult(key,'ok',raw,{'actual_date':key.date}))
    manifest=cache._manifest(key);data=json.loads(manifest.read_text());blob=tmp_path/(data['sha256']+'.png')
    if corruption=='png':blob.write_bytes(b'broken')
    elif corruption=='png_checksum':
        broken=bytearray(raw);offset=8
        while offset<len(broken):
            size=struct.unpack('>I',broken[offset:offset+4])[0]
            if broken[offset+4:offset+8]==b'IDAT':
                broken[offset+8+size]^=1
                break
            offset+=12+size
        broken_digest=hashlib.sha256(broken).hexdigest()
        (tmp_path/(broken_digest+'.png')).write_bytes(broken)
        data['sha256']=broken_digest;manifest.write_text(json.dumps(data))
    elif corruption=='missing_png':blob.unlink()
    else:
        data['actual_date' if corruption=='metadata_date' else 'identity']='wrong';manifest.write_text(json.dumps(data))
    client=TileClient(cache,lambda k:(raw,{'actual_date':k.date}))
    loaded=client.fetch(key)
    assert loaded.status=='ok' and not loaded.from_cache and client.network_requests==1


def test_clearing_user_cache_does_not_touch_saved_routes(tmp_path):
    cache=TileCache(tmp_path);before=hashlib.sha256((ROOT/'data/real-test/noaa20-kostanay/spring.csv').read_bytes()).hexdigest()
    key=TileKey('ndvi','2026-04-15',16,108);cache.put(result())
    assert cache.get(key) is not None
    assert cache.clear()==2 and cache.get(key) is None
    assert hashlib.sha256((ROOT/'data/real-test/noaa20-kostanay/spring.csv').read_bytes()).hexdigest()==before


def test_default_cache_uses_xdg_outside_the_project(tmp_path,monkeypatch):
    monkeypatch.setenv('XDG_CACHE_HOME',str(tmp_path))
    assert user_cache_directory()==tmp_path/'steppe-jukebox/nasa-gibs'
    assert not user_cache_directory().is_relative_to(ROOT)


@pytest.mark.parametrize('color,state',[( (0,0,0,0),'transparent'),((169,137,110,128),'partial_alpha'),((1,2,3,255),'unknown_color'),((169,137,110,255),'classified')])
def test_ndvi_pixel_states_are_distinct(color,state):
    value=Palette(PALETTES/'ndvi.xml').ndvi(color)
    assert value['status']==state
    if state!='classified':assert value['ndvi_class'] is None
    else:assert value['ndvi_class']==2


def test_temperature_whole_interval_threshold_not_midpoint():
    palette=Palette(PALETTES/'temperature.xml')
    ambiguous=[rgb for rgb,rows in palette.entries.items() if any(row['numbers']==(Decimal('273.80'),Decimal('274.40')) for row in rows)]
    assert ambiguous
    assert palette.temperature((*ambiguous[0],255))['status']=='temperature_ambiguous'
    assert palette.temperature((*ambiguous[0],255))['interval_c']==[['0.65','1.25']]


@pytest.mark.parametrize('ndvi_status',['request_error','date_mismatch','invalid_image'])
def test_request_failure_never_becomes_snow_or_water(ndvi_status):
    output=overlays(result(status=ndvi_status),np.ones((512,512),bool),result('snow',(255,255,255,255)),water=result('water',(168,248,255,255),day=WATER_DATE))
    assert output['snow_png'] is None and output['water_png'] is None
    assert output['counts']['snow']==output['counts']['water']==0


@pytest.mark.parametrize('color',[(169,137,110,255),(1,2,3,255),(0,0,0,128)])
def test_opaque_or_partial_ndvi_never_receives_snow_or_water(color):
    snow_color=next(iter(Palette(PALETTES/'snow.xml').snow_colors()))
    output=overlays(result(color=color),np.ones((512,512),bool),result('snow',(*snow_color,255)),water=result('water',(168,248,255,255),day=WATER_DATE))
    assert output['counts']['snow']==output['counts']['water']==0
    assert not np.array(Image.open(io.BytesIO(output['snow_png'])))[:,:,3].any()


def test_snow_stays_white_with_warm_ambiguous_missing_or_failed_temperature():
    palettes={key:Palette(PALETTES/(key+'.xml')) for key in LAYERS}
    snow_color=next(iter(palettes['snow'].snow_colors()))
    for state,colors in palettes['temperature'].temperature_colors().items():
        color=next(iter(colors));output=overlays(result(),np.ones((512,512),bool),result('snow',(*snow_color,255)),result('temperature',(*color,255)),palettes=palettes)
        assert output['counts']['snow']==512*512
        assert output['counts'][state]==512*512
        assert np.all(np.array(Image.open(io.BytesIO(output['snow_png'])))==255)
    for temperature in [None,result('temperature',status='request_error')]:
        output=overlays(result(),np.ones((512,512),bool),result('snow',(*snow_color,255)),temperature,palettes=palettes)
        assert output['counts']['snow']==output['counts']['temperature_unknown']==512*512


def test_cold_alone_does_not_create_snow_and_date_mismatch_is_not_snow():
    palettes={key:Palette(PALETTES/(key+'.xml')) for key in LAYERS}
    cold=next(iter(palettes['temperature'].temperature_colors()['temperature_cold']))
    snow_color=next(iter(palettes['snow'].snow_colors()))
    for snow in [None,result('snow',status='request_error'),result('snow',(*snow_color,255),day='2026-01-15')]:
        output=overlays(result(),np.ones((512,512),bool),snow,result('temperature',(*cold,255)),palettes=palettes)
        assert output['counts']['snow']==0


def test_polygon_holes_are_preserved_in_native_pixel_mask():
    geometry={'type':'Polygon','coordinates':[[[60,50],[64,50],[64,54],[60,54],[60,50]],[[61,51],[63,51],[63,53],[61,53],[61,51]]]}
    grid=RegionGrid(geometry)
    r,c,y,x=pixel_coordinate(52,62)
    assert not grid.tile_mask(r,c)[y,x]
    r,c,y,x=pixel_coordinate(50.5,60.5)
    assert grid.tile_mask(r,c)[y,x]


def test_bounded_parallel_fetch_publishes_partial_results_before_all(tmp_path):
    grid=RegionGrid(load_boundary(ROOT/'data/maps/kostanay.geojson'))
    active=peak=0;lock=threading.Lock();release=threading.Event();raw=png((169,137,110,255))
    def fetch(key):
        nonlocal active,peak
        with lock:active+=1;peak=max(peak,active)
        if key.col==107 and key.row==15:time.sleep(.02)
        else:release.wait(3)
        with lock:active-=1
        return raw,{'actual_date':key.date}
    job=MapJob('parallel','2026-04-15',grid,(Cell('test',53,64),),client=TileClient(TileCache(tmp_path),fetch),workers=4).start()
    deadline=time.monotonic()+2
    while not job.results and time.monotonic()<deadline:time.sleep(.01)
    try:
        assert 0<len(job.results)<15 and not job.done
        assert peak<=4
    finally:release.set();job.thread.join(5)
    assert job.done and len(job.results)==15 and peak<=4


def test_nasa_locale_keys_match_and_have_consistent_interpolation():
    catalogs=json.loads((ROOT/'steppe_jukebox/frontend/locales.json').read_text())
    for language,catalog in catalogs.items():
        assert catalog.keys()==catalogs['en'].keys(),language
        for key,value in catalog.items():
            assert value
            if not isinstance(value,str):
                assert isinstance(value,list) and len(value)==len(catalogs['en'][key])
                continue
            assert set(re.findall(r'\{(\w+)\}',value))==set(re.findall(r'\{(\w+)\}',catalogs['en'][key]))


def test_cancelled_request_does_not_repopulate_cleared_cache(tmp_path):
    release=threading.Event();entered=threading.Event();cancel=threading.Event()
    key=TileKey('ndvi','2026-04-15',16,108);raw=png((0,0,0,0))
    def fetch(key):
        entered.set();release.wait(2)
        return raw,{'actual_date':key.date}
    client=TileClient(TileCache(tmp_path),fetch)
    thread=threading.Thread(target=lambda:client.fetch(key,False,cancel));thread.start()
    assert entered.wait(1)
    cancel.set();client.cache.clear();release.set();thread.join(3)
    assert client.cache.get(key) is None
