"""Ported prototype sections: keyboard, language, narrow layout and audio clock."""

import pytest
from playwright.sync_api import expect

from test_browser import browser, journey_url, localized_ui, media, assert_reset, resize_viewport


pytestmark = pytest.mark.browser


@pytest.mark.parametrize("language,region,method", [
    ("ru", "Костанайская область", "Как это работает"),
    ("kk", "Қостанай облысы", "Қалай жұмыс істейді"),
    ("en", "Kostanay Region", "How it works"),
])
@pytest.mark.parametrize("region_key", ["kostanay", "akmola"])
def test_prototype_navigation_and_context_fit_desktop_and_mobile(browser, journey_url, language, region, method, region_key):
    with localized_ui(browser, journey_url) as (page, frame):
        frame.locator("#region").select_option(region_key)
        frame.locator("#language").select_option(language)
        if region_key == "akmola":
            region = {"ru": "Акмолинская область", "kk": "Ақмола облысы", "en": "Akmola Region"}[language]
        expect(frame.locator("#region option:checked")).to_have_text(region)
        expect(frame.locator("#map-attribution")).to_contain_text("OpenStreetMap")
        expect(frame.locator(".region-outline")).to_have_count(1)
        for width in [1440, 390, 320]:
            resize_viewport(page, frame, width, 900)
            for view in ["listen", "method"]:
                frame.locator(f"#tab-{view}").click()
                expect(frame.locator(f"#{view}-view")).to_be_visible()
                assert frame.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), (language, width, view)
                assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
            expect(frame.locator("#tab-method")).to_have_text(method)
        assert frame.locator('#navigation [role="tab"]:visible').evaluate_all("nodes => nodes.map(n => n.dataset.view)") == ["listen", "method"]
        expect(frame.locator("#research-view")).not_to_be_visible()
        expect(frame.locator("#places-view, .field-context")).to_have_count(0)
        frame.locator("#tab-listen").click()
        frame.locator("#tab-listen").press("ArrowRight")
        expect(frame.locator("#tab-method")).to_be_focused()
        frame.locator("#tab-method").press("ArrowRight")
        expect(frame.locator("#tab-listen")).to_be_focused()
        frame.locator("#tab-listen").press("End")
        expect(frame.locator("#tab-method")).to_be_focused()
        frame.locator("#tab-method").press("Home")
        expect(frame.locator("#tab-listen")).to_be_focused()
        assert media(frame)["paused"] and media(frame)["time"] == 0


def test_navigation_and_language_preserve_clock_restart_stops_without_autoplay(browser, journey_url):
    with localized_ui(browser, journey_url) as (page, frame):
        frame.locator("#mode").select_option("journey")
        frame.locator("#toggle").press("Enter")
        frame.wait_for_function("document.querySelector('audio').currentTime > 0.65")
        original_source = frame.locator("audio").get_attribute("src")
        before = media(frame)["time"]
        frame.locator("#tab-method").click()
        frame.locator("#language").select_option("kk")
        assert media(frame)["time"] >= before
        assert not media(frame)["paused"]
        assert frame.locator("audio").get_attribute("src") == original_source
        frame.locator("#tab-listen").click()
        frame.locator("#toggle").press("Space")
        paused = media(frame)["time"]
        active = frame.locator(".cell.active").get_attribute("data-cell-id")
        frame.locator("#tab-method").click()
        frame.locator("#language").select_option("en")
        frame.locator("#tab-listen").click()
        assert media(frame)["time"] == paused
        expect(frame.locator(".cell.active")).to_have_attribute("data-cell-id", active)
        frame.locator("#restart").press("Enter")
        frame.locator("#language").select_option("ru")
        assert_reset(frame)
        page.wait_for_timeout(650)
        assert_reset(frame)
        frame.locator("#toggle").press("Enter")
        frame.wait_for_function("document.querySelector('audio').currentTime > 0.65")
        frame.locator("#restart").press("Space")
        assert_reset(frame)
