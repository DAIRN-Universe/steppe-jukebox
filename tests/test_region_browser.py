"""Real two-region playback, switching and geographic alignment in Chromium."""

import csv

import pytest
from playwright.sync_api import expect

from test_browser import (
    ROOT, assert_map_coordinates, assert_reset, browser, journey_url, localized_ui, media,
)


pytestmark = pytest.mark.browser


def dataset_rows(region, filename):
    with (ROOT / f"data/real-test/noaa20-{region}/{filename}").open(newline="") as source:
        return list(csv.DictReader(source))


@pytest.mark.parametrize("mode", ["fixed", "journey"])
@pytest.mark.parametrize("state", ["playing", "paused"])
def test_region_switch_stops_old_track_resets_and_preserves_choices(browser, journey_url, mode, state):
    with localized_ui(browser, journey_url) as (page, frame):
        frame.locator("#season").select_option("summer")
        frame.locator("#mode").select_option(mode)
        original_source = frame.locator("audio").get_attribute("src")
        original_boundary = frame.locator(".region-outline").get_attribute("d")
        for region, key, count, duration, ring_count in [
            ("akmola", "ArrowDown", 56, 28, 6),
            ("kostanay", "ArrowUp", 48, 24, 1),
        ]:
            frame.locator("#toggle").press("Enter")
            frame.wait_for_function("document.querySelector('audio').currentTime > .65")
            if state == "paused":
                frame.locator("#toggle").press("Space")
                assert media(frame)["paused"]
            selector = frame.get_by_label("Область", exact=True)
            selector.focus()
            selector.press(key)
            expect(selector).to_have_value(region)
            expect(frame.locator("#mode")).to_have_value(mode)
            expect(frame.locator("#season")).to_have_value("summer")
            assert_reset(frame)
            frame.wait_for_function("document.querySelector('audio').readyState >= 2")
            assert frame.locator("audio").evaluate("audio => audio.duration") == duration
            expect(frame.locator("audio")).to_have_count(1)
            expect(frame.locator("#timeline tbody tr")).to_have_count(count)
            route = dataset_rows(region, "route.csv")
            ids = [row["cell_id"] for row in route]
            assert frame.locator("#timeline tbody tr").evaluate_all("rows => rows.map(row => row.dataset.cellId)") == ids
            assert frame.locator("#map-content .cell").evaluate_all("nodes => nodes.map(node => node.dataset.cellId)") == ids
            path = frame.locator(".region-outline").get_attribute("d")
            assert path.count("M ") == ring_count
            source = frame.locator("audio").get_attribute("src")
            if region == "akmola":
                assert path != original_boundary and source != original_source
            else:
                assert path == original_boundary and source == original_source
            if mode == "journey":
                expect(frame.locator("#step-date")).to_have_text("2026-04-15")
                expect(frame.locator("#step-place")).to_contain_text(ids[0])
                expected = [row["date"] for row in dataset_rows(region, "journey.csv")]
                assert frame.locator("#timeline tbody tr").evaluate_all("rows => rows.map(row => row.children[2].textContent)") == expected
            else:
                expect(frame.locator("#season-info")).to_contain_text("2026-07-16")
            page.wait_for_timeout(650)
            assert_reset(frame)
            expect(frame.locator("#error")).to_be_hidden()


@pytest.mark.parametrize("mode", ["fixed", "journey"])
def test_region_switch_cancels_pending_native_play(browser, journey_url, mode):
    with localized_ui(browser, journey_url) as (page, frame):
        frame.locator("#mode").select_option(mode)
        frame.evaluate("""() => {
          document.querySelector('#toggle').addEventListener('click', () => {
            const region = document.querySelector('#region');
            region.value = 'akmola';
            region.dispatchEvent(new Event('change'));
          }, {once: true});
        }""")
        frame.locator("#toggle").press("Enter")
        page.wait_for_timeout(650)
        expect(frame.locator("#region")).to_have_value("akmola")
        assert_reset(frame)
        expect(frame.locator("#error")).to_be_hidden()
        expect(frame.locator("#timeline tbody tr")).to_have_count(56)


@pytest.mark.parametrize("language", ["ru", "kk", "en"])
def test_both_region_boundaries_and_routes_share_localized_coordinate_axes(browser, journey_url, language):
    with localized_ui(browser, journey_url) as (page, frame):
        frame.locator("#language").select_option(language)
        for region in ["kostanay", "akmola"]:
            frame.locator("#region").select_option(region)
            for width in [1440, 390, 320]:
                page.set_viewport_size({"width": width, "height": 1000})
                # ResizeObserver redraws SVG nodes between layout and the next paint.
                frame.evaluate("() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))")
                assert_map_coordinates(frame, ROOT / f"data/real-test/noaa20-{region}/route.csv")
                assert frame.evaluate("getComputedStyle(document.querySelector('.region-outline')).fillRule") == "evenodd"
                expect(frame.locator("#map-credit")).to_be_visible()
                expect(frame.locator("#map-attribution")).to_contain_text("OpenStreetMap")
            if language == "en":
                import re
                assert not re.search("[А-Яа-яӘәҒғҚқҢңӨөҰұҮүҺһІі]", frame.locator("#player").inner_text())


def test_navigation_hides_region_controls_and_region_switch_resets_audio(browser, journey_url):
    with localized_ui(browser, journey_url) as (_, frame):
        frame.locator("#mode").select_option("journey")
        frame.locator("#toggle").press("Enter")
        frame.wait_for_function("document.querySelector('audio').currentTime > .2")
        frame.locator("#tab-method").click()
        expect(frame.locator("#selection-panel")).not_to_be_visible()
        assert not media(frame)["paused"]
        frame.locator("#tab-listen").click()
        frame.locator("#region").select_option("akmola")
        assert_reset(frame)
        expect(frame.locator("#route-map .cell")).to_have_count(56)
        frame.locator("#language").select_option("en")
        frame.locator("#tab-method").click()
        expect(frame.locator("#selection-panel")).not_to_be_visible()
        frame.locator("#tab-listen").click()
        frame.locator("#region").select_option("kostanay")
        expect(frame.locator("#step-place")).to_contain_text("Kamennoye Lake")
        assert media(frame)["paused"] and media(frame)["time"] == 0
        expect(frame.locator("#route-map .cell")).to_have_count(48)


def test_akmola_gap_advances_date_and_marker_user_pause_freezes_them(browser, journey_url):
    with localized_ui(browser, journey_url) as (page, frame):
        frame.locator("#region").select_option("akmola")
        frame.locator("#mode").select_option("journey")
        frame.locator("#toggle").press("Enter")
        frame.wait_for_function("document.querySelector('audio').currentTime > .1")
        frame.locator("audio").evaluate("audio => { audio.currentTime = 13.05; }")
        expect(frame.locator(".cell.active")).to_have_attribute("data-cell-id", "AKM-027")
        expect(frame.locator("#step-date")).to_have_text("2026-07-24")
        expect(frame.locator("#status")).to_contain_text("нет данных → пауза")
        assert not media(frame)["paused"]
        frame.locator("#toggle").press("Space")
        frozen = media(frame)["time"]
        assert 13 <= frozen < 13.5
        page.wait_for_timeout(650)
        assert media(frame)["time"] == frozen
        expect(frame.locator(".cell.active")).to_have_attribute("data-cell-id", "AKM-027")
        expect(frame.locator("#step-date")).to_have_text("2026-07-24")
        for language in ["kk", "en", "ru"]:
            frame.locator("#language").select_option(language)
            assert media(frame)["time"] == frozen
            expect(frame.locator("#step-date")).to_have_text("2026-07-24")
        frame.locator("#toggle").press("Enter")
        frame.wait_for_function("document.querySelector('audio').currentTime >= 13.5")
        frame.locator("#toggle").press("Space")
        index = int(media(frame)["time"] / 0.5)
        expected = dataset_rows("akmola", "journey.csv")
        assert index >= 27
        expect(frame.locator(".cell.active")).to_have_attribute("data-cell-id", expected[index]["cell_id"])
        expect(frame.locator("#step-date")).to_have_text(expected[index]["date"])


def test_full_akmola_journey_tracks_all_56_dates_and_rest_on_audio_clock(browser, journey_url):
    expected = dataset_rows("akmola", "journey.csv")
    with localized_ui(browser, journey_url) as (_, frame):
        frame.locator("#region").select_option("akmola")
        frame.locator("#mode").select_option("journey")
        frame.evaluate("""() => {
          window.regionSamples = [];
          const audio = document.querySelector('audio');
          function sample() {
            window.regionSamples.push({time: audio.currentTime,
              row: document.querySelector('#timeline tr.active')?.dataset.cellId,
              marker: document.querySelector('.cell.active')?.dataset.cellId,
              date: document.querySelector('#step-date').textContent,
              paused: audio.paused, status: document.querySelector('#status').textContent});
            if (!audio.ended) requestAnimationFrame(sample);
          }
          requestAnimationFrame(sample);
        }""")
        frame.locator("#toggle").press("Enter")
        frame.wait_for_function("document.querySelector('audio').ended", timeout=35_000)
        samples = frame.evaluate("window.regionSamples")
        checked = set()
        for sample in samples:
            current = sample["time"]
            if current < .05 or current > 27.95 or abs(current - round(current / .5) * .5) < .05:
                continue
            index = int(current / .5)
            step = expected[index]
            assert sample["row"] == sample["marker"] == step["cell_id"], sample
            assert sample["date"] == step["date"], sample
            assert not sample["paused"]
            if index == 26:
                assert "нет данных → пауза" in sample["status"]
            checked.add(index)
        assert checked == set(range(56))
        assert media(frame)["time"] == 28
        expect(frame.locator(".cell.active")).to_have_count(0)
        expect(frame.locator("#step-date")).to_have_text("2026-11-13")
        frame.locator("#toggle").press("Enter")
        expect(frame.locator(".cell.active")).to_have_attribute("data-cell-id", "AKM-001")
        expect(frame.locator("#step-date")).to_have_text("2026-04-15")
        frame.locator("#toggle").press("Space")
