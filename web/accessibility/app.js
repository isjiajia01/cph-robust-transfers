const state = {
  appState: "idle",
  bootstrap: null,
  originSuggestions: [],
  selectedOrigin: null,
  activeStopId: null,
  reachability: null,
  overlays: { hubs: [], vulnerable_nodes: [] },
  overlayVisibility: { hubs: true, vulnerable: true },
  map: null,
  layers: {
    reachableCluster: null,
    origin: null,
    overlayHubs: null,
    overlayVulnerable: null,
  },
  pager: {
    page: 1,
    perPage: 80,
  },
  controls: {
    sortBy: "quality_desc",
    reliabilityFilter: "all",
    bucketFilter: "all",
    directOnly: false,
    viewMode: "scheduled",
  },
};

const dom = {
  form: document.getElementById("query-form"),
  originInput: document.getElementById("origin-input"),
  originSuggestions: document.getElementById("origin-suggestions"),
  departAt: document.getElementById("depart-at"),
  maxMinutes: document.getElementById("max-minutes"),
  maxChanges: document.getElementById("max-changes"),
  resultsStatus: document.getElementById("results-status"),
  resultsList: document.getElementById("results-list"),
  detailCard: document.getElementById("detail-card"),
  summaryCards: document.getElementById("summary-cards"),
  freshnessBadge: document.getElementById("freshness-badge"),
  toggleHubs: document.getElementById("toggle-hubs"),
  toggleVulnerable: document.getElementById("toggle-vulnerable"),
  bucketBars: document.getElementById("bucket-bars"),
  windowNote: document.getElementById("window-note"),
  paginationLabel: document.getElementById("pagination-label"),
  prevPage: document.getElementById("prev-page"),
  nextPage: document.getElementById("next-page"),
  sortBy: document.getElementById("sort-by"),
  qualityFilter: document.getElementById("quality-filter"),
  bucketFilter: document.getElementById("bucket-filter"),
  directOnly: document.getElementById("direct-only"),
  viewMode: document.getElementById("view-mode"),
  shareLink: document.getElementById("share-link"),
  shareStatus: document.getElementById("share-status"),
  overlayScopeNote: document.getElementById("overlay-scope-note"),
  viewModeCopy: document.getElementById("view-mode-copy"),
  legendCopy: document.getElementById("legend-copy"),
};

let searchTimer = null;

const travelBucketConfig = [
  { key: "0-15", label: "0-15", color: "#2dd4bf" },
  { key: "16-30", label: "16-30", color: "#38bdf8" },
  { key: "31-45", label: "31-45", color: "#f59e0b" },
  { key: "46+", label: "46+", color: "#ef4444" },
];

const lossBucketConfig = [
  { key: "0-5", label: "0-5", color: "#94a3b8" },
  { key: "6-10", label: "6-10", color: "#38bdf8" },
  { key: "11-15", label: "11-15", color: "#f59e0b" },
  { key: "16+", label: "16+", color: "#ef4444" },
];

function bucketKey(minutes) {
  if (minutes <= 15) return "0-15";
  if (minutes <= 30) return "16-30";
  if (minutes <= 45) return "31-45";
  return "46+";
}

function lossBucketKey(minutes) {
  if (minutes <= 5) return "0-5";
  if (minutes <= 10) return "6-10";
  if (minutes <= 15) return "11-15";
  return "16+";
}

function activeBucketConfig(viewMode) {
  return viewMode === "loss" ? lossBucketConfig : travelBucketConfig;
}

function displayMinutesForView(item, viewMode) {
  if (viewMode === "robust") return item.robust_travel_time_min ?? item.travel_time_min ?? 999;
  if (viewMode === "loss") return item.accessibility_loss_min ?? 0;
  return item.scheduled_travel_time_min ?? item.travel_time_min ?? 999;
}

function filterStopsForView(stops, viewMode) {
  if (viewMode !== "loss") return stops;
  return stops.filter((stop) => Boolean(stop.accessibility_loss_flag));
}

function updateViewModeCopy(viewMode) {
  if (viewMode === "robust") {
    dom.viewModeCopy.textContent = "Robust shows scheduled travel time plus the current p95 delay-risk overlay.";
    dom.legendCopy.textContent = "Robust view colors stops by risk-adjusted travel time buckets.";
    return;
  }
  if (viewMode === "loss") {
    dom.viewModeCopy.textContent = "Accessibility loss isolates stops that were reachable on schedule but fall outside the time budget once delay risk is applied.";
    dom.legendCopy.textContent = "Accessibility loss view colors stops by added minutes caused by uncertainty, and only keeps affected stops on the map.";
    return;
  }
  dom.viewModeCopy.textContent = "Scheduled shows base travel time, robust adds delay risk, and accessibility loss isolates stops pushed beyond the time budget by uncertainty.";
  dom.legendCopy.textContent = "Scheduled view colors stops by scheduled travel time buckets.";
}

function colorScale(minutes) {
  return travelBucketConfig.find((bucket) => bucket.key === bucketKey(minutes))?.color || "#94a3b8";
}

function colorScaleForView(minutes, viewMode) {
  if (viewMode === "loss") {
    return lossBucketConfig.find((bucket) => bucket.key === lossBucketKey(minutes))?.color || "#94a3b8";
  }
  return colorScale(minutes);
}

function qualityCopy(band) {
  switch (band) {
    case "leading":
      return "Strong service quality in the current summary layer.";
    case "stable":
      return "Solid service quality with manageable tail delay.";
    case "watchlist":
      return "Usable but worth watching for delay slippage.";
    case "at-risk":
      return "Elevated disruption risk compared with the stronger lines.";
    case "critical":
      return "Weak service quality. Prioritise with caution.";
    default:
      return "No matching reliability summary is available for this stop.";
  }
}

function transferCopy(changes) {
  if (changes == null) return "Transfer count unavailable.";
  if (changes === 0) return "Direct or walk-connected result.";
  if (changes === 1) return "Requires a single transfer.";
  return `Requires ${changes} transfers.`;
}

function accessibilityExplanation(item) {
  const scheduled = item.scheduled_travel_time_min ?? item.travel_time_min;
  const robust = item.robust_travel_time_min ?? item.travel_time_min;
  const loss = item.accessibility_loss_min ?? 0;
  const line = item.line || "the current line context";
  const p95 = item.risk_p95_delay_sec;

  if (item.accessibility_loss_flag) {
    return `This stop is reachable on schedule in ${scheduled} min, but falls out of the time budget once ${line} absorbs its reliability penalty. The robust travel time rises to ${robust} min, adding ${loss} min of accessibility loss.`;
  }
  if (typeof p95 === "number" && p95 > 0) {
    return `This stop remains reachable after applying the current reliability overlay. ${line} contributes a p95 delay of ${p95}s, lifting the robust travel time from ${scheduled} min to ${robust} min.`;
  }
  return `This stop is shown with scheduled travel time only because no stronger line-level delay signal is currently available.`;
}

function setDefaultDeparture() {
  const now = new Date();
  now.setMinutes(now.getMinutes() - (now.getMinutes() % 5), 0, 0);
  dom.departAt.value = now.toISOString().slice(0, 16);
}

function applyUrlState() {
  const params = new URLSearchParams(window.location.search);
  const departAt = params.get("depart_at_local");
  if (departAt) dom.departAt.value = departAt;
  const maxMinutes = params.get("max_minutes");
  if (maxMinutes) dom.maxMinutes.value = maxMinutes;
  const maxChanges = params.get("max_changes");
  if (maxChanges) dom.maxChanges.value = maxChanges;
  const page = params.get("page");
  if (page) state.pager.page = Math.max(1, Number(page));
  const perPage = params.get("per_page");
  if (perPage) state.pager.perPage = Math.max(1, Number(perPage));
  const sortBy = params.get("sort_by");
  if (sortBy) state.controls.sortBy = sortBy;
  const reliabilityFilter = params.get("reliability_filter");
  if (reliabilityFilter) state.controls.reliabilityFilter = reliabilityFilter;
  const bucketFilter = params.get("bucket_filter");
  if (bucketFilter) state.controls.bucketFilter = bucketFilter;
  state.controls.directOnly = params.get("direct_only") === "1";
  const viewMode = params.get("view_mode");
  if (viewMode) state.controls.viewMode = viewMode;

  const modeParam = params.get("modes");
  if (modeParam) {
    const wanted = new Set(modeParam.split(",").map((value) => value.trim()).filter(Boolean));
    document.querySelectorAll('input[name="mode"]').forEach((input) => {
      input.checked = wanted.has(input.value);
    });
  }

  const originId = params.get("origin_id");
  const originName = params.get("origin_name");
  const lat = params.get("lat");
  const lon = params.get("lon");
  if (originId && originName && lat && lon) {
    state.selectedOrigin = {
      id: originId,
      name: originName,
      type: "stop",
      lat: Number(lat),
      lon: Number(lon),
    };
    dom.originInput.value = originName;
  }
}

function buildShareUrl({ includeAutorun = true } = {}) {
  const params = new URLSearchParams();
  params.set("depart_at_local", dom.departAt.value);
  params.set("max_minutes", String(dom.maxMinutes.value));
  params.set("max_changes", String(dom.maxChanges.value));
  params.set("sort_by", state.controls.sortBy);
  params.set("reliability_filter", state.controls.reliabilityFilter);
  params.set("bucket_filter", state.controls.bucketFilter);
  params.set("view_mode", state.controls.viewMode);
  params.set("page", String(state.pager.page));
  params.set("per_page", String(state.pager.perPage));
  if (state.controls.directOnly) params.set("direct_only", "1");

  const selectedModes = Array.from(document.querySelectorAll('input[name="mode"]:checked'))
    .map((input) => input.value)
    .filter(Boolean);
  if (selectedModes.length) params.set("modes", selectedModes.join(","));

  if (state.selectedOrigin) {
    params.set("origin_id", state.selectedOrigin.id);
    params.set("origin_name", state.selectedOrigin.name);
    params.set("lat", String(state.selectedOrigin.lat));
    params.set("lon", String(state.selectedOrigin.lon));
  }

  if (includeAutorun && state.selectedOrigin) {
    params.set("autorun", "1");
  }

  const url = new URL(window.location.href);
  url.search = params.toString();
  return url.toString();
}

function syncUrlState() {
  const url = buildShareUrl();
  window.history.replaceState({}, "", url);
}

function setShareStatus(message) {
  dom.shareStatus.textContent = message;
}

function fetchJson(url, options = {}) {
  return fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...options,
  }).then(async (response) => {
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error || `HTTP ${response.status}`);
    }
    return payload;
  });
}

function clusterColorForChildren(children) {
  const sums = { "0-15": 0, "16-30": 0, "31-45": 0, "46+": 0 };
  children.forEach((marker) => {
    const key = marker.options.bucketKey || "46+";
    sums[key] += 1;
  });
  let selected = "46+";
  let max = -1;
  Object.entries(sums).forEach(([key, value]) => {
    if (value > max) {
      max = value;
      selected = key;
    }
  });
  return colorScale(selected === "0-15" ? 15 : selected === "16-30" ? 30 : selected === "31-45" ? 45 : 60);
}

function initMap() {
  state.map = L.map("map", {
    zoomControl: false,
    preferCanvas: true,
  }).setView([55.6761, 12.5683], 11);

  L.control.zoom({ position: "bottomright" }).addTo(state.map);

  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
  }).addTo(state.map);

  state.layers.reachableCluster = L.markerClusterGroup({
    spiderfyOnMaxZoom: true,
    showCoverageOnHover: false,
    maxClusterRadius: 42,
    iconCreateFunction(cluster) {
      const count = cluster.getChildCount();
      const color = clusterColorForChildren(cluster.getAllChildMarkers());
      return L.divIcon({
        html: `<div class="cluster-badge" style="background:${color}">${count}</div>`,
        className: "",
        iconSize: [42, 42],
      });
    },
  });
  state.map.addLayer(state.layers.reachableCluster);
  state.layers.origin = L.layerGroup().addTo(state.map);
  state.layers.overlayHubs = L.layerGroup().addTo(state.map);
  state.layers.overlayVulnerable = L.layerGroup().addTo(state.map);
}

async function loadBootstrap() {
  const [bootstrap, overlays] = await Promise.all([
    fetchJson("/api/frontend-config"),
    fetchJson("/api/station-overlays"),
  ]);
  state.bootstrap = bootstrap;
  state.overlays = overlays;
  state.overlayVisibility.hubs = bootstrap.show_hubs_overlay;
  state.overlayVisibility.vulnerable = bootstrap.show_vulnerable_overlay;
  state.pager.perPage = bootstrap.default_page_size || state.pager.perPage;
  state.controls.sortBy = bootstrap.default_sort_by || state.controls.sortBy;
  state.controls.reliabilityFilter = bootstrap.default_reliability_filter || state.controls.reliabilityFilter;
  state.controls.bucketFilter = bootstrap.default_bucket_filter || state.controls.bucketFilter;
  dom.toggleHubs.checked = state.overlayVisibility.hubs;
  dom.toggleVulnerable.checked = state.overlayVisibility.vulnerable;
  dom.sortBy.value = state.controls.sortBy;
  dom.qualityFilter.value = state.controls.reliabilityFilter;
  dom.bucketFilter.value = state.controls.bucketFilter;
  dom.directOnly.checked = state.controls.directOnly;
  dom.viewMode.value = state.controls.viewMode;
  updateViewModeCopy(state.controls.viewMode);
  if (bootstrap.overlay_scope_label) {
    dom.overlayScopeNote.textContent = `${bootstrap.overlay_scope_label}: hubs and vulnerable nodes are clipped to the Greater Copenhagen window.`;
  }
  renderOverlays();
}

async function runLocationSearch(query) {
  if (query.trim().length < 2) {
    state.originSuggestions = [];
    renderSuggestions();
    return;
  }
  try {
    const payload = await fetchJson(`/api/location-search?q=${encodeURIComponent(query)}&limit=8`);
    state.originSuggestions = payload.items || [];
  } catch (_error) {
    state.originSuggestions = [];
  }
  renderSuggestions();
}

function renderSuggestions() {
  const suggestions = state.originSuggestions;
  if (!suggestions.length) {
    dom.originSuggestions.hidden = true;
    dom.originSuggestions.innerHTML = "";
    return;
  }
  dom.originSuggestions.hidden = false;
  dom.originSuggestions.innerHTML = suggestions
    .map(
      (item, index) => `
        <div class="suggestion" data-suggestion-index="${index}">
          <strong>${item.name}</strong>
          <div class="muted-small">${item.type || "stop"}${item.id ? ` · ${item.id}` : ""}</div>
        </div>
      `
    )
    .join("");
}

function selectOrigin(item) {
  state.selectedOrigin = item;
  state.originSuggestions = [];
  state.pager.page = 1;
  dom.originInput.value = item.name;
  renderSuggestions();
  syncUrlState();
  renderDetail({
    name: item.name,
    id: item.id,
    travel_time_min: null,
    reliability_band: "unknown",
    confidence_tag: "n/a",
    evidence_level: "n/a",
    line: "",
    mode: "",
  });
}

function renderSummaryCards(payload) {
  const stats = payload.stats;
  const reliability = payload.reliability_summary || {};
  const cards = [
    {
      label: "Scheduled access",
      value: String(reliability.scheduled_accessible_count ?? stats.total_reachable_stop_count),
      meta: `${stats.clipped_reachable_stop_count} survive filters/window`,
    },
    {
      label: "Robust access",
      value: String(reliability.robust_accessible_count ?? "n/a"),
      meta: `within ${reliability.max_minutes ?? "?"} min`,
    },
    {
      label: "Access loss",
      value: String(reliability.accessibility_loss_count ?? 0),
      meta: `${((Number(reliability.accessibility_loss_ratio ?? 0) * 100).toFixed(1))}% of scheduled`,
    },
    {
      label: "Cache",
      value: String(stats.cache_status || "live"),
      meta: `${stats.cache_source || "upstream"} · ${stats.cache_age_sec || 0}s`,
    },
  ];
  dom.summaryCards.innerHTML = cards
    .map(
      (item) => `
        <div class="summary-card">
          <div class="label">${item.label}</div>
          <div class="value">${item.value}</div>
          <div class="muted-small">${item.meta}</div>
        </div>
      `
    )
    .join("");
}

function renderBucketBars(bucketCounts, total, viewMode) {
  dom.bucketBars.innerHTML = activeBucketConfig(viewMode)
    .map((bucket) => {
      const count = bucketCounts?.[bucket.key] || 0;
      const pct = total > 0 ? (count / total) * 100 : 0;
      return `
        <div class="bucket-row">
          <span>${bucket.label}</span>
          <div class="bucket-track">
            <div class="bucket-fill" style="width:${pct}%; background:${bucket.color}"></div>
          </div>
          <span>${count}</span>
        </div>
      `;
    })
    .join("");
}

function renderResults(payload) {
  state.reachability = payload;
  const stats = payload.stats;
  const viewMode = state.controls.viewMode;
  const mapStops = filterStopsForView(payload.map_stops, viewMode);
  const pageStops = filterStopsForView(payload.reachable_stops, viewMode);
  dom.resultsStatus.textContent =
    `${stats.total_reachable_stop_count} stops match the current filters from ${state.selectedOrigin?.name || "selected origin"} · ${viewMode} view.`;
  dom.freshnessBadge.textContent = stats.cache_status || "live";
  dom.freshnessBadge.dataset.state = stats.cache_status || "miss";
  dom.paginationLabel.textContent = `${pageStops.length} rows on this page`;
  dom.windowNote.textContent = `${mapStops.length} in map window · cap ${stats.max_result_window}`;
  renderSummaryCards(payload);
  const bucketCounts = viewMode === "loss"
    ? {
        "0-5": mapStops.filter((stop) => lossBucketKey(displayMinutesForView(stop, viewMode)) === "0-5").length,
        "6-10": mapStops.filter((stop) => lossBucketKey(displayMinutesForView(stop, viewMode)) === "6-10").length,
        "11-15": mapStops.filter((stop) => lossBucketKey(displayMinutesForView(stop, viewMode)) === "11-15").length,
        "16+": mapStops.filter((stop) => lossBucketKey(displayMinutesForView(stop, viewMode)) === "16+").length,
      }
    : stats.bucket_counts;
  renderBucketBars(bucketCounts, mapStops.length, viewMode);

  dom.resultsList.innerHTML = pageStops
    .map(
      (item) => `
        <li class="result-row ${item.id === state.activeStopId ? "is-active" : ""}" data-stop-id="${item.id}">
          <div class="result-title">
            <span>${item.name}</span>
            <span>${displayMinutesForView(item, viewMode)} min</span>
          </div>
          <div class="result-meta">
            ${viewMode === "loss" ? `loss ${item.accessibility_loss_min ?? 0} min` : `${(item.reliability_band || "unknown").replace("-", " ")}`}${item.risk_p95_delay_sec ? ` · p95 ${item.risk_p95_delay_sec}s` : ""}${item.changes != null ? ` · ${item.changes} chg` : ""}${item.line ? ` · ${item.line}` : ""}
          </div>
        </li>
      `
    )
    .join("");

  dom.prevPage.disabled = stats.page <= 1;
  dom.nextPage.disabled = stats.page >= stats.total_pages;
  renderReachabilityLayer(mapStops, viewMode);
  if (pageStops.length) {
    state.activeStopId = pageStops[0].id;
    renderDetail(pageStops[0]);
    syncResultSelection();
  }
  syncUrlState();
}

function renderReachabilityLayer(stops, viewMode) {
  state.layers.reachableCluster.clearLayers();
  state.layers.origin.clearLayers();
  const bounds = [];

  stops.forEach((stop) => {
    if (typeof stop.lat !== "number" || typeof stop.lon !== "number") {
      return;
    }
    bounds.push([stop.lat, stop.lon]);
    const marker = L.circleMarker([stop.lat, stop.lon], {
      radius: 6,
      color: "rgba(255,255,255,0.82)",
      weight: 1.5,
      fillColor: colorScaleForView(displayMinutesForView(stop, viewMode), viewMode),
      fillOpacity: 0.9,
      bucketKey: viewMode === "loss" ? lossBucketKey(displayMinutesForView(stop, viewMode)) : bucketKey(displayMinutesForView(stop, viewMode)),
      stopId: stop.id,
    });
    marker.on("click", () => {
      state.activeStopId = stop.id;
      renderDetail(stop);
      syncResultSelection();
    });
    marker.bindPopup(renderPopup(stop));
    state.layers.reachableCluster.addLayer(marker);
  });

  if (state.selectedOrigin?.lat && state.selectedOrigin?.lon) {
    const originMarker = L.circleMarker([state.selectedOrigin.lat, state.selectedOrigin.lon], {
      radius: 9,
      color: "#05131a",
      weight: 3,
      fillColor: "#fde68a",
      fillOpacity: 1,
    }).bindPopup(`<strong>Origin</strong><br>${state.selectedOrigin.name}`);
    state.layers.origin.addLayer(originMarker);
    bounds.push([state.selectedOrigin.lat, state.selectedOrigin.lon]);
  }

  if (bounds.length) {
    state.map.fitBounds(bounds, { padding: [90, 90] });
  }
}

function renderOverlays() {
  state.layers.overlayHubs.clearLayers();
  state.layers.overlayVulnerable.clearLayers();

  if (state.overlayVisibility.hubs) {
    state.overlays.hubs.forEach((hub) => {
      L.circleMarker([hub.lat, hub.lon], {
        radius: 4.5,
        color: "#ffffff",
        weight: 1,
        fillColor: "#38bdf8",
        fillOpacity: 0.7,
      })
        .bindPopup(`<strong>${hub.name}</strong><br>Hub degree ${hub.degree}`)
        .addTo(state.layers.overlayHubs);
    });
  }

  if (state.overlayVisibility.vulnerable) {
    state.overlays.vulnerable_nodes.forEach((item) => {
      L.circleMarker([item.lat, item.lon], {
        radius: 5.5,
        color: "#ffffff",
        weight: 1,
        fillColor: "#ef4444",
        fillOpacity: 0.72,
      })
        .bindPopup(`<strong>${item.name}</strong><br>Betweenness ${item.betweenness_score}`)
        .addTo(state.layers.overlayVulnerable);
    });
  }
}

function renderDetail(item) {
  if (!item) {
    dom.detailCard.innerHTML = `<p class="panel-copy">No item selected.</p>`;
    return;
  }
  dom.detailCard.innerHTML = `
    <div class="detail-block">
      <h3>${item.name || "Selected stop"}</h3>
      <p><strong>ID:</strong> ${item.id || "n/a"}</p>
      <p><strong>Travel time:</strong> ${item.travel_time_min != null ? `${item.travel_time_min} min` : "n/a"}</p>
      <p><strong>Robust time:</strong> ${item.robust_travel_time_min != null ? `${item.robust_travel_time_min} min` : "n/a"}</p>
      <p><strong>Access loss:</strong> ${item.accessibility_loss_min != null ? `${item.accessibility_loss_min} min` : "n/a"}</p>
      <p><strong>Changes:</strong> ${item.changes != null ? item.changes : "n/a"}</p>
    </div>
    <div class="detail-block">
      <h3>Why this matters</h3>
      <p>${accessibilityExplanation(item)}</p>
    </div>
    <div class="detail-block">
      <h3>Reliability overlay</h3>
      <p><strong>Band:</strong> ${item.reliability_band || "unknown"}</p>
      <p><strong>P95 delay:</strong> ${item.risk_p95_delay_sec != null ? `${item.risk_p95_delay_sec}s` : "n/a"}</p>
      <p><strong>Confidence:</strong> ${item.confidence_tag || "unknown"}</p>
      <p><strong>Evidence:</strong> ${item.evidence_level || "unknown"}</p>
    </div>
    <div class="detail-block">
      <h3>Route context</h3>
      <p><strong>Line:</strong> ${item.line || "not provided"}</p>
      <p><strong>Mode:</strong> ${item.mode || "not provided"}</p>
      <p><strong>Bucket:</strong> ${bucketKey(item.travel_time_min ?? 999)}</p>
      <p>${transferCopy(item.changes)}</p>
      <p>${qualityCopy(item.reliability_band || "unknown")}</p>
    </div>
  `;
}

function renderPopup(item) {
  const band = item.reliability_band || "unknown";
  const safeBandClass = band.replace(/[^a-z-]/g, "");
  return `
    <div class="popup-card">
      <div class="popup-title">${item.name}</div>
      <span class="popup-pill ${safeBandClass}">${band.replace("-", " ")}</span>
      <div class="popup-meta">
        <strong>${item.scheduled_travel_time_min ?? item.travel_time_min} min</strong> scheduled · ${item.robust_travel_time_min ?? item.travel_time_min} min robust
      </div>
      <div class="popup-meta">${transferCopy(item.changes)}</div>
      <div class="popup-meta"><strong>Line:</strong> ${item.line || "not provided"}</div>
      <div class="popup-meta"><strong>Mode:</strong> ${item.mode || "not provided"}</div>
      <div class="popup-meta">${qualityCopy(band)}</div>
      <div class="popup-meta">${accessibilityExplanation(item)}</div>
      <div class="popup-meta">${item.risk_p95_delay_sec ? `P95 delay ${item.risk_p95_delay_sec}s · ${item.confidence_tag || "unknown"} confidence` : "No line-level delay summary available."}</div>
    </div>
  `;
}

function syncResultSelection() {
  Array.from(dom.resultsList.querySelectorAll(".result-row")).forEach((node) => {
    node.classList.toggle("is-active", node.dataset.stopId === state.activeStopId);
  });
}

function buildQueryPayload() {
  const selectedModes = Array.from(document.querySelectorAll('input[name="mode"]:checked')).map((input) => input.value);
  return {
    origin: {
      id: state.selectedOrigin?.id,
      type: state.selectedOrigin?.type || "stop",
      lat: state.selectedOrigin?.lat,
      lon: state.selectedOrigin?.lon,
    },
    depart_at_local: dom.departAt.value,
    max_minutes: Number(dom.maxMinutes.value),
    max_changes: Number(dom.maxChanges.value),
    modes: selectedModes,
    page: state.pager.page,
    per_page: state.pager.perPage,
    sort_by: state.controls.sortBy,
    reliability_filter: state.controls.reliabilityFilter,
    bucket_filter: state.controls.bucketFilter,
    direct_only: state.controls.directOnly,
  };
}

async function fetchReachabilityPage() {
  if (!state.selectedOrigin) {
    dom.resultsStatus.textContent = "Choose an origin from the suggestion list first.";
    return;
  }
  state.appState = "loading_reachability";
  dom.resultsStatus.textContent = "Computing reachability...";
  dom.freshnessBadge.textContent = "loading";
  dom.freshnessBadge.dataset.state = "";
  setShareStatus("Share link updated for current query.");
  try {
    const payload = buildQueryPayload();
    const response = await fetchJson("/api/reachability", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    state.appState = "results_ready";
    renderResults(response);
  } catch (error) {
    state.appState = "error";
    dom.resultsStatus.textContent = error.message;
    dom.freshnessBadge.textContent = "error";
    dom.freshnessBadge.dataset.state = "";
  }
}

function attachEvents() {
  dom.originInput.addEventListener("input", (event) => {
    clearTimeout(searchTimer);
    const query = event.target.value;
    searchTimer = setTimeout(() => runLocationSearch(query), 220);
  });

  dom.originSuggestions.addEventListener("click", (event) => {
    const suggestion = event.target.closest("[data-suggestion-index]");
    if (!suggestion) return;
    selectOrigin(state.originSuggestions[Number(suggestion.dataset.suggestionIndex)]);
  });

  document.addEventListener("click", (event) => {
    if (!event.target.closest(".origin-group")) {
      state.originSuggestions = [];
      renderSuggestions();
    }
  });

  dom.form.addEventListener("submit", (event) => {
    event.preventDefault();
    state.pager.page = 1;
    fetchReachabilityPage();
  });

  dom.resultsList.addEventListener("click", (event) => {
    const row = event.target.closest("[data-stop-id]");
    if (!row || !state.reachability) return;
    const item = state.reachability.reachable_stops.find((stop) => stop.id === row.dataset.stopId);
    if (!item) return;
    state.activeStopId = item.id;
    renderDetail(item);
    syncResultSelection();
  });

  dom.toggleHubs.addEventListener("change", () => {
    state.overlayVisibility.hubs = dom.toggleHubs.checked;
    renderOverlays();
  });

  dom.toggleVulnerable.addEventListener("change", () => {
    state.overlayVisibility.vulnerable = dom.toggleVulnerable.checked;
    renderOverlays();
  });

  dom.sortBy.addEventListener("change", () => {
    state.controls.sortBy = dom.sortBy.value;
    state.pager.page = 1;
    syncUrlState();
    if (state.selectedOrigin) fetchReachabilityPage();
  });

  dom.qualityFilter.addEventListener("change", () => {
    state.controls.reliabilityFilter = dom.qualityFilter.value;
    state.pager.page = 1;
    syncUrlState();
    if (state.selectedOrigin) fetchReachabilityPage();
  });

  dom.bucketFilter.addEventListener("change", () => {
    state.controls.bucketFilter = dom.bucketFilter.value;
    state.pager.page = 1;
    syncUrlState();
    if (state.selectedOrigin) fetchReachabilityPage();
  });

  dom.directOnly.addEventListener("change", () => {
    state.controls.directOnly = dom.directOnly.checked;
    state.pager.page = 1;
    syncUrlState();
    if (state.selectedOrigin) fetchReachabilityPage();
  });

  dom.viewMode.addEventListener("change", () => {
    state.controls.viewMode = dom.viewMode.value;
    updateViewModeCopy(state.controls.viewMode);
    syncUrlState();
    if (state.reachability) renderResults(state.reachability);
  });

  dom.prevPage.addEventListener("click", () => {
    if (!state.reachability || state.reachability.stats.page <= 1) return;
    state.pager.page -= 1;
    fetchReachabilityPage();
  });

  dom.nextPage.addEventListener("click", () => {
    if (!state.reachability || state.reachability.stats.page >= state.reachability.stats.total_pages) return;
    state.pager.page += 1;
    fetchReachabilityPage();
  });

  document.querySelectorAll('input[name="mode"]').forEach((input) => {
    input.addEventListener("change", () => {
      state.pager.page = 1;
      syncUrlState();
      if (state.selectedOrigin) fetchReachabilityPage();
    });
  });

  [dom.departAt, dom.maxMinutes, dom.maxChanges].forEach((input) => {
    input.addEventListener("change", () => {
      state.pager.page = 1;
      syncUrlState();
    });
  });

  dom.shareLink.addEventListener("click", async () => {
    const url = buildShareUrl();
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(url);
        setShareStatus("Share link copied.");
      } else {
        window.prompt("Copy this share link:", url);
        setShareStatus("Share link ready to copy.");
      }
    } catch (_error) {
      window.prompt("Copy this share link:", url);
      setShareStatus("Share link ready to copy.");
    }
  });
}

async function init() {
  setDefaultDeparture();
  applyUrlState();
  initMap();
  attachEvents();
  await loadBootstrap();
  syncUrlState();
  if (state.selectedOrigin && new URLSearchParams(window.location.search).get("autorun") === "1") {
    await fetchReachabilityPage();
  }
}

init().catch((error) => {
  dom.resultsStatus.textContent = error.message;
});
