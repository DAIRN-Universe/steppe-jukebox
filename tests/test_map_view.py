"""Actual mouse/touch selection, zoom/pan and audio preservation without a water mask."""
import pytest
from playwright.sync_api import expect
from test_browser import browser, running_app, media
from test_live_browser import transport, ui, load
from test_route_browser import remove_all, enable_points

pytestmark=pytest.mark.browser


def visible_keys(frame):
    return frame.evaluate('''()=>{const g=steppeMapView.hooks.geometry();
      return [...document.querySelectorAll('[data-pick-key]')].map(n=>({key:n.dataset.pickKey,
        x:+n.getAttribute('x')+(+n.getAttribute('width'))/2,y:+n.getAttribute('y')+(+n.getAttribute('height'))/2}))
        .filter(p=>p.x>g.left+20&&p.x<g.right-20&&p.y>g.top+20&&p.y<g.bottom-20)
        .sort((a,b)=>Math.hypot(a.x-g.centerX,a.y-g.centerY)-Math.hypot(b.x-g.centerX,b.y-g.centerY)).map(p=>p.key); }''')


@pytest.mark.parametrize('touch',[False,True])
def test_five_consecutive_pointer_selections_zoom_and_player(browser,tmp_path,monkeypatch,touch):
    folder=transport(tmp_path,monkeypatch);(folder/'mask-offline').touch()
    with running_app(None,tmp_path/'pointer.log',live=True) as url:
        if touch:
            ctx=browser.new_context(locale='ru-RU',viewport={'width':390,'height':844},has_touch=True,is_mobile=True)
            page=ctx.new_page();page.goto(url)
            from test_browser import player_frame
            f=player_frame(page)
        else:ctx,page,f=ui(browser,url)
        errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        enable_points(f);remove_all(f)
        f.locator('#map-zoom-in').click();f.locator('#map-zoom-in').click()
        expect(f.locator('#route-map')).to_have_attribute('data-zoom','4')
        keys=visible_keys(f)[:6];assert len(keys)==6
        for i,key in enumerate(keys[:5]):
            target=f.locator(f'[data-pick-key="{key}"]')
            if touch:target.tap()
            else:target.click()
            expect(f.locator('#route-coordinate-list li')).to_have_count(i+1)
        f.locator(f'[data-pick-key="{keys[5]}"]').click()
        expect(f.locator('#route-coordinate-list li')).to_have_count(5)
        expect(f.locator('#route-feedback')).to_contain_text('1–5')
        assert not (folder/'requests.log').exists()  # Selecting points uses no NASA requests.
        load(f);assert f.evaluate('steppeLive.ready')
        expect(f.locator('#add-route-points')).to_be_checked()
        expect(f.locator('#route-map')).to_have_attribute('data-zoom','4')
        assert media(f)['paused'] and f.locator('audio').count()==1
        f.locator('#toggle').press('Enter');f.wait_for_function('document.querySelector("audio").currentTime>.1')
        f.locator('#map-zoom-out').click()
        assert not media(f)['paused']
        f.locator('#toggle').press('Space');before=media(f)['time']
        f.locator('#map-fit').click()
        assert abs(media(f)['time']-before)<.01 and media(f)['paused']
        expect(f.locator('#route-map')).to_have_attribute('data-zoom','1')
        assert 'Land_Water_Mask' not in (folder/'requests.log').read_text()
        f.locator('#map-zoom-in').click()
        f.locator('#region').select_option('akmola')
        expect(f.locator('#route-map')).to_have_attribute('data-zoom','1')
        expect(f.locator('#route-coordinate-list li')).to_have_count(4)
        assert not errors,errors
        ctx.close()


def test_wheel_anchor_pan_no_accidental_point_and_reset(browser,tmp_path,monkeypatch):
    transport(tmp_path,monkeypatch)
    with running_app(None,tmp_path/'pan.log',live=True) as url:
        ctx,page,f=ui(browser,url);enable_points(f);remove_all(f)
        key=visible_keys(f)[0];target=f.locator(f'[data-pick-key="{key}"]')
        width=target.bounding_box()['width'];target.hover()
        before=f.evaluate('steppeMapView.hooks.geometry().projectX((steppeLive.map.config.cells.find(c=>c.key==="'+key+'").bounds[0]+steppeLive.map.config.cells.find(c=>c.key==="'+key+'").bounds[2])/2)')
        page.mouse.wheel(0,-200)
        f.wait_for_function('steppeMapView.zoom>1')
        assert target.bounding_box()['width']>width
        after=f.evaluate('steppeMapView.hooks.geometry().projectX((steppeLive.map.config.cells.find(c=>c.key==="'+key+'").bounds[0]+steppeLive.map.config.cells.find(c=>c.key==="'+key+'").bounds[2])/2)')
        assert abs(before-after)<1  # Wheel keeps the geographic anchor under the cursor.
        target.hover();box=target.bounding_box();x=box['x']+box['width']/2;y=box['y']+box['height']/2
        page.mouse.move(x,y);page.mouse.down();page.mouse.move(x+45,y+25,steps=5);page.mouse.up()
        expect(f.locator('#route-coordinate-list li')).to_have_count(0)
        f.wait_for_function('Math.abs(steppeMapView.lon)>0.01||Math.abs(steppeMapView.lat)>0.01')
        key=visible_keys(f)[0];f.locator(f'[data-pick-key="{key}"]').click()
        expect(f.locator('#route-coordinate-list li')).to_have_count(1)
        f.locator('#map-fit').click()
        assert f.evaluate('[steppeMapView.zoom,steppeMapView.lon,steppeMapView.lat]')==[1,0,0]
        expect(f.locator('#route-coordinate-list li')).to_have_count(1)
        ctx.close()


def test_two_finger_pinch_does_not_add_points(browser,tmp_path,monkeypatch):
    transport(tmp_path,monkeypatch)
    with running_app(None,tmp_path/'pinch.log',live=True) as url:
        ctx=browser.new_context(locale='ru-RU',viewport={'width':390,'height':844},has_touch=True,is_mobile=True)
        page=ctx.new_page();page.goto(url)
        from test_browser import player_frame
        f=player_frame(page);enable_points(f);remove_all(f)
        target=f.locator(f'[data-pick-key="{visible_keys(f)[0]}"]');target.scroll_into_view_if_needed()
        b=target.bounding_box();x=b['x']+b['width']/2;y=b['y']+b['height']/2
        cdp=ctx.new_cdp_session(page)
        def touches(kind,d):cdp.send('Input.dispatchTouchEvent',{'type':kind,'touchPoints':[] if kind=='touchEnd' else
            [{'x':x-d,'y':y,'id':1},{'x':x+d,'y':y,'id':2}]})
        touches('touchStart',12);touches('touchMove',24);touches('touchMove',32);touches('touchEnd',0)
        f.wait_for_function('steppeMapView.zoom>1.5')
        expect(f.locator('#route-coordinate-list li')).to_have_count(0)
        ctx.close()
