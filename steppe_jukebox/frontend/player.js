/* One audio clock; language changes update text without touching the transport. */
(() => {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const audio = $("audio"), toggle = $("toggle"), select = $("season");
  const languageSelect = $("language");
  const svgNS = "http://www.w3.org/2000/svg";
  const storageKey = "steppe-jukebox.language";
  const supported = ["kk", "en", "ru"];
  let data, season, revision;
  let language = "en", preference = "auto";
  let buttonState = "play", audioError = null;
  let generation = 0, started = false, wantsPlayback = false;
  let frame = null, activeIndex = -1;
  let rows = [], markers = [];
  try {
    const saved = localStorage.getItem(storageKey);
    if (["auto", ...supported].includes(saved)) preference = saved;
  } catch { /* Browser storage may be disabled; switching still works. */ }

  function systemLanguage() {
    for (const locale of [...(navigator.languages || []), navigator.language]) {
      const base = (locale || "").toLowerCase().split(/[-_]/)[0];
      if (supported.includes(base)) return base;
    }
    return "en";
  }

  function t(key, values = {}) {
    const template = data.translations[language][key] ?? data.translations.en[key];
    return template.replace(/\{(\w+)\}/g, (_, name) => String(values[name]));
  }

  function seconds(value) {
    const locale = {kk: "kk-KZ", en: "en-GB", ru: "ru-RU"}[language];
    return value.toLocaleString(locale, {minimumFractionDigits: 1, maximumFractionDigits: 1});
  }

  const seasonName = () => data.translations[language][season.key] ?? season.name;

  function send(type, fields = {}) {
    window.parent.postMessage({isStreamlitMessage: true, type, ...fields}, "*");
  }

  function resize() {
    send("streamlit:setFrameHeight", {height: Math.ceil(document.documentElement.getBoundingClientRect().height)});
  }

  function setButton(state) {
    buttonState = state;
    toggle.textContent = t(state);
  }

  function setActive(index) {
    if (index === activeIndex) return;
    if (activeIndex >= 0) {
      rows[activeIndex]?.classList.remove("active");
      rows[activeIndex]?.removeAttribute("aria-current");
      markers[activeIndex]?.classList.remove("active");
    }
    activeIndex = index;
    if (index >= 0) {
      rows[index].classList.add("active");
      rows[index].setAttribute("aria-current", "step");
      markers[index].classList.add("active");
      const container = rows[index].closest(".table-scroll");
      const rowRect = rows[index].getBoundingClientRect();
      const containerRect = container.getBoundingClientRect();
      if (rowRect.top < containerRect.top || rowRect.bottom > containerRect.bottom) {
        container.scrollTop += rowRect.top - containerRect.top - (container.clientHeight - rowRect.height) / 2;
      }
    }
  }

  function renderPosition() {
    if (!season) return;
    const time = started ? Math.min(audio.currentTime || 0, season.duration_s) : 0;
    $("progress").value = time;
    $("clock").textContent = t("clock", {current: seconds(time), duration: seconds(season.duration_s)});
    // Half-open intervals come from the same sample offsets as the WAV.
    const index = !started || audio.ended ? -1 : season.intervals.findIndex((slot) => time >= slot.start_s && time < slot.end_s);
    setActive(index);
    let status = t(audio.ended ? "ended" : "ready");
    if (!audio.ended && index >= 0) {
      const slot = season.intervals[index];
      const note = slot.note ? t("class_note", {value: slot.ndvi_class, note: slot.note}) : t("missing_rest");
      status = t("status_slot", {phase: t(audio.paused && !wantsPlayback ? "paused" : "playing"),
        cell: slot.cell_id, note, index: index + 1, total: rows.length});
    }
    if ($("status").textContent !== status) $("status").textContent = status;
  }

  function animate() {
    renderPosition();
    frame = audio.paused || audio.ended ? null : requestAnimationFrame(animate);
  }

  function stopAnimation() {
    if (frame !== null) cancelAnimationFrame(frame);
    frame = null;
  }

  async function play() {
    const token = ++generation;
    if (audio.ended || audio.currentTime >= season.duration_s) audio.currentTime = 0;
    started = true;
    wantsPlayback = true;
    audioError = null;
    $("error").hidden = true;
    setButton("pause");
    try {
      await audio.play(); // Direct native button click, including Enter/Space.
      if (token !== generation) return;
      renderPosition();
    } catch {
      if (token !== generation) return;
      wantsPlayback = false;
      audio.pause();
      setButton("play");
      audioError = "play_error";
      refreshText();
    }
  }

  function pause() {
    generation++;
    wantsPlayback = false;
    audio.pause();
    stopAnimation();
    setButton("resume");
    renderPosition();
  }

  function svgElement(name, attributes) {
    const node = document.createElementNS(svgNS, name);
    for (const [key, value] of Object.entries(attributes)) node.setAttribute(key, value);
    return node;
  }

  function drawRoute() {
    const content = $("map-content");
    content.replaceChildren();
    const lats = data.route.map((cell) => cell.lat), lons = data.route.map((cell) => cell.lon);
    const minLat = Math.min(...lats), maxLat = Math.max(...lats);
    const minLon = Math.min(...lons), maxLon = Math.max(...lons);
    const cosLat = Math.max(0.01, Math.cos((minLat + maxLat) / 2 * Math.PI / 180));
    const width = (maxLon - minLon) * cosLat, height = maxLat - minLat;
    const scale = Math.min(620 / (width || 1), 200 / (height || 1));
    const points = data.route.map((cell) => [360 + (cell.lon - (minLon + maxLon) / 2) * cosLat * scale,
      140 - (cell.lat - (minLat + maxLat) / 2) * scale]);
    content.append(svgElement("polyline", {points: points.map((point) => point.join(",")).join(" "), class: "route-line"}));
    markers = points.map(([x, y], index) => {
      const slot = season.intervals[index];
      const color = slot.ndvi_class ? data.scale[slot.ndvi_class - 1].color : data.missing_color;
      const group = svgElement("g", {class: "cell", "data-cell-id": slot.cell_id});
      const text = svgElement("text", {x, y});
      text.textContent = index + 1;
      group.append(svgElement("title", {}), svgElement("rect", {x: x - 13, y: y - 13, width: 26, height: 26, rx: 4, fill: color}), text);
      content.append(group);
      return group;
    });
  }

  function drawTable() {
    const body = $("timeline").querySelector("tbody");
    body.replaceChildren();
    rows = season.intervals.map((slot) => {
      const row = document.createElement("tr");
      row.dataset.cellId = slot.cell_id;
      for (let i = 0; i < 5; i++) row.append(document.createElement("td"));
      body.append(row);
      return row;
    });
    $("timeline").closest(".table-scroll").scrollTop = 0;
  }

  function refreshText() {
    if (!data) return;
    document.documentElement.lang = language;
    document.title = t("page_title");
    document.querySelectorAll("[data-i18n]").forEach((node) => { node.textContent = t(node.dataset.i18n); });
    document.querySelectorAll("[data-i18n-aria]").forEach((node) => { node.setAttribute("aria-label", t(node.dataset.i18nAria)); });
    $("system-language").textContent = t("system_language");
    languageSelect.value = preference;
    $("test-warning").hidden = Boolean(data.error) || !data.is_test;
    $("description").textContent = data.description_i18n?.[language] || data.description || "";
    $("description").hidden = Boolean(data.error) || !$("description").textContent;
    $("data-error").hidden = !data.error;
    $("footer").hidden = Boolean(data.error);
    if (data.error) {
      $("data-error").textContent = t("data_error", {detail: t(`error_${data.error.code}`, data.error.context)});
      resize();
      return;
    }
    if (!season) return;
    for (const option of select.options) option.textContent = t(option.value);
    setButton(buttonState);
    $("tempo").textContent = t("tempo", {bpm: data.bpm, step: seconds(data.step_seconds)});
    const info = $("season-info");
    info.textContent = `${seasonName()} · ${season.date || t("no_date")} · `;
    if (season.source_url) {
      const link = document.createElement("a");
      link.href = season.source_url;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      link.textContent = t("source_link");
      info.append(link);
    } else info.append(document.createTextNode(t(data.is_test ? "test_sequence" : "source_missing")));
    $("timeline-caption").textContent = t("timeline_caption", {season: seasonName()});
    season.intervals.forEach((slot, index) => {
      const values = [index + 1, slot.cell_id, slot.ndvi_class ?? t("missing"), slot.note || t("rest"), `${seconds(slot.start_s)}–${seconds(slot.end_s)}`];
      [...rows[index].children].forEach((td, i) => { td.textContent = values[i]; });
      markers[index].querySelector("title").textContent = `${slot.cell_id}: ${slot.note || t("missing_rest")}`;
    });
    const noteNames = data.translations[language].note_names;
    const notes = data.scale.map((note, index) => t("scale_note", {value: index + 1, label: noteNames[index], note: note.name})).join(", ");
    $("scale-description").textContent = t("scale_description", {notes});
    $("legend").replaceChildren();
    [...data.scale.map((note, i) => ({color: note.color, text: `${i + 1} → ${note.name} (${noteNames[i]})`})),
      {color: data.missing_color, text: t("missing_rest")}].forEach(({color, text}) => {
      const item = document.createElement("li"), swatch = document.createElement("span");
      swatch.className = "swatch";
      swatch.style.backgroundColor = color;
      swatch.setAttribute("aria-hidden", "true");
      item.append(swatch, document.createTextNode(text));
      $("legend").append(item);
    });
    $("error").hidden = !audioError;
    if (audioError) $("error").textContent = t(audioError);
    renderPosition();
    resize();
  }

  function chooseLanguage(choice, persist = true) {
    preference = choice;
    language = preference === "auto" ? systemLanguage() : preference;
    if (persist) {
      try { localStorage.setItem(storageKey, preference); } catch { /* Optional storage. */ }
    }
    // No source reload, play/pause call, or replacement of active rows/markers.
    refreshText();
  }

  function resetTransport() {
    generation++;
    wantsPlayback = false;
    started = false;
    audio.pause();
    stopAnimation();
    setActive(-1);
    audio.removeAttribute("src");
    audio.load();
    season = null;
    rows = [];
    markers = [];
    buttonState = "play";
    audioError = null;
  }

  function chooseSeason(key) {
    resetTransport(); // Synchronous: old audio stops before loading the new source.
    season = data.seasons.find((item) => item.key === key);
    select.value = season.key;
    audio.src = season.audio_src;
    audio.load();
    $("progress").max = season.duration_s;
    drawRoute();
    drawTable();
    refreshText();
  }

  function render(payload) {
    if (payload.revision === revision) return;
    revision = payload.revision;
    data = payload;
    language = preference === "auto" ? systemLanguage() : preference;
    $("interface").hidden = false;
    $("player").hidden = Boolean(data.error);
    if (data.error) {
      resetTransport();
      refreshText();
      return;
    }
    select.replaceChildren();
    for (const item of data.seasons) {
      const option = document.createElement("option");
      option.value = item.key;
      select.append(option);
    }
    chooseSeason(data.seasons[0].key);
  }

  toggle.addEventListener("click", () => wantsPlayback || !audio.paused ? pause() : play());
  select.addEventListener("change", () => chooseSeason(select.value));
  languageSelect.addEventListener("change", () => chooseLanguage(languageSelect.value));
  window.addEventListener("languagechange", () => {
    if (preference === "auto") chooseLanguage("auto", false);
  });
  audio.addEventListener("playing", () => {
    stopAnimation();
    frame = requestAnimationFrame(animate);
  });
  audio.addEventListener("timeupdate", renderPosition);
  audio.addEventListener("seeked", renderPosition);
  audio.addEventListener("pause", renderPosition);
  audio.addEventListener("ended", () => {
    wantsPlayback = false;
    stopAnimation();
    setButton("replay");
    renderPosition();
  });
  audio.addEventListener("error", () => {
    if (!audio.getAttribute("src") || !audio.error) return;
    generation++;
    wantsPlayback = false;
    stopAnimation();
    setButton("play");
    audioError = "load_error";
    refreshText();
  });
  window.addEventListener("pagehide", () => { generation++; audio.pause(); stopAnimation(); });
  window.addEventListener("message", (event) => {
    if (event.source === window.parent && event.data?.type === "streamlit:render" && event.data.args?.payload) render(event.data.args.payload);
  });
  new ResizeObserver(resize).observe(document.body);
  send("streamlit:componentReady", {apiVersion: 1});
})();
