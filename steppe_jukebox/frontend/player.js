/* One audio clock; language changes update text without touching the transport. */
(() => {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const audio = $("audio"), toggle = $("toggle"), select = $("season");
  const languageSelect = $("language");
  const modeSelect = $("mode");
  const svgNS = "http://www.w3.org/2000/svg";
  const storageKey = "steppe-jukebox.language";
  const supported = ["kk", "en", "ru"];
  let data, season, revision;
  let mode = "fixed";
  let language = "en", preference = "auto";
  let buttonState = "play", audioError = null;
  let generation = 0, started = false, wantsPlayback = false;
  let frame = null, activeIndex = -1;
  let rows = [], markers = [];
  let mapGeometry = null, renderedMapWidth = 0;
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

  const numberLocale = () => ({kk: "kk-KZ", en: "en-GB", ru: "ru-RU"}[language]);

  function seconds(value) {
    return value.toLocaleString(numberLocale(), {minimumFractionDigits: 1, maximumFractionDigits: 1});
  }

  const seasonName = () => data.translations[language][season.key] ?? season.name;
  const placeName = (slot) => slot.landmark ? (data.translations[language][slot.landmark] ?? slot.landmark) : t("route_point");

  function renderCurrentStep(index) {
    const slot = season.intervals[index], cell = data.route[index];
    $("step-date").textContent = slot.date;
    $("step-date").setAttribute("datetime", slot.date);
    const coordinate = (value) => value.toLocaleString(numberLocale(), {maximumFractionDigits: 4});
    $("step-place").textContent = t("step_coordinates", {place: placeName(slot), cell: slot.cell_id, lat: coordinate(cell.lat), lon: coordinate(cell.lon)});
    const distance = (value) => value.toLocaleString(numberLocale(), {minimumFractionDigits: 1, maximumFractionDigits: 1});
    $("step-position").textContent = t("journey_position", {index: index + 1, total: rows.length, distance: distance(slot.distance_km), total_distance: distance(season.distance_km)});
  }

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

  function sizeMarker(marker, active) {
    const size = active && marker.classList.contains("compact") ? 14 : Number(marker.dataset.size);
    const rect = marker.querySelector("rect");
    for (const [key, value] of Object.entries({x: -size / 2, y: -size / 2, width: size, height: size, rx: Math.min(4, size / 4)})) {
      rect.setAttribute(key, value);
    }
  }

  function highlightMarker(index) {
    if (!markers[index]) return;
    markers[index].classList.add("active");
    sizeMarker(markers[index], true);
    $("map-content").append(markers[index]);
  }

  function setActive(index) {
    if (index === activeIndex) return;
    if (activeIndex >= 0) {
      rows[activeIndex]?.classList.remove("active");
      rows[activeIndex]?.removeAttribute("aria-current");
      markers[activeIndex]?.classList.remove("active");
      if (markers[activeIndex]) sizeMarker(markers[activeIndex], false);
    }
    activeIndex = index;
    if (index >= 0) {
      rows[index].classList.add("active");
      rows[index].setAttribute("aria-current", "step");
      // SVG paints in DOM order: the current cell must stay above nearby cells.
      highlightMarker(index);
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
    if (mode === "journey") renderCurrentStep(audio.ended ? rows.length - 1 : Math.max(0, index));
    let status = t(audio.ended ? "ended" : "ready");
    if (!audio.ended && index >= 0) {
      const slot = season.intervals[index];
      const note = slot.note ? t("class_note", {value: slot.ndvi_class, note: slot.note}) : t("missing_rest");
      status = t(mode === "journey" ? "journey_status" : "status_slot", {phase: t(audio.paused && !wantsPlayback ? "paused" : "playing"),
        cell: slot.cell_id, note, index: index + 1, total: rows.length, date: slot.date, place: mode === "journey" ? placeName(slot) : ""});
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

  function coordinateTicks(min, max, count) {
    const rawStep = (max - min) / Math.max(1, count - 1);
    const magnitude = 10 ** Math.floor(Math.log10(rawStep));
    let step = [1, 2, 5, 10].find((multiple) => multiple * magnitude >= rawStep) * magnitude;
    // A rounded step can leave only one tick in a narrow, offset range.
    while (Math.floor(max / step + 1e-9) - Math.ceil(min / step - 1e-9) + 1 < 2) step /= 2;
    let precision = Math.max(0, -Math.floor(Math.log10(step)));
    while (Math.abs(Number(step.toFixed(precision)) - step) > step * 1e-8) precision++;
    const first = Math.ceil(min / step - 1e-9) * step;
    const ticks = [];
    for (let index = 0; index < 50; index++) {
      const value = first + index * step;
      if (value > max + step * 1e-9) break;
      const coordinate = Math.abs(value) < step * 1e-8 ? 0 : Number(value.toFixed(precision));
      ticks.push({value: coordinate, label: `${coordinate.toLocaleString(numberLocale(), {
        minimumFractionDigits: precision, maximumFractionDigits: precision, useGrouping: false})}°`});
    }
    return ticks;
  }

  function renderAxes() {
    if (!mapGeometry) return;
    const {left, right, top, bottom, height, projectX, projectY, longitudeRange, latitudeRange} = mapGeometry;
    const axes = $("map-axes"), grid = $("map-grid");
    axes.replaceChildren();
    grid.replaceChildren();
    axes.append(svgElement("path", {d: `M ${left} ${top} V ${bottom} H ${right}`, class: "axis-line"}));
    const xTicks = coordinateTicks(...longitudeRange, Math.max(2, Math.min(6, Math.floor((right - left) / 90) + 1)));
    const yTicks = coordinateTicks(...latitudeRange, Math.max(2, Math.floor((bottom - top) / 50) + 1));
    for (const tick of xTicks) {
      const x = projectX(tick.value);
      grid.append(svgElement("line", {x1: x, y1: top, x2: x, y2: bottom, class: "grid-line"}));
      const group = svgElement("g", {class: "axis-tick", "data-axis": "longitude", "data-value": tick.value});
      const text = svgElement("text", {x, y: bottom + 24, "text-anchor": "middle"});
      text.textContent = tick.label;
      group.append(svgElement("line", {x1: x, y1: bottom, x2: x, y2: bottom + 6, class: "axis-line"}), text);
      axes.append(group);
    }
    for (const tick of yTicks) {
      const y = projectY(tick.value);
      grid.append(svgElement("line", {x1: left, y1: y, x2: right, y2: y, class: "grid-line"}));
      const group = svgElement("g", {class: "axis-tick", "data-axis": "latitude", "data-value": tick.value});
      const text = svgElement("text", {x: left - 10, y, "text-anchor": "end", "dominant-baseline": "central"});
      text.textContent = tick.label;
      group.append(svgElement("line", {x1: left - 6, y1: y, x2: left, y2: y, class: "axis-line"}), text);
      axes.append(group);
    }
    $("longitude-label").setAttribute("x", (left + right) / 2);
    $("longitude-label").setAttribute("y", height - 12);
    $("longitude-label").textContent = t("longitude_axis");
    $("latitude-label").setAttribute("transform", `translate(18,${(top + bottom) / 2}) rotate(-90)`);
    $("latitude-label").textContent = t("latitude_axis");
  }

  function drawRoute() {
    const map = $("route-map");
    const viewWidth = Math.max(280, map.clientWidth), viewHeight = map.clientHeight || 340;
    renderedMapWidth = map.clientWidth;
    map.setAttribute("viewBox", `0 0 ${viewWidth} ${viewHeight}`);
    const left = 100, right = viewWidth - 22, top = 22, bottom = viewHeight - 66;
    const content = $("map-content");
    content.replaceChildren();
    const lats = data.route.map((cell) => cell.lat), lons = data.route.map((cell) => cell.lon);
    const minLat = Math.min(...lats), maxLat = Math.max(...lats);
    const minLon = Math.min(...lons), maxLon = Math.max(...lons);
    const cosLat = Math.max(0.01, Math.cos((minLat + maxLat) / 2 * Math.PI / 180));
    // Minimum extent provides context for a single point or a flat route.
    const width = Math.max(maxLon - minLon, 0.02) * cosLat, height = Math.max(maxLat - minLat, 0.02);
    const scale = Math.min((right - left - 40) / width, (bottom - top - 40) / height);
    const centerX = (left + right) / 2, centerY = (top + bottom) / 2;
    const centerLon = (minLon + maxLon) / 2, centerLat = (minLat + maxLat) / 2;
    const projectX = (lon) => centerX + (lon - centerLon) * cosLat * scale;
    const projectY = (lat) => centerY - (lat - centerLat) * scale;
    mapGeometry = {left, right, top, bottom, height: viewHeight, projectX, projectY,
      longitudeRange: [Math.max(-180, centerLon + (left - centerX) / (cosLat * scale)), Math.min(180, centerLon + (right - centerX) / (cosLat * scale))],
      latitudeRange: [Math.max(-90, centerLat - (bottom - centerY) / scale), Math.min(90, centerLat - (top - centerY) / scale)]};
    renderAxes();
    const points = data.route.map((cell) => [projectX(cell.lon), projectY(cell.lat)]);
    content.append(svgElement("polyline", {points: points.map((point) => point.join(",")).join(" "), class: "route-line"}));
    const spacing = points.slice(1).map(([x, y], i) => Math.hypot(x - points[i][0], y - points[i][1])).filter((distance) => distance > 0);
    const markerSize = Math.min(26, Math.max(1.25, Math.min(...spacing) * 0.8));
    const compact = markerSize < 18;
    markers = points.map(([x, y], index) => {
      const slot = season.intervals[index];
      const color = slot.ndvi_class ? data.scale[slot.ndvi_class - 1].color : data.missing_color;
      const group = svgElement("g", {class: compact ? "cell compact" : "cell", "data-cell-id": slot.cell_id,
        "data-size": markerSize, transform: `translate(${x},${y})`});
      const text = svgElement("text", {x: compact ? 16 : 0, y: 0});
      text.textContent = index + 1;
      const rect = svgElement("rect", {fill: color});
      rect.style.setProperty("--cell-stroke", compact ? 0.3 : 2);
      group.append(svgElement("title", {}), rect, text);
      sizeMarker(group, false);
      content.append(group);
      return group;
    });
    highlightMarker(activeIndex);
  }

  function drawTable() {
    const body = $("timeline").querySelector("tbody");
    body.replaceChildren();
    rows = season.intervals.map((slot) => {
      const row = document.createElement("tr");
      row.dataset.cellId = slot.cell_id;
      for (let i = 0; i < (mode === "journey" ? 6 : 5); i++) row.append(document.createElement("td"));
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
    $("season-field").hidden = mode === "journey";
    $("journey-caveat").hidden = mode !== "journey";
    $("current-step").hidden = mode !== "journey";
    $("date-column").hidden = mode !== "journey";
    $("audio").setAttribute("aria-label", t(mode === "journey" ? "journey_audio_label" : "audio_label"));
    renderAxes();
    for (const option of select.options) option.textContent = t(option.value);
    setButton(buttonState);
    $("tempo").textContent = t("tempo", {bpm: data.bpm, step: seconds(data.step_seconds)});
    const info = $("season-info");
    info.textContent = mode === "journey" ? t("journey_summary", {start: season.intervals[0].date, end: season.intervals.at(-1).date, count: rows.length}) + " · " : `${seasonName()} · ${season.date || t("no_date")} · `;
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
      if (mode === "journey") values.splice(2, 0, slot.date);
      [...rows[index].children].forEach((td, i) => { td.textContent = values[i]; });
      markers[index].querySelector("title").textContent = `${slot.cell_id}${slot.date ? ` · ${slot.date} · ${placeName(slot)}` : ""}: ${slot.note || t("missing_rest")}`;
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

  function activateTrack(track) {
    resetTransport(); // Synchronous: old audio stops before loading the new source.
    season = track;
    if (mode === "fixed") select.value = season.key;
    audio.src = season.audio_src;
    audio.load();
    $("progress").max = season.duration_s;
    drawRoute();
    drawTable();
    refreshText();
  }

  function chooseSeason(key) {
    activateTrack(data.seasons.find((item) => item.key === key));
  }

  function chooseMode(value) {
    mode = value === "journey" && data.journey ? "journey" : "fixed";
    modeSelect.value = mode;
    activateTrack(mode === "journey" ? data.journey : data.seasons.find((item) => item.key === select.value) ?? data.seasons[0]);
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
    $("mode-field").hidden = !data.journey;
    chooseMode("fixed");
  }

  toggle.addEventListener("click", () => wantsPlayback || !audio.paused ? pause() : play());
  select.addEventListener("change", () => chooseSeason(select.value));
  modeSelect.addEventListener("change", () => chooseMode(modeSelect.value));
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
    if (!audio.ended) return; // Ignore an old track's queued event after a switch.
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
  new ResizeObserver(() => {
    if (season && $("route-map").clientWidth !== renderedMapWidth) drawRoute();
  }).observe($("route-map"));
  send("streamlit:componentReady", {apiVersion: 1});
})();
