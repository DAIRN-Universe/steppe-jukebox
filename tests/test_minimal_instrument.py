"""User-driven seeking on the sole audio clock, and the agreed responsive layout."""
import math

import pytest
from playwright.sync_api import expect

from test_browser import browser, journey_url, localized_ui, media, running_app
from test_live_browser import transport, ui, load

pytestmark = pytest.mark.browser


def assert_synced(frame):
    state = media(frame)
    index = min(47, math.floor(state['time'] / .5))
    cell = f'KST-{index + 1:03d}'
    expect(frame.locator('#point-cell')).to_have_text(cell)
    expect(frame.locator('#timeline tr.active')).to_have_attribute('data-cell-id', cell)
    expect(frame.locator('.cell.active')).to_have_attribute('data-cell-id', cell)
    assert abs(float(frame.locator('#progress').input_value()) - state['time']) < .12


def test_click_drag_keyboard_and_end_seek_preserve_pause_and_playback(browser, journey_url):
    with localized_ui(browser, journey_url) as (page, frame):
        slider = frame.locator('#progress')
        expect(slider).to_be_enabled()
        bounds = slider.bounding_box()
        slider.click(position={'x': bounds['width'] * .35, 'y': bounds['height'] / 2})
        assert media(frame)['paused'] and 7 < media(frame)['time'] < 10
        assert_synced(frame)
        # Drag the actual thumb, without invoking an internal JS seek function.
        # The click may have scrolled the outer Streamlit page into view.
        bounds = slider.bounding_box()
        current = media(frame)['time'] / 24
        page.mouse.move(bounds['x'] + 7 + (bounds['width'] - 14) * current, bounds['y'] + bounds['height'] / 2)
        page.mouse.down()
        page.mouse.move(bounds['x'] + bounds['width'] * .7, bounds['y'] + bounds['height'] / 2, steps=8)
        page.mouse.up()
        assert media(frame)['paused'] and 15 < media(frame)['time'] < 18
        assert_synced(frame)
        slider.press('Home'); slider.press('ArrowRight')
        assert media(frame)['time'] == .5 and media(frame)['paused']
        assert_synced(frame)
        assert slider.evaluate('e=>getComputedStyle(e).outlineStyle') != 'none'
        slider.press('End')
        expect(frame.locator('#point-count')).to_have_text('48 / 48')
        expect(frame.locator('#toggle')).to_have_text('Запустить снова')
        assert media(frame)['time'] == 24 and media(frame)['paused']
        slider.press('ArrowLeft')
        assert media(frame)['time'] == 23.5 and media(frame)['paused']
        assert_synced(frame)
        slider.press('Home')
        frame.locator('#toggle').press('Enter')
        frame.wait_for_function('document.querySelector("audio").currentTime > .1')
        slider.click(position={'x': bounds['width'] * .45, 'y': bounds['height'] / 2})
        assert not media(frame)['paused'] and 9 < media(frame)['time'] < 12
        before = media(frame)['time']
        frame.wait_for_function('(t)=>document.querySelector("audio").currentTime > t + .2', arg=before)
        frame.locator('#toggle').press('Space')
        assert_synced(frame)
        frame.locator('#restart').press('Enter')
        assert media(frame)['time'] == 0 and media(frame)['paused']
        expect(frame.locator('#point-count')).to_have_text('48')
        expect(frame.locator('.cell.active')).to_have_count(0)


def test_step_buttons_and_cursor_keys_preserve_clock_and_native_navigation(browser, journey_url):
    with localized_ui(browser, journey_url) as (page, frame):
        back, forward = frame.locator('#step-back'), frame.locator('#step-forward')
        expect(back).to_be_disabled(); expect(forward).to_be_enabled()
        forward.click()
        assert media(frame)['time'] == .5 and media(frame)['paused']
        assert_synced(frame)
        back.click()
        assert media(frame)['time'] == 0 and media(frame)['paused']
        expect(back).to_be_disabled()
        frame.locator('#toggle').press('ArrowRight')
        assert media(frame)['time'] == .5 and media(frame)['paused']
        # The slider's own handler must not also trigger the page shortcut.
        frame.locator('#progress').press('ArrowRight')
        assert media(frame)['time'] == 1
        forward.press('ArrowLeft')
        assert media(frame)['time'] == .5
        # Selection fields and tabs keep native cursor-key navigation.
        frame.locator('#language').press('ArrowRight')
        assert media(frame)['time'] == .5
        frame.locator('#tab-listen').press('ArrowRight')
        expect(frame.locator('#method-view')).to_be_visible()
        assert media(frame)['time'] == .5
        frame.locator('[data-open-view="listen"].back-button').press('ArrowLeft')
        assert media(frame)['time'] == .5
        frame.locator('#tab-listen').click()
        frame.locator('#progress').press('End')
        expect(forward).to_be_disabled(); expect(back).to_be_enabled()
        back.click()
        assert media(frame)['time'] == 23.5 and media(frame)['paused']
        assert_synced(frame)
        frame.locator('#progress').press('Home')
        frame.locator('#toggle').press('Enter')
        frame.wait_for_function('document.querySelector("audio").currentTime > .1')
        # Sample and trigger within one browser task to exclude clock drift.
        before, after = forward.evaluate('e=>{const a=document.querySelector("audio"),t=a.currentTime;e.click();return [t,a.currentTime]}')
        assert abs(after - before - .5) < .01 and not media(frame)['paused']
        before, after = forward.evaluate('e=>{const a=document.querySelector("audio"),t=a.currentTime;e.dispatchEvent(new KeyboardEvent("keydown",{key:"ArrowLeft",bubbles:true}));return [t,a.currentTime]}')
        assert abs(after - max(0, before - .5)) < .01 and not media(frame)['paused']
        frame.locator('#toggle').press('Space')


@pytest.mark.parametrize('provider', ['gibs', 'eic'])
def test_journey_seek_changes_map_date_and_rewinds_trail_without_autoplay(browser, tmp_path, monkeypatch, provider):
    transport(tmp_path, monkeypatch)
    with running_app(None, tmp_path/'seek.log', live=True) as url:
        ctx, page, frame = ui(browser, url)
        try:
            expect(frame.locator('#progress')).to_be_disabled()
            expect(frame.locator('#step-back')).to_be_disabled()
            expect(frame.locator('#step-forward')).to_be_disabled()
            expect(frame.locator('#point-note')).to_have_text('—')
            frame.locator('#provider').select_option(provider)
            frame.locator('#mode').select_option('journey'); load(frame)
            slider = frame.locator('#progress'); expect(slider).to_be_enabled()
            slider.press('End'); slider.press('ArrowLeft')
            frame.wait_for_function('steppeLive.hooks.currentDate()==="2026-06-10"')
            expect(frame.locator('#point-cell')).to_have_text('KST-048')
            expect(frame.locator('#step-date')).to_have_text('2026-06-10')
            assert frame.evaluate('steppeLive.map.currentIndex') == 47
            assert frame.locator('.route-tile.passed').count() > 0
            assert media(frame)['paused']
            slider.press('Home')
            expect(frame.locator('#point-cell')).to_have_text('KST-001')
            expect(frame.locator('#step-date')).to_have_text('2026-04-20')
            expect(frame.locator('.route-tile.passed')).to_have_count(0)
            assert media(frame)['paused']
            frame.locator('#provider').select_option('eic' if provider == 'gibs' else 'gibs')
            expect(slider).to_be_disabled()
            assert media(frame)['paused'] and media(frame)['time'] == 0
            expect(frame.locator('#point-note')).to_have_text('—')
        finally:
            ctx.close()


@pytest.mark.parametrize('language', ['ru', 'kk', 'en'])
def test_recording_controls_fit_1080p_and_phone_has_no_horizontal_scroll(browser, journey_url, language):
    with localized_ui(browser, journey_url) as (page, frame):
        frame.locator('#language').select_option(language)
        page.set_viewport_size({'width': 1920, 'height': 1080})
        frame.evaluate('()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)))')
        assert not frame.locator('#technical-details').evaluate('e=>e.open')
        for selector in ['#route-map', '.point-card', '#progress', '#toggle', '#restart', '#step-back', '#step-forward', '#selection-panel']:
            rect = frame.locator(selector).bounding_box()
            assert rect['x'] >= 0 and rect['y'] >= 0
            assert rect['y'] + rect['height'] <= 1080, (selector, rect)
        for width in [390, 320]:
            page.set_viewport_size({'width': width, 'height': 844})
            frame.evaluate('()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)))')
            assert frame.evaluate('document.documentElement.scrollWidth <= innerWidth')
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            assert frame.locator('#point-note').evaluate('e=>e.getClientRects().length') == 1
            frame.locator('#progress').press('End')
            assert frame.locator('#point-count').evaluate('e=>e.scrollWidth <= e.clientWidth + 1')
            frame.locator('#restart').press('Enter')
            for selector in ['#toggle', '#restart', '#step-back', '#step-forward', '#progress', '#region']:
                control = frame.locator(selector)
                control.scroll_into_view_if_needed()
                rect = control.bounding_box()
                assert rect['x'] >= 0 and rect['x'] + rect['width'] <= width
                if selector != '#progress': assert rect['height'] >= 44
            frame.locator('#technical-details > summary').click()
            expect(frame.locator('#timeline')).to_be_visible()
            assert frame.evaluate('document.documentElement.scrollWidth <= innerWidth')
            frame.locator('#technical-details > summary').click()
