"""Restored papers stay separate from satellite data and the running player."""

import pytest
from playwright.sync_api import expect

from test_browser import browser, running_app, media, resize_viewport
from test_live_browser import transport, ui, load


pytestmark = pytest.mark.browser

PAPERS = {
    "naurzum": "https://doi.org/10.1515/hacq-2016-0017",
    "kamennoye": "https://doi.org/10.32523/2616-7034-2023-145-4-63-70",
}


@pytest.mark.parametrize("locale,language,title", [
    ("ru-RU", "ru", "Научные работы"),
    ("kk-KZ", "kk", "Ғылыми еңбектер"),
    ("en-GB", "en", "Research"),
])
def test_research_sources_regions_and_narrow_layout(browser, tmp_path, monkeypatch, locale, language, title):
    folder = transport(tmp_path, monkeypatch)
    with running_app(None, tmp_path / "research.log", live=True) as url:
        ctx, page, f = ui(browser, url, locale)
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        f.locator("#tab-research").click()
        expect(f.locator("#research-view h1")).to_have_text(title)
        expect(f.locator("html")).to_have_attribute("lang", language)
        for selector in ["#listen-view", "#method-view", "#playback-controls", "#selection-panel"]:
            expect(f.locator(selector)).not_to_be_visible()
        expect(f.locator(".research-card")).to_have_count(2)
        expect(f.locator('[data-study="naurzum"]')).to_contain_text("2010")
        expect(f.locator('[data-study="kamennoye"]')).to_contain_text("2019–2022")
        for study, link in PAPERS.items():
            anchor = f.locator(f'[data-study="{study}"] a')
            expect(anchor).to_have_attribute("href", link)
            expect(anchor).to_have_attribute("target", "_blank")
            expect(anchor).to_have_attribute("rel", "noopener noreferrer")
        expect(f.locator("#research-region-note")).not_to_be_visible()
        for width in [1440, 1280, 1024, 853, 390, 320]:
            resize_viewport(page, f, width, 1000)
            assert f.evaluate("document.documentElement.scrollWidth <= innerWidth"), (language, width)
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            tabs = f.locator('#navigation [role="tab"]').evaluate_all("nodes => nodes.map(n => n.getBoundingClientRect().toJSON())")
            assert all(t["left"] >= 0 and t["right"] <= f.evaluate("innerWidth") for t in tabs), (language, width, tabs)
            assert all(a["bottom"] <= b["top"] + 1 or a["right"] <= b["left"] + 1 for a, b in zip(tabs, tabs[1:]))
        f.locator("#research-view .back-button").click()
        f.locator("#region").select_option("akmola")
        f.locator("#tab-research").click()
        expect(f.locator("#research-region-note")).to_be_visible()
        expect(f.locator(".research-card")).to_have_count(2)
        assert not (folder / "requests.log").exists()
        assert not errors
        ctx.close()


def test_research_navigation_and_source_link_preserve_live_audio(browser, tmp_path, monkeypatch):
    folder = transport(tmp_path, monkeypatch)
    with running_app(None, tmp_path / "research-audio.log", live=True) as url:
        ctx, page, f = ui(browser, url)
        load(f)
        source = f.locator("audio").get_attribute("src")
        requests = (folder / "requests.log").read_text()
        f.locator("#map-zoom-in").click()
        zoom = f.evaluate("steppeMapView.zoom")
        f.locator("#toggle").click()
        f.wait_for_function("document.querySelector('audio').currentTime > .1")
        before = media(f)["time"]
        f.locator("#tab-method").click()
        f.locator("#tab-method").press("ArrowRight")
        expect(f.locator("#tab-research")).to_be_focused()
        f.locator("#language").select_option("kk")
        ctx.route(PAPERS["naurzum"], lambda route: route.fulfill(status=200, content_type="text/html", body="<title>Research</title>"))
        with ctx.expect_page() as popup:
            f.locator('[data-study="naurzum"] a').click()
        popup.value.wait_for_url(PAPERS["naurzum"])
        popup.value.close()
        assert media(f)["time"] >= before and not media(f)["paused"]
        f.locator("#research-view .back-button").click()
        f.locator("#toggle").click()
        paused = media(f)["time"]
        f.locator("#tab-research").click()
        f.locator("#language").select_option("en")
        f.locator("#tab-listen").click()
        assert media(f)["paused"] and abs(media(f)["time"] - paused) < .01
        assert f.locator("audio").get_attribute("src") == source
        assert f.evaluate("steppeMapView.zoom") == zoom
        assert (folder / "requests.log").read_text() == requests
        expect(f.locator("audio")).to_have_count(1)
        ctx.close()
