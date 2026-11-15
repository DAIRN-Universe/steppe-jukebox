"""Focused integration checks with source-shaped PNGs and all external sockets blocked."""
import os
import textwrap
from pathlib import Path

import pytest
from PIL import Image
from playwright.sync_api import expect

from test_browser import ROOT, browser, running_app, player_frame
from steppe_jukebox.eic import EicPalette
from steppe_jukebox.gibs import PALETTES, Palette

pytestmark = pytest.mark.browser


def transport(tmp_path, monkeypatch):
    folder=tmp_path/'transport';folder.mkdir()
    palette=EicPalette()
    for day,fraction in [('20260420',.3),('20260610',.7)]:
        color=tuple(map(int,palette.ramp[int(len(palette.ramp)*fraction)]))
        Image.new('RGB',(8640,4320),color).save(folder/(day+'.png'))
    gibs=Palette(PALETTES/'ndvi.xml')
    for value in [2,4]:
        color=next(c for c in gibs.entries if gibs.ndvi((*c,255)).get('ndvi_class')==value)
        Image.new('RGBA',(512,512),(*color,255)).save(folder/(str(value)+'.png'))
    Image.new('RGBA',(512,512),(122,87,6,0)).save(folder/'mask.png')
    (folder/'sitecustomize.py').write_text(textwrap.dedent('''
        import io,os,socket
        from pathlib import Path
        from urllib.error import URLError
        from urllib.parse import urlsplit
        import urllib.request
        folder=Path(os.environ['STEPPE_LIVE_FIXTURE']);original=urllib.request.urlopen
        class Response:
            status=200
            def __init__(self,raw,url,day):self.body=io.BytesIO(raw);self.url=url;self.headers={'layer-time-actual':day+'T00:00:00Z'}
            def read(self,n=-1):return self.body.read(n)
            def geturl(self):return self.url
            def __enter__(self):return self
            def __exit__(self,*a):self.body.close()
        def opened(request,*args,**kwargs):
            url=request.full_url if hasattr(request,'full_url') else str(request)
            if urlsplit(url).hostname in {'127.0.0.1','localhost','::1'}:return original(request,*args,**kwargs)
            with (folder/'requests.log').open('a') as out:out.write(url+'\\n')
            if (folder/'offline').exists():raise URLError('offline fixture')
            if 'gibs.earthdata.nasa.gov' in url:
                if 'MODIS_Terra_L3_Land_Water_Mask' in url:
                    if (folder/'mask-offline').exists():raise URLError('mask unavailable')
                    return Response((folder/'mask.png').read_bytes(),url,'2015-01-01')
                day=url.split('/')[8]
                actual='2026-01-15' if (folder/'wrong-date').exists() else day
                return Response((folder/('2.png' if day=='2026-04-20' else '4.png')).read_bytes(),url,actual)
            if url.endswith('/equirectangular/'):
                return Response(b'SNPP_VIIRS.20260420.ndvi_w_snow.oceanblue.png SNPP_VIIRS.20260610.ndvi_w_snow.oceanblue.png',url,'')
            if 'SNPP_VIIRS.' in url:
                day=url.rsplit('/',1)[-1].split('.')[1]
                return Response((folder/(day+'.png')).read_bytes(),url,day)
            raise URLError('Unsupported external URL')
        urllib.request.urlopen=opened
        connect=socket.socket.connect
        def guarded(self,address):
            if isinstance(address,tuple) and address[0] not in {'localhost','127.0.0.1','::1'}:raise OSError('External network blocked')
            return connect(self,address)
        socket.socket.connect=guarded
        # Two real-shaped dates exercise step-date switching without downloading
        # a whole year; unchanged v0.3.0 scenarios have their own fixture tests.
        from dataclasses import replace
        import steppe_jukebox.live as live
        original_regions=live.load_live_regions
        def regions():
            return {k:replace(r,dates=tuple('2026-04-20' if i<len(r.route)//2 else '2026-06-10' for i in range(len(r.route)))) for k,r in original_regions().items()}
        live.load_live_regions=regions
    '''))
    monkeypatch.setenv('PYTHONPATH',str(folder)+os.pathsep+str(ROOT))
    monkeypatch.setenv('STEPPE_LIVE_FIXTURE',str(folder))
    monkeypatch.setenv('XDG_CACHE_HOME',str(tmp_path/'cache'))
    return folder


def ui(browser,url,locale='ru-RU'):
    ctx=browser.new_context(locale=locale,viewport={'width':1440,'height':1000})
    ctx.route('**/*',lambda r:r.continue_() if r.request.url.startswith(('http://127.0.0.1:','data:')) else r.abort())
    page=ctx.new_page();page.goto(url);frame=player_frame(page)
    expect(frame.locator('#provider')).to_be_visible()
    return ctx,page,frame


def load(frame):
    previous=frame.evaluate('steppeLive.active')
    frame.locator('#load-data').press('Enter')
    frame.wait_for_function('''previous=>!steppeLive.buildId&&!steppeLive.loading&&
        (steppeLive.routeError||(steppeLive.active!==previous&&
        (steppeLive.ready||steppeLive.request?.state==="error")))''',arg=previous,timeout=45000)


def test_shared_player_source_date_region_mode_and_offline_cache(browser,tmp_path,monkeypatch):
    folder=transport(tmp_path,monkeypatch)
    with running_app(None,tmp_path/'server.log',live=True) as url:
        ctx,page,f=ui(browser,url)
        assert page.locator('iframe').count()==1 and f.locator('audio').count()==1
        assert not (folder/'requests.log').exists()
        expect(f.locator('#season-field')).not_to_be_visible()
        load(f);expect(f.locator('#toggle')).to_be_enabled()
        assert f.evaluate('steppeLive.request.source')=='gibs'
        assert f.evaluate('steppeLive.request.track.intervals[0].ndvi_class')==2
        f.locator('#toggle').press('Enter');f.wait_for_function('document.querySelector("audio").currentTime>.15')
        f.locator('#provider').select_option('eic')
        assert f.evaluate('document.querySelector("audio").paused')
        expect(f.locator('#toggle')).to_be_disabled()
        load(f);expect(f.locator('#toggle')).to_be_enabled()
        expect(f.locator('#eic-date')).to_be_visible()
        assert f.evaluate('steppeLive.request.source')=='eic'
        f.locator('#eic-date').select_option('2026-06-10')
        expect(f.locator('#toggle')).to_be_disabled();load(f)
        assert f.evaluate('steppeLive.request.track.intervals[0].ndvi_class')==4
        f.locator('#region').select_option('akmola');expect(f.locator('#toggle')).to_be_disabled();load(f)
        assert f.evaluate('steppeLive.request.track.intervals.length')==56
        assert f.evaluate('steppeLive.request.track.duration_s')==28
        expect(f.locator('#mode-field')).not_to_be_visible()
        assert f.evaluate('steppeLive.request.mode')=='fixed'
        f.locator('#toggle').press('Enter');f.wait_for_function('document.querySelector("audio").currentTime>.1')
        f.evaluate('document.querySelector("audio").currentTime=14.2')
        f.wait_for_function('document.querySelector("#step-date").textContent==="2026-06-10"')
        assert f.evaluate('steppeLive.maps.get("2026-06-10").source')=='eic'
        f.evaluate('document.querySelector("audio").currentTime=27.9')
        f.wait_for_function('document.querySelector("audio").ended')
        assert f.evaluate('steppeLive.hooks.currentDate()')=='2026-06-10'
        assert f.locator('#step-date').inner_text()=='2026-06-10'
        f.locator('#toggle').press('Enter');f.wait_for_function('document.querySelector("audio").currentTime>.1')
        f.locator('#toggle').press('Space');assert f.evaluate('document.querySelector("audio").paused')
        before=f.evaluate('document.querySelector("audio").currentTime');f.locator('#language').select_option('kk')
        assert f.evaluate('document.querySelector("audio").currentTime')==before
        (folder/'offline').touch()
        load(f)
        assert f.evaluate('steppeLive.request.network_requests')==0
        assert f.evaluate('steppeLive.ready')
        ctx.close()


def test_eic_unavailable_date_refresh_and_cache_clear(browser,tmp_path,monkeypatch):
    folder=transport(tmp_path,monkeypatch)
    with running_app(None,tmp_path/'catalog.log',live=True) as url:
        ctx,page,f=ui(browser,url)
        f.locator('#provider').select_option('eic');load(f)
        expect(f.locator('#toggle')).to_be_enabled()
        f.locator('#technical-details > summary').press('Enter')
        f.locator('#live-diagnostics summary').press('Enter')
        f.locator('#refresh-eic-dates').press('Enter')
        f.wait_for_function('window.steppeLive.inFlight===null')
        expect(f.locator('#catalog-error')).not_to_be_visible()
        f.locator('#clear-live-cache').press('Enter');f.wait_for_function('window.steppeLive.inFlight===null&&window.steppeLive.queue.length===0')
        expect(f.locator('#toggle')).to_be_disabled()
        f.locator('#observation-date').fill('2027-01-01');f.locator('#observation-date').press('Tab');load(f)
        assert f.evaluate('steppeLive.request.error')=='unavailable_dates'
        assert not f.evaluate('steppeLive.ready')
        assert f.locator('audio').get_attribute('src') is None
        f.locator('#eic-date').select_option('2026-06-10');load(f)
        assert f.evaluate('steppeLive.request.state')=='ready'
        assert f.evaluate('steppeLive.request.network_requests')==1  # catalog was cached by the failed-date check
        f.locator('[data-point-id="KST-006"]').focus();f.locator('[data-point-id="KST-006"]').press('Enter')
        expect(f.locator('#live-inspector')).to_be_visible()
        expect(f.locator('#live-pixel')).to_contain_text('KST-006')
        ctx.close()


def test_failed_requests_or_wrong_dates_never_fall_back_to_saved_audio(browser,tmp_path,monkeypatch):
    folder=transport(tmp_path,monkeypatch);(folder/'wrong-date').touch()
    with running_app(None,tmp_path/'errors.log',live=True) as url:
        ctx,page,f=ui(browser,url);load(f)
        assert f.evaluate('steppeLive.request.error')=='route_data_error'
        expect(f.locator('#toggle')).to_be_disabled()
        expect(f.locator('#progress')).to_be_disabled()
        expect(f.locator('#point-note')).to_have_text('—')
        assert f.locator('audio').get_attribute('src') is None
        assert f.locator('#load-state').get_attribute('data-error')=='true'
        ctx.close()


@pytest.mark.parametrize('language,locale',[('ru','ru-RU'),('kk','kk-KZ'),('en','en-GB')])
def test_shared_layout_and_navigation_keep_audio_on_three_languages(browser,tmp_path,monkeypatch,language,locale):
    transport(tmp_path,monkeypatch)
    with running_app(None,tmp_path/'layout.log',live=True) as url:
        ctx,page,f=ui(browser,url,locale)
        assert f.locator('html').get_attribute('lang')==language
        load(f);expect(f.locator('#toggle')).to_be_enabled()
        f.locator('#toggle').press('Enter');f.wait_for_function('document.querySelector("audio").currentTime>.1')
        f.locator('#tab-method').press('Enter');assert not f.evaluate('document.querySelector("audio").paused')
        f.locator('#tab-listen').press('Enter')
        for width in [1440,390,320]:
            page.set_viewport_size({'width':width,'height':1000})
            f.evaluate('()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)))')
            assert f.evaluate('document.documentElement.scrollWidth<=innerWidth')
        f.locator('#toggle').press('Space');assert f.evaluate('document.querySelector("audio").paused')
        ctx.close()
