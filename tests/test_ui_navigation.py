"""Ported prototype sections: keyboard, language, narrow layout and audio clock."""

import pytest
from playwright.sync_api import expect

from test_browser import browser, journey_url, localized_ui, media, assert_reset


pytestmark = pytest.mark.browser


@pytest.mark.parametrize("language,region,places,method", [
    ("ru", "Костанайская область", "Растения и места", "Как это работает"),
    ("kk", "Қостанай облысы", "Өсімдіктер мен орындар", "Қалай жұмыс істейді"),
    ("en", "Kostanay Region", "Plants and places", "How it works"),
])
@pytest.mark.parametrize("region_key", ["kostanay", "akmola"])
def test_prototype_navigation_and_context_fit_desktop_and_mobile(browser, journey_url, language, region, places, method, region_key):
    with localized_ui(browser, journey_url) as (page, frame):
        frame.locator("#region").select_option(region_key)
        frame.locator("#language").select_option(language)
        if region_key == "akmola":
            region = {"ru": "Акмолинская область", "kk": "Ақмола облысы", "en": "Akmola Region"}[language]
        expect(frame.locator("#region option:checked")).to_have_text(region)
        expect(frame.locator("#map-attribution")).to_contain_text("OpenStreetMap")
        expect(frame.locator(".region-outline")).to_have_count(1)
        for width in [1440, 390, 320]:
            page.set_viewport_size({"width": width, "height": 900})
            for view in ["listen", "places", "method"]:
                frame.locator(f"#tab-{view}").click()
                expect(frame.locator(f"#{view}-view")).to_be_visible()
                assert frame.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), (language, width, view)
                assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
            expect(frame.locator("#tab-places")).to_have_text(places)
            expect(frame.locator("#tab-method")).to_have_text(method)
        frame.locator("#tab-places").click()
        if region_key == "kostanay":
            expect(frame.locator("#place-content")).to_contain_text("2010")
            frame.locator('[data-place="kamennoye"]').click()
            expect(frame.locator("#place-content")).to_contain_text("2019–2022")
            expect(frame.locator("#place-content")).to_contain_text("177")
            frame.locator('[data-place="akkum"]').click()
        else:
            expect(frame.locator("#place-tabs button")).to_have_count(0)
            expect(frame.locator("#place-content")).not_to_contain_text("2010")
            expect(frame.locator("#place-content")).not_to_contain_text("177")
        expect(frame.locator("#place-content a")).to_have_count(0)
        frame.locator("#tab-listen").click()
        frame.locator("#tab-listen").press("ArrowRight")
        expect(frame.locator("#tab-places")).to_be_focused()
        frame.locator("#tab-places").press("End")
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
        frame.locator("#tab-places").click()
        frame.locator("#language").select_option("kk")
        frame.locator("#tab-method").click()
        assert media(frame)["time"] >= before
        assert not media(frame)["paused"]
        assert frame.locator("audio").get_attribute("src") == original_source
        frame.locator("#tab-listen").click()
        frame.locator("#toggle").press("Space")
        paused = media(frame)["time"]
        active = frame.locator(".cell.active").get_attribute("data-cell-id")
        frame.locator("#tab-places").click()
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
