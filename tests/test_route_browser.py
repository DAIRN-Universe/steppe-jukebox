"""MVP route markers, compact fields, failure retention and the sole player."""
import pytest
from playwright.sync_api import expect
from test_browser import ROOT, browser, running_app, media
from test_live_browser import transport, ui, load

pytestmark=pytest.mark.browser


def open_points(frame):
    if not frame.locator('#route-points').evaluate('e=>e.open'):
        frame.locator('#route-points > summary').click()


def enable_points(frame):
    open_points(frame)
    frame.locator('#add-route-points').check()


def remove_all(frame):
    open_points(frame)
    while frame.locator('#route-coordinate-list button').count():
        frame.locator('#route-coordinate-list button').first.click()


def pick(frame,key):
    target=frame.locator(f'[data-pick-key="{key}"]')
    target.focus();target.press('Enter')


@pytest.mark.parametrize('provider',['gibs','eic'])
def test_initial_markers_five_point_limit_build_order_date_source_and_region(browser,tmp_path,monkeypatch,provider):
    transport(tmp_path,monkeypatch)
    with running_app(None,tmp_path/'routes.log',live=True) as url:
        ctx,page,f=ui(browser,url);errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        expect(f.locator('#mode-field')).not_to_be_visible()
        expect(f.locator('#route-coordinate-list li')).to_have_count(3)
        expect(f.locator('.route-waypoint')).to_have_count(3)
        expect(f.locator('#point-count')).to_have_text('48')
        expect(f.locator('#toggle')).to_be_disabled()
        assert f.locator('audio').get_attribute('src') is None
        expect(f.locator('.route-tile:not([hidden])')).to_have_count(0)
        f.locator('#provider').select_option(provider)
        enable_points(f);remove_all(f)
        keys=f.evaluate('steppeLive.map.config.cells.slice(0,5).map(c=>c.key)')
        for key in keys:pick(f,key)
        expect(f.locator('#route-coordinate-list li')).to_have_count(5)
        pick(f,keys[0]);expect(f.locator('#route-coordinate-list li')).to_have_count(5)
        expect(f.locator('#route-feedback')).to_contain_text('1–5')
        # Deleting a mistaken fifth point frees a slot; then return to the first.
        f.locator('#route-coordinate-list button').last.click();pick(f,keys[0])
        load(f)
        assert f.evaluate('steppeLive.request.state')=='ready'
        path=f.evaluate('steppeLive.map.config.point_keys')
        assert path[0]==path[-1]==keys[0]
        ordered=[path.index(k) for k in keys[:4]];assert ordered==sorted(ordered)
        ids=f.evaluate('steppeLive.request.track.intervals.map(s=>s.cell_id)')
        assert len(set(ids))==len(ids)
        assert f.evaluate('steppeLive.request.track.duration_s')==len(path)*.5
        assert media(f)['paused'] and media(f)['time']==0
        assert f.locator('audio').count()==1
        f.locator('#progress').press('ArrowRight')
        expect(f.locator('#point-cell')).to_have_text('USR-0002')
        expect(f.locator('#timeline tr.active')).to_have_attribute('data-cell-id','USR-0002')
        assert f.evaluate('steppeLive.map.currentIndex')==1
        token=f.evaluate('steppeLive.routeToken')
        if provider=='eic':f.locator('#eic-date').select_option('2026-06-10')
        else:f.locator('#observation-date').fill('2026-06-10');f.locator('#observation-date').press('Tab')
        load(f)
        assert f.evaluate('steppeLive.routeToken')==token
        assert f.evaluate('steppeLive.map.config.point_keys')==path
        assert f.evaluate('steppeLive.request.track.intervals[0].ndvi_class')==4
        # Verified source cache is reused for the custom path.
        load(f);assert f.evaluate('steppeLive.request.network_requests')==0
        f.locator('#provider').select_option('eic' if provider=='gibs' else 'gibs');load(f)
        assert f.evaluate('steppeLive.map.config.point_keys')==path
        f.locator('#reset-route').click()
        expect(f.locator('#point-count')).to_have_text('48');expect(f.locator('#toggle')).to_be_disabled()
        expect(f.locator('#route-coordinate-list li')).to_have_count(3)
        f.locator('#region').select_option('akmola')
        expect(f.locator('#point-count')).to_have_text('56')
        assert f.evaluate('steppeLive.map.config.point_ids[0]')=='AKM-001'
        assert f.evaluate('steppeLive.routeToken') is None
        assert media(f)['paused']
        assert not errors,errors
        ctx.close()


def test_one_point_keyboard_compact_translations_and_late_build_response(browser,tmp_path,monkeypatch):
    transport(tmp_path,monkeypatch)
    with running_app(None,tmp_path/'keyboard.log',live=True) as url:
        ctx,page,f=ui(browser,url);enable_points(f);remove_all(f)
        first=f.locator('[data-pick-key][tabindex="0"]');key=first.get_attribute('data-pick-key')
        first.focus();first.press('Space');load(f)
        assert f.evaluate('steppeLive.request.track.duration_s')==.5
        assert f.evaluate('steppeLive.map.config.point_keys')==[key]
        for lang in ['kk','en','ru']:
            f.locator('#language').select_option(lang)
            assert 'undefined' not in f.locator('#route-points').inner_text()
            for width,height in [(1280,720),(1024,576),(853,480),(390,844),(320,844)]:
                page.set_viewport_size({'width':width,'height':height})
                assert f.evaluate('document.documentElement.scrollWidth<=innerWidth')
                if width>=853:
                    for selector in ['#toggle','#progress','#step-forward']:
                        rect=f.locator(selector).bounding_box();assert rect['y']+rect['height']<=height
        # A reply to an abandoned draft must not replace the current geometry.
        old=f.evaluate('steppeLive.map.config.point_keys')
        f.evaluate('''()=>{steppeLive.buildId='old-build';steppeLive.invalidate();
          steppeLive.accept({route_result:{id:'old-build',definition:{route:[]}},catalog_dates:[]});}''')
        assert f.evaluate('steppeLive.map.config.point_keys')==old
        ctx.close()


def test_unavailable_water_mask_is_never_requested_and_any_cell_is_usable(browser,tmp_path,monkeypatch):
    folder=transport(tmp_path,monkeypatch);(folder/'mask-offline').touch()
    with running_app(None,tmp_path/'offline.log',live=True) as url:
        ctx,page,f=ui(browser,url);enable_points(f);remove_all(f)
        # A real mask used to classify this cell as water.
        pick(f,'258/1069');load(f)
        assert f.evaluate('steppeLive.ready')
        assert f.evaluate('steppeLive.map.config.point_keys')==['258/1069']
        assert 'Land_Water_Mask' not in (folder/'requests.log').read_text()
        assert f.locator('#route-mask-retry').count()==0
        ctx.close()


def test_server_validation_does_not_replace_loaded_preset(browser,tmp_path,monkeypatch):
    folder=transport(tmp_path,monkeypatch)
    with running_app(None,tmp_path/'validation.log',live=True) as url:
        ctx,page,f=ui(browser,url);load(f);enable_points(f)
        key=f.evaluate('steppeLive.map.config.cells[0].key')
        for points,code in [([key]*6,'points_limit'),(['9999/9999'],'outside')]:
            f.evaluate('''points=>{steppeLive.routeError=null;
                steppeLive.buildId=steppeLive.command('build_route',{region:steppeLive.hooks.region(),waypoints:points});}''',points)
            f.wait_for_function('(code)=>steppeLive.buildId===null&&steppeLive.routeError?.error===code',arg=code)
            assert f.evaluate('steppeLive.ready')
            expect(f.locator('#point-count')).to_have_text('48')
            assert f.evaluate('steppeLive.routeToken') is None
        ctx.close()
