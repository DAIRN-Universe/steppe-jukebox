"""A collapsed point editor below Load, without an upcoming route trail."""
import pytest
from playwright.sync_api import expect
from test_browser import browser,running_app,media
from test_live_browser import transport,ui,load
from test_route_browser import enable_points,remove_all,pick

pytestmark=pytest.mark.browser


@pytest.mark.parametrize('region,count',[('kostanay',3),('akmola',4)])
def test_collapsible_panel_order_markers_and_playback_trail(browser,tmp_path,monkeypatch,region,count):
    transport(tmp_path,monkeypatch)
    with running_app(None,tmp_path/'panel.log',live=True) as url:
        ctx,page,f=ui(browser,url);errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        f.locator('#region').select_option(region)
        panel=f.locator('#route-points');summary=f.locator('#route-points > summary')
        assert not panel.evaluate('e=>e.open')
        expect(f.locator('#route-point-counter')).to_have_text(f'{count}/5')
        expect(f.locator('#route-coordinate-list')).not_to_be_visible()
        expect(f.locator('.route-waypoint')).to_have_count(count)
        expect(f.locator('.route-tile:not([hidden])')).to_have_count(0)
        for lang in ['ru','kk','en']:
            f.locator('#language').select_option(lang)
            for width in [1280,900,390,320]:
                page.set_viewport_size({'width':width,'height':1000})
                f.evaluate('()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)))')
                assert f.evaluate('document.documentElement.scrollWidth<=innerWidth')
                boxes=f.evaluate('''()=>({load:document.querySelector('#load-data').getBoundingClientRect().toJSON(),
                    panel:document.querySelector('#route-points').getBoundingClientRect().toJSON()})''')
                load_box,panel_box=boxes['load'],boxes['panel']
                assert panel_box['y']>=load_box['y']+load_box['height']-1
                assert panel_box['height']<75
        page.set_viewport_size({'width':1280,'height':1000})
        summary.press('Enter');expect(f.locator('#route-coordinate-list')).to_be_visible()
        enable_points(f);draft=f.evaluate('steppeLive.draft')
        summary.press('Space');assert not panel.evaluate('e=>e.open')
        assert f.evaluate('steppeLive.draft')==draft
        f.locator('#map-zoom-in').click();assert not panel.evaluate('e=>e.open')
        load(f);assert not panel.evaluate('e=>e.open')
        expect(f.locator('.route-tile:not([hidden])')).to_have_count(0)
        f.locator('#step-forward').click()
        assert f.locator('.route-tile.active').count()==1
        assert f.locator('.route-tile:not([hidden]):not(.active):not(.passed)').count()==0
        f.locator('#toggle').press('Enter');f.wait_for_function('document.querySelector("audio").currentTime>.55')
        summary.click();assert not media(f)['paused']
        summary.click();assert not media(f)['paused']
        f.locator('#toggle').click();before=media(f)['time']
        summary.click();assert media(f)['paused'] and abs(media(f)['time']-before)<.01
        # Adding on the map remains active when its settings are collapsed.
        assert f.evaluate('document.querySelector("#add-route-points").checked')
        # An empty draft error is revealed even when the panel was collapsed.
        enable_points(f);remove_all(f);summary.click();f.locator('#load-data').click()
        assert panel.evaluate('e=>e.open')
        expect(f.locator('#route-feedback')).to_be_visible()
        assert f.evaluate('steppeLive.routeError.error')=='points_limit'
        # Restart and backward seeking restore a hidden upcoming trail.
        f.locator('#reset-route').click();load(f)
        expect(f.locator('.route-tile:not([hidden])')).to_have_count(0)
        f.locator('#step-forward').click();f.locator('#step-back').click()
        assert f.locator('.route-tile.passed').count()==0
        f.locator('#restart').click()
        expect(f.locator('.route-tile:not([hidden])')).to_have_count(0)
        assert not errors,errors
        ctx.close()
