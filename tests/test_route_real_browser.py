"""Opt-in acceptance against a prepared real NASA cache, without network access."""
import base64
import io
import json
import os
from pathlib import Path
import shutil
import wave

import numpy as np
import pytest
from playwright.sync_api import expect
from test_browser import ROOT, browser, running_app, media
from test_live_browser import ui, load
from test_route_browser import enable_points, remove_all, pick, open_points

pytestmark=[pytest.mark.browser,pytest.mark.skipif(not os.environ.get('STEPPE_REAL_CACHE'),reason='Prepared NASA cache required')]


def test_real_routes_without_water_mask_both_sources_and_control_rest(browser,tmp_path,monkeypatch):
    source=Path(os.environ['STEPPE_REAL_CACHE'])
    # Accept a parent containing nasa-gibs and nasa-eic; never mutate its files.
    target=tmp_path/'cache/steppe-jukebox';shutil.copytree(source,target)
    guard=tmp_path/'guard';guard.mkdir()
    (guard/'sitecustomize.py').write_text('''
from urllib.parse import urlsplit
import urllib.request
original=urllib.request.urlopen
def opened(request,*args,**kwargs):
    url=request.full_url if hasattr(request,'full_url') else str(request)
    if urlsplit(url).hostname not in {'localhost','127.0.0.1','::1'}:raise OSError('Offline acceptance')
    return original(request,*args,**kwargs)
urllib.request.urlopen=opened
''')
    monkeypatch.setenv('PYTHONPATH',str(guard)+os.pathsep+str(ROOT))
    monkeypatch.setenv('XDG_CACHE_HOME',str(tmp_path/'cache'))
    output=ROOT/'docs/media/map-zoom';output.mkdir(exist_ok=True)
    report=[]
    with running_app(None,tmp_path/'real.log',live=True) as url:
        ctx,page,f=ui(browser,url);page.set_viewport_size({'width':1280,'height':720})
        errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        expect(f.locator('#route-coordinate-list li')).to_have_count(3)
        page.screenshot(path=str(output/'initial-panel.png'),full_page=True)
        open_points(f)
        f.locator('#route-points').screenshot(path=str(output/'points-field.png'))
        # The release control remains a rest exactly at KST-006.
        f.locator('#observation-date').fill('2026-06-10');f.locator('#observation-date').press('Tab');load(f)
        request=f.evaluate('steppeLive.request');assert request['state']=='ready',request['error']
        assert request['network_requests']==0
        slot=request['track']['intervals'][5]
        assert slot['cell_id']=='KST-006' and slot['ndvi_class'] is None
        raw=base64.b64decode(request['track']['audio_src'].split(',')[1])
        with wave.open(io.BytesIO(raw)) as wav:
            rate=wav.getframerate();samples=np.frombuffer(wav.readframes(wav.getnframes()),dtype='<i2')
        assert not samples[int(2.5*rate):int(3*rate)].any()
        f.locator('#progress').press('Home')
        for _ in range(5):f.locator('#step-forward').click()
        expect(f.locator('#point-cell')).to_have_text('KST-006')
        page.screenshot(path=str(output/'preset-kst006.png'),full_page=True)
        for region in ['kostanay','akmola']:
            f.locator('#reset-route').click()
            f.locator('#region').select_option(region)
            example=json.loads((ROOT/f'data/route-fixtures/{region}-detour.json').read_text())
            enable_points(f);remove_all(f)
            from steppe_jukebox.live import load_live_regions
            from steppe_jukebox.nasa_grid import display_grid
            from steppe_jukebox.routing import build_path
            example['path']=build_path(display_grid(load_live_regions()[region].grid,())['cells'],example['waypoints'])
            for key in example['waypoints']:pick(f,key)
            for provider,day in [('gibs','2026-06-10'),('eic','2026-04-20')]:
                f.locator('#provider').select_option(provider)
                if f.locator('#eic-date').is_visible():f.locator('#eic-date').select_option(day)
                else:f.locator('#observation-date').fill(day);f.locator('#observation-date').press('Tab')
                load(f);request=f.evaluate('steppeLive.request')
                assert request['state']=='ready',request['error']
                assert request['network_requests']==0
                assert f.evaluate('steppeLive.map.config.point_keys')==example['path']
                assert {s['date'] for s in request['track']['intervals']}=={day}
                assert media(f)['paused']
                f.locator('#progress').press('Home');f.locator('#step-forward').click()
                f.locator('#step-forward').click()
                expect(f.locator('#point-cell')).to_have_text('USR-0003')
                assert f.evaluate('steppeLive.map.currentIndex')==2
                f.locator('#add-route-points').check()
                f.locator('#map-zoom-in').click()
                page.set_viewport_size({'width':1280,'height':1100})
                f.locator('#toggle').scroll_into_view_if_needed()
                page.screenshot(path=str(output/f'{region}-{provider}-detour.png'),full_page=True)
                open_points(f)
                f.locator('#route-points').screenshot(path=str(output/f'{region}-points-field.png'))
                report.append({'region':region,'source':provider,'date':day,'steps':len(example['path']),
                               'network_requests':request['network_requests'],'water_mask_used':False,
                               'waypoints':example['waypoints'],'path':example['path']})
        page.set_viewport_size({'width':320,'height':844})
        assert f.evaluate('document.documentElement.scrollWidth<=innerWidth')
        page.screenshot(path=str(output/'mobile-320.png'),full_page=True)
        assert not errors,errors
        (output/'real-checks.json').write_text(json.dumps({'control_rest':'KST-006: PCM zero at 2.5–3.0s',
            'cases':report,'javascript_errors':errors},ensure_ascii=False,indent=2)+'\n')
        ctx.close()
