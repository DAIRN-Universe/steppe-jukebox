"""Research material is retained but unavailable in the public navigation."""

import pytest
from playwright.sync_api import expect

from test_browser import browser, app_url, localized_ui, media


pytestmark = pytest.mark.browser


@pytest.mark.parametrize('language', ['ru', 'kk', 'en'])
def test_research_stays_hidden_during_navigation_and_playback(browser, app_url, language):
    with localized_ui(browser, app_url) as (page, f):
        f.locator('#language').select_option(language)
        expect(f.locator('#tab-research')).not_to_be_visible()
        expect(f.locator('#research-view')).not_to_be_visible()
        expect(f.get_by_role('tab')).to_have_count(2)
        # Retain the original publications for a later decision to restore them.
        expect(f.locator('.research-card a[href^="https://doi.org/"]')).to_have_count(2)
        f.locator('#toggle').click()
        f.wait_for_function('document.querySelector("audio").currentTime > .1')
        f.locator('#tab-listen').press('End')
        expect(f.locator('#tab-method')).to_be_focused()
        f.locator('#tab-method').press('ArrowRight')
        expect(f.locator('#tab-listen')).to_be_focused()
        assert not media(f)['paused']
        # The hidden tab cannot be opened through its stale click handler either.
        f.locator('#tab-research').evaluate('e => e.click()')
        expect(f.locator('#listen-view')).to_be_visible()
        expect(f.locator('#research-view')).not_to_be_visible()
