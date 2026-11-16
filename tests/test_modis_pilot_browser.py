"""Play the real pilot classes through the existing saved-data player."""
import csv
import json
import shutil
import pytest
from playwright.sync_api import expect
from test_browser import ROOT, browser, localized_ui, running_app

pytestmark = pytest.mark.browser

@pytest.mark.parametrize('year', [2001, 2013, 2025])
def test_modis_pilot_playback_uses_one_clock(browser, tmp_path, year):
    data = tmp_path / 'dataset'
    data.mkdir()
    shutil.copy(ROOT / 'data/real-test/noaa20-kostanay/route.csv', data / 'route.csv')
    with (ROOT / f'data/modis-pilot/{year}-route.csv').open() as f:
        samples = list(csv.DictReader(f))
    for season in ('spring', 'summer'):
        with (data / f'{season}.csv').open('w', newline='') as f:
            out = csv.writer(f); out.writerow(['cell_id', 'ndvi_class'])
            out.writerows((row['cell_id'], row['class']) for row in samples)
    (data / 'metadata.json').write_text(json.dumps({'is_test': False, 'description': f'NASA MOD13Q1 pilot {year}'}))
    with running_app(data, tmp_path / 'app.log') as url:
        with localized_ui(browser, url, locale='en-US') as (page, frame):
            frame.locator('#toggle').click()
            for index in (0, 1, 2):
                frame.wait_for_function('i => { const a=document.querySelector("audio"), r=document.querySelector("#timeline tr.active"), m=document.querySelector("#route-map .cell.active"); return !a.paused && a.currentTime >= i*.5+.08 && a.currentTime < (i+1)*.5-.05 && r?.dataset.cellId === `KST-${String(i+1).padStart(3,"0")}` && m?.dataset.cellId === r.dataset.cellId; }', arg=index, timeout=10000)
            if year == 2013:
                frame.locator('#progress').fill('0.6')
                frame.wait_for_function('document.querySelector("#timeline tr.active")?.dataset.cellId === "KST-002"')
                expect(frame.locator('#route-map .cell.active')).to_have_attribute('data-cell-id', 'KST-002')
                assert samples[1]['class'] == '' and samples[1]['note'] == ''
            frame.locator('#toggle').click()
            assert frame.locator('audio').evaluate('a => a.paused')
