"""Real media-clock checks: python -m pytest -m browser (Chromium required)."""

import os
import socket
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

import pytest
from playwright.sync_api import expect, sync_playwright


pytestmark = pytest.mark.browser
ROOT = Path(__file__).resolve().parents[1]


@contextmanager
def running_app(directory, log_path):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    url = f"http://127.0.0.1:{port}"
    with log_path.open("w+") as log:
        server = subprocess.Popen([
            sys.executable, "-m", "streamlit", "run", "app.py", "--server.headless", "true",
            "--server.address", "127.0.0.1", "--server.port", str(port),
            "--browser.gatherUsageStats", "false", "--server.fileWatcherType", "none",
        ], cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
            env={**os.environ, "STEPPE_DATA_DIR": str(directory)})
        try:
            for _ in range(150):
                try:
                    with urlopen(url + "/_stcore/health", timeout=1) as response:
                        if response.status == 200:
                            break
                except (URLError, TimeoutError):
                    pass
                if server.poll() is not None:
                    pytest.fail(log_path.read_text())
                time.sleep(0.1)
            else:
                pytest.fail("Streamlit did not start: " + log_path.read_text())
            yield url
        finally:
            server.terminate()
            server.wait(timeout=10)


@pytest.fixture(scope="module")
def app_url(tmp_path_factory):
    if url := os.environ.get("STEPPE_TEST_URL"):
        yield url
        return
    with running_app(ROOT / "data" / "synthetic", tmp_path_factory.mktemp("streamlit") / "server.log") as url:
        yield url


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as playwright:
        executable = os.environ.get("STEPPE_BROWSER_EXECUTABLE")
        instance = playwright.chromium.launch(
            executable_path=executable or None,
            headless=True,
            args=["--autoplay-policy=document-user-activation-required", "--disable-dev-shm-usage"],
        )
        yield instance
        instance.close()


def player_frame(page):
    iframe = page.locator("iframe").first
    iframe.wait_for(timeout=30_000)
    frame = iframe.element_handle().content_frame()
    expect(frame.locator("#interface")).to_be_visible(timeout=30_000)
    return frame


@contextmanager
def localized_ui(browser, app_url, locale="ru-RU", init_script=None):
    context = browser.new_context(viewport={"width": 1280, "height": 1000}, locale=locale)
    if init_script:
        context.add_init_script(init_script)
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(app_url)
    try:
        yield page, player_frame(page)
    finally:
        context.close()
    assert errors == [], errors


@pytest.fixture
def ui(browser, app_url):
    with localized_ui(browser, app_url) as (page, frame):
        expect(frame.get_by_text("ТЕСТОВЫЕ ДАННЫЕ", exact=False)).to_be_visible()
        expect(frame.get_by_role("button", name="Запустить", exact=True)).to_be_visible()
        yield page, frame


def media(frame):
    return frame.locator("audio").evaluate("(audio) => ({time: audio.currentTime, paused: audio.paused, ended: audio.ended, error: audio.error?.code})")


def assert_reset(frame):
    assert media(frame)["paused"]
    assert media(frame)["time"] == 0
    expect(frame.locator("#timeline tr.active")).to_have_count(0)
    expect(frame.locator("#route-map .cell.active")).to_have_count(0)
    expect(frame.locator("#toggle")).to_have_text("Запустить")


def test_keyboard_season_start_pause_and_resume(ui):
    page, frame = ui
    select = frame.get_by_label("Сезон", exact=True)
    button = frame.locator("#toggle")  # Its accessible name changes with transport state.
    assert_reset(frame)  # Loading the page must not autoplay.
    select.focus()
    select.press("ArrowDown")
    expect(select).to_have_value("summer")
    assert_reset(frame)
    select.press("Tab")
    expect(button).to_be_focused()
    button.press("Enter")
    frame.wait_for_function("document.querySelector('audio').currentTime > 0.1")
    assert not media(frame)["paused"]
    expect(frame.locator("#timeline tr.active")).to_have_attribute("data-cell-id", "cell-01")
    expect(frame.locator("#status")).to_contain_text("E4")
    button.press("Space")
    paused = media(frame)
    active = frame.locator("#timeline tr.active").get_attribute("data-cell-id")
    assert paused["paused"]
    page.wait_for_timeout(600)
    assert media(frame)["time"] == paused["time"]
    expect(frame.locator("#timeline tr.active")).to_have_attribute("data-cell-id", active)
    expect(frame.locator("#status")).to_contain_text("На паузе")
    button.press("Enter")
    frame.wait_for_function("document.querySelector('audio').currentTime > " + str(paused["time"] + 0.15))
    button.press("Space")
    select.focus()
    select.press("ArrowUp")
    expect(select).to_have_value("spring")
    assert_reset(frame)


def test_entire_route_highlights_from_real_audio_clock_including_silence_and_replay(ui):
    _, frame = ui
    frame.evaluate("""() => {
      window.observations = [];
      const audio = document.querySelector('audio');
      function sample() {
        const row = document.querySelector('#timeline tr.active');
        const rowRect = row?.getBoundingClientRect();
        const containerRect = document.querySelector('.table-scroll').getBoundingClientRect();
        window.observations.push({time: audio.currentTime,
          row: row?.dataset.cellId,
          marker: document.querySelector('#route-map .cell.active')?.dataset.cellId,
          visible: rowRect && rowRect.top >= containerRect.top && rowRect.bottom <= containerRect.bottom,
          status: document.querySelector('#status').textContent});
        if (!audio.ended) requestAnimationFrame(sample);
      }
      requestAnimationFrame(sample);
    }""")
    frame.locator("#toggle").press("Enter")
    frame.wait_for_function("document.querySelector('audio').ended", timeout=10_000)
    samples = frame.evaluate("window.observations")
    checked = set()
    for sample in samples:
        current = sample["time"]
        # Independent rAF callbacks may straddle a slot boundary by one frame.
        if current < 0.05 or current > 5.95 or abs(current - round(current / 0.5) * 0.5) < 0.04:
            continue
        index = int(current / 0.5)
        cell_id = f"cell-{index + 1:02}"
        assert sample["row"] == sample["marker"] == cell_id, sample
        assert sample["visible"], sample
        if index == 5:
            assert "нет данных → пауза" in sample["status"]
        checked.add(index)
    assert checked == set(range(12))
    assert media(frame)["time"] == 6
    assert not media(frame)["error"]
    expect(frame.locator("#timeline tr.active")).to_have_count(0)
    expect(frame.locator("#route-map .cell.active")).to_have_count(0)
    expect(frame.locator("#toggle")).to_have_text("Запустить снова")
    frame.locator("#toggle").press("Enter")
    frame.wait_for_function("!document.querySelector('audio').paused && document.querySelector('audio').currentTime > 0.05")
    expect(frame.locator("#timeline tr.active")).to_have_attribute("data-cell-id", "cell-01")
    frame.locator("#toggle").press("Space")


def test_change_season_while_playing_stops_old_audio_and_requires_new_gesture(ui):
    page, frame = ui
    old_source = frame.locator("audio").get_attribute("src")
    frame.locator("#toggle").click()
    frame.wait_for_function("document.querySelector('audio').currentTime > 0.65")
    select = frame.get_by_label("Сезон", exact=True)
    select.focus()
    select.press("ArrowDown")
    expect(select).to_have_value("summer")
    assert_reset(frame)
    assert frame.locator("audio").get_attribute("src") != old_source
    expect(frame.locator("audio")).to_have_count(1)
    page.wait_for_timeout(700)
    assert_reset(frame)
    expect(frame.locator("#error")).to_be_hidden()
    frame.locator("#toggle").press("Enter")
    frame.wait_for_function("document.querySelector('audio').currentTime > 0.05")
    expect(frame.locator("#status")).to_contain_text("E4")
    select.focus()
    select.press("ArrowUp")
    assert_reset(frame)


@pytest.mark.parametrize("action", ["season", "pause"])
def test_pending_play_promise_cannot_restart_superseded_playback(ui, action):
    page, frame = ui
    frame.evaluate("""(action) => {
      const button = document.querySelector('#toggle');
      button.addEventListener('click', () => {
        if (action === 'season') {
          const select = document.querySelector('#season');
          select.value = 'summer';
          select.dispatchEvent(new Event('change'));
        } else button.dispatchEvent(new MouseEvent('click', {bubbles: true}));
      }, {once: true});
    }""", action)
    frame.locator("#toggle").press("Enter")
    page.wait_for_timeout(600)
    assert media(frame)["paused"]
    expect(frame.locator("#error")).to_be_hidden()
    if action == "season":
        expect(frame.locator("#season")).to_have_value("summer")
        assert_reset(frame)


def test_layout_and_accessible_scale_on_desktop_and_mobile(ui):
    page, frame = ui
    results = ROOT / "test-results"
    results.mkdir(exist_ok=True)
    frame.get_by_text("Шкала: цвет → класс → нота", exact=True).click()
    expect(frame.locator("#scale-description")).to_be_visible()
    expect(frame.get_by_role("list", name="Цвета и ноты классов NDVI").get_by_role("listitem")).to_have_count(6)
    expect(frame.get_by_role("img", name="Маршрут по ячейкам")).to_be_visible()
    expect(frame.get_by_label("Сезон", exact=True)).to_be_visible()
    for name, viewport in [("desktop", {"width": 1280, "height": 1000}), ("mobile", {"width": 390, "height": 844})]:
        page.set_viewport_size(viewport)
        page.wait_for_timeout(250)
        assert frame.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        dimensions = frame.evaluate("({content: document.body.scrollHeight, viewport: window.innerHeight})")
        assert dimensions["content"] <= dimensions["viewport"] + 2, dimensions
        page.screenshot(path=str(results / f"{name}.png"), full_page=True)


@pytest.mark.parametrize("locale,language,play,season,warning", [
    ("kk-KZ", "kk", "Ойнату", "Көктем", "СЫНАҚ ДЕРЕКТЕРІ"),
    ("kk", "kk", "Ойнату", "Көктем", "СЫНАҚ ДЕРЕКТЕРІ"),
    ("en-GB", "en", "Play", "Spring", "TEST DATA"),
    ("en-US", "en", "Play", "Spring", "TEST DATA"),
    ("ru-RU", "ru", "Запустить", "Весна", "ТЕСТОВЫЕ ДАННЫЕ"),
    ("fr-FR", "en", "Play", "Spring", "TEST DATA"),
])
def test_default_language_comes_from_browser_locale(browser, app_url, locale, language, play, season, warning):
    with localized_ui(browser, app_url, locale) as (_, frame):
        expect(frame.locator("html")).to_have_attribute("lang", language)
        expect(frame.locator("#language")).to_have_value("auto")
        expect(frame.get_by_role("button", name=play, exact=True)).to_be_visible()
        expect(frame.locator("#season option:checked")).to_have_text(season)
        expect(frame.locator("#test-warning")).to_contain_text(warning)
        assert media(frame)["paused"]
        assert media(frame)["time"] == 0
        if language == "en":
            assert "0.0 / 6.0 s" == frame.locator("#clock").inner_text()
            import re
            assert not re.search("[А-Яа-яӘәҒғҚқҢңӨөҰұҮүҺһІі]", frame.locator("#player").inner_text())
            assert not re.search("[А-Яа-яӘәҒғҚқҢңӨөҰұҮүҺһІі]", frame.locator("#description").inner_text())


def test_system_language_uses_ordered_preferences_and_tracks_changes(browser, app_url):
    script = "Object.defineProperty(navigator, 'languages', {configurable: true, get: () => ['fr-FR', 'kk-KZ', 'en-US']});"
    with localized_ui(browser, app_url, "fr-FR", script) as (_, frame):
        expect(frame.locator("html")).to_have_attribute("lang", "kk")
        frame.evaluate("""() => {
          Object.defineProperty(navigator, 'languages', {configurable: true, get: () => ['en-GB']});
          dispatchEvent(new Event('languagechange'));
        }""")
        expect(frame.locator("html")).to_have_attribute("lang", "en")
        frame.locator("#language").select_option("ru")
        frame.evaluate("dispatchEvent(new Event('languagechange'))")
        expect(frame.locator("html")).to_have_attribute("lang", "ru")
        frame.locator("#language").select_option("auto")
        expect(frame.locator("html")).to_have_attribute("lang", "en")


def test_manual_language_survives_reload_and_can_return_to_system(browser, app_url):
    with localized_ui(browser, app_url, "kk-KZ") as (page, frame):
        frame.locator("#language").select_option("en")
        page.reload()
        frame = player_frame(page)
        expect(frame.locator("html")).to_have_attribute("lang", "en")
        expect(frame.locator("#language")).to_have_value("en")
        frame.locator("#language").select_option("auto")
        expect(frame.locator("html")).to_have_attribute("lang", "kk")
        page.reload()
        expect(player_frame(page).locator("html")).to_have_attribute("lang", "kk")


def test_language_switching_preserves_audio_and_paused_position(ui):
    _, frame = ui
    frame.locator("#season").select_option("summer")
    frame.locator("#toggle").press("Enter")
    frame.wait_for_function("document.querySelector('audio').currentTime > 0.65")
    frame.evaluate("""() => {
      const audio = document.querySelector('audio');
      window.originalSource = audio.src;
      window.originalRows = [...document.querySelectorAll('#timeline tbody tr')];
      window.transportEvents = [];
      for (const type of ['play', 'pause', 'emptied', 'loadstart']) audio.addEventListener(type, () => window.transportEvents.push(type));
    }""")
    before = media(frame)["time"]
    language = frame.get_by_label("Язык", exact=True)
    language.focus()
    language.press("ArrowDown")  # Native keyboard selection: system -> Kazakh.
    expect(frame.locator("#language")).to_have_value("kk")
    expect(frame.get_by_label("Тіл", exact=True)).to_be_focused()
    expect(frame.get_by_role("button", name="Кідірту", exact=True)).to_be_visible()
    expect(frame.locator("#season option:checked")).to_have_text("Жаз")
    expect(frame.locator("#status")).to_contain_text("Ойнатылуда")
    assert not media(frame)["paused"]
    assert media(frame)["time"] >= before
    assert frame.evaluate("document.querySelector('audio').src === window.originalSource")
    assert frame.evaluate("window.originalRows.every((row, i) => row === document.querySelectorAll('#timeline tbody tr')[i])")
    assert frame.evaluate("window.transportEvents") == []
    frame.locator("#toggle").press("Space")
    paused = media(frame)["time"]
    active = frame.locator("#timeline tr.active").get_attribute("data-cell-id")
    for language, resume, phase in [("en", "Resume", "Paused"), ("ru", "Продолжить", "На паузе"), ("kk", "Жалғастыру", "Кідіртілді")]:
        frame.locator("#language").select_option(language)
        assert media(frame)["time"] == paused
        assert media(frame)["paused"]
        expect(frame.locator("#timeline tr.active")).to_have_attribute("data-cell-id", active)
        expect(frame.locator("#route-map .cell.active")).to_have_attribute("data-cell-id", active)
        expect(frame.get_by_role("button", name=resume, exact=True)).to_be_visible()
        expect(frame.locator("#status")).to_contain_text(phase)
    frame.locator("#toggle").press("Enter")
    frame.wait_for_function("document.querySelector('audio').currentTime > " + str(paused + 0.1))
    frame.locator("#season").select_option("spring")
    assert media(frame)["paused"] and media(frame)["time"] == 0
    expect(frame.locator("#timeline tr.active")).to_have_count(0)
    expect(frame.get_by_role("button", name="Ойнату", exact=True)).to_be_visible()


def test_localized_play_failure_can_be_translated_and_retried(browser, app_url):
    with localized_ui(browser, app_url, "en-GB") as (_, frame):
        frame.evaluate("() => { document.querySelector('audio').play = () => Promise.reject(new DOMException('Test failure', 'NotAllowedError')); }")
        frame.locator("#toggle").press("Enter")
        expect(frame.get_by_role("alert").filter(has_text="Unable to start audio")).to_be_visible()
        frame.locator("#language").select_option("kk")
        expect(frame.locator("#error")).to_contain_text("Дыбысты ойнату мүмкін болмады")
        assert media(frame)["paused"]
        frame.evaluate("delete document.querySelector('audio').play")
        frame.locator("#toggle").press("Enter")
        frame.wait_for_function("document.querySelector('audio').currentTime > 0.05")
        expect(frame.locator("#error")).to_be_hidden()


def test_csv_errors_keep_language_picker_and_translate_details(browser, tmp_path):
    dataset = tmp_path / "invalid-data"
    dataset.mkdir()
    (dataset / "route.csv").write_text("wrong,header\n")
    with running_app(dataset, tmp_path / "error-server.log") as url:
        with localized_ui(browser, url, "en-US") as (_, frame):
            expect(frame.locator("#data-error")).to_have_text("Data error: route.csv: expected header cell_id,lat,lon")
            expect(frame.locator("#player")).to_be_hidden()
            frame.locator("#language").select_option("kk")
            expect(frame.locator("#data-error")).to_have_text("Деректер қатесі: route.csv: күтілетін тақырып — cell_id,lat,lon")
            frame.locator("#language").select_option("ru")
            expect(frame.locator("#data-error")).to_have_text("Ошибка данных: route.csv: ожидается заголовок cell_id,lat,lon")


@pytest.mark.parametrize("language,label", [("kk", "Тіл"), ("en", "Language")])
def test_translated_ui_fits_mobile_and_exposes_localized_accessibility(browser, app_url, language, label):
    with localized_ui(browser, app_url, language) as (page, frame):
        page.set_viewport_size({"width": 390, "height": 844})
        frame.locator("#scale-details summary").click()
        expect(frame.get_by_label(label, exact=True)).to_be_visible()
        expect(frame.locator("#scale-description")).to_be_visible()
        for selector in ["#audio", "#progress", "#legend", "#interface"]:
            assert frame.locator(selector).get_attribute("aria-label")
        assert frame.evaluate("document.documentElement.scrollWidth <= innerWidth")
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        results = ROOT / "test-results"
        results.mkdir(exist_ok=True)
        frame.locator("#language").scroll_into_view_if_needed()
        page.screenshot(path=str(results / f"{language}-mobile.png"), full_page=True)
