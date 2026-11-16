"""Opt-in browser acceptance against the user's prepared NASA cache."""
import os
import pytest
from playwright.sync_api import expect
from test_browser import browser, running_app
from test_live_browser import ui, load

pytestmark = [pytest.mark.browser, pytest.mark.skipif(not os.environ.get('STEPPE_ISSUE23_REAL'), reason='Requires real NASA cache')]

def test_real_presets_and_exact_dates(browser, tmp_path):
    with running_app(None, tmp_path/'real23.log', live=True) as url:
        ctx, page, f = ui(browser, url)
        for region in ['north-kazakhstan','pavlodar','west-kazakhstan','aktobe','karaganda','abai']:
            f.locator('#region').select_option(region)
            for provider, day in [('gibs','2026-04-15'),('eic','2026-04-20')]:
                f.locator('#provider').select_option(provider)
                if f.locator('#eic-date').is_visible():
                    f.locator('#eic-date').select_option(day)
                else:
                    f.locator('#observation-date').fill(day)
                    f.locator('#observation-date').press('Tab')
                load(f)
                result = f.evaluate('steppeLive.request')
                assert result['state'] == 'ready', (region, provider, result)
                assert {s['date'] for s in result['track']['intervals']} == {day}
                assert f.evaluate('document.querySelector("audio").paused')
                assert f.evaluate('steppeLive.maps.size > 0')
                f.locator('#step-forward').click()
                assert f.evaluate('steppeLive.map.currentIndex') == 1
        ctx.close()


def test_real_custom_routes_maps_and_audio(browser, tmp_path):
    import base64, io, wave
    import numpy as np
    from pathlib import Path
    from test_route_browser import enable_points, remove_all, pick
    from steppe_jukebox.sound import SCALE, SAMPLE_RATE, STEP_SAMPLES
    output = Path('/tmp/steppe-issue23-review')
    output.mkdir(exist_ok=True)
    with running_app(None, tmp_path/'custom-real.log', live=True) as url:
        ctx, page, f = ui(browser, url)
        page.set_viewport_size({'width': 1440, 'height': 1100})
        for region in ['north-kazakhstan','pavlodar','west-kazakhstan','aktobe','karaganda','abai']:
            f.locator('#region').select_option(region)
            keys = f.evaluate('steppeLive.map.config.point_keys')
            chosen = [keys[round(i * (len(keys)-1) / 4)] for i in range(5)]
            enable_points(f); remove_all(f)
            for key in chosen: pick(f, key)
            for provider, day in [('gibs','2026-04-15'),('eic','2026-04-20')]:
                f.locator('#provider').select_option(provider)
                if f.locator('#eic-date').is_visible(): f.locator('#eic-date').select_option(day)
                else:
                    f.locator('#observation-date').fill(day); f.locator('#observation-date').press('Tab')
                load(f)
                result = f.evaluate('steppeLive.request')
                assert result['state'] == 'ready', (region, provider, result.get('error'), result.get('route_errors'))
                slots = result['track']['intervals']
                assert all(s['date'] == day for s in slots)
                assert result['track']['duration_s'] == len(slots) * .5
                assert f.evaluate('document.querySelector("audio").paused')
                with wave.open(io.BytesIO(base64.b64decode(result['track']['audio_src'].split(',')[1]))) as wav:
                    assert wav.getframerate() == SAMPLE_RATE and wav.getnframes() == len(slots)*STEP_SAMPLES
                    samples=np.frombuffer(wav.readframes(wav.getnframes()),dtype='<i2')
                for i,slot in enumerate(slots):
                    segment=samples[i*STEP_SAMPLES:(i+1)*STEP_SAMPLES]
                    if slot['ndvi_class'] is None: assert not segment.any()
                    else:
                        assert segment.any() and slot['note'] == SCALE[slot['ndvi_class']-1].name
                        spectrum=np.abs(np.fft.rfft(segment))
                        frequency=np.argmax(spectrum)*SAMPLE_RATE/len(segment)
                        assert abs(frequency-SCALE[slot['ndvi_class']-1].frequency)<3
                f.locator('#step-forward').click()
                assert f.evaluate('steppeLive.map.currentIndex') == 1
                expect(f.locator('#timeline tr.active')).to_have_attribute('data-cell-id','USR-0002')
                f.locator('#route-map').screenshot(path=str(output/f'{region}-{provider}.png'))
                f.locator('#toggle').click()
                f.wait_for_function('document.querySelector("audio").currentTime > .6',timeout=10000)
                f.locator('#toggle').click()
        ctx.close()
