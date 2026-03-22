const state = {
  bootstrap: null,
  selectedScenarioId: null,
  selectedDuration: null,
  selectedMaxChanges: null,
  selectedCategory: null,
  selectedOriginId: null,
  layerCache: new Map(),
  detailCache: new Map(),
  map: null,
  atlasLayer: null,
  poiLayer: null,
  selectionLayer: null,
  currentLayerPayload: null,
};

const dom = {
  atlasTitle: document.getElementById("atlas-title"),
  atlasSubtitle: document.getElementById("atlas-subtitle"),
  boundaryLabel: document.getElementById("boundary-label"),
  bundleStatus: document.getElementById("bundle-status"),
  scenarioCount: document.getElementById("scenario-count"),
  categoryCount: document.getElementById("category-count"),
  scenarioSelect: document.getElementById("scenario-select"),
  durationSelect: document.getElementById("duration-select"),
  maxChangesSelect: document.getElementById("max-changes-select"),
  categoryButtons: document.getElementById("category-buttons"),
  scenarioDescription: document.getElementById("scenario-description"),
  layerTitle: document.getElementById("layer-title"),
  mapCaption: document.getElementById("map-caption"),
  legendScale: document.getElementById("legend-scale"),
  originCountChip: document.getElementById("origin-count-chip"),
  layerMedianChip: document.getElementById("layer-median-chip"),
  layerTopChip: document.getElementById("layer-top-chip"),
  originTitle: document.getElementById("origin-title"),
  originBadge: document.getElementById("origin-badge"),
  originContext: document.getElementById("origin-context"),
  originAnchorCard: document.getElementById("origin-anchor-card"),
  summaryGrid: document.getElementById("summary-grid"),
  deltaTitle: document.getElementById("delta-title"),
  deltaCopy: document.getElementById("delta-copy"),
  municipalityTitle: document.getElementById("municipality-title"),
  municipalityBadge: document.getElementById("municipality-badge"),
  municipalityCopy: document.getElementById("municipality-copy"),
  municipalityList: document.getElementById("municipality-list"),
  poiTitle: document.getElementById("poi-title"),
  poiCount: document.getElementById("poi-count"),
  poiList: document.getElementById("poi-list"),
};

const categoryColors = {
  campus: "#658e2c",
  hospital: "#c95f48",
  job_hub: "#2d7b8a",
};
const categoryPalettes = {
  campus: ["#f4efdf", "#dce8c7", "#b9d487", "#7cac52", "#355f2d"],
  hospital: ["#fbede7", "#f1ceb9", "#e79a78", "#cf6b51", "#7c2d23"],
  job_hub: ["#e8f3f3", "#c1dde1", "#84bac4", "#43808f", "#163f4a"],
};

function scenarioById(id) {
  return state.bootstrap.scenarios.find((item) => item.scenario_id === id);
}

function layerKey() {
  return `${state.selectedScenarioId}__${state.selectedDuration}__mc${state.selectedMaxChanges}`;
}

function layerPath() {
  const entry = state.bootstrap.files.layers.find(
    (item) =>
      item.scenario_id === state.selectedScenarioId &&
      item.duration === state.selectedDuration &&
      item.max_changes === state.selectedMaxChanges,
  );
  return entry?.path;
}

function currentCategoryMeta() {
  return state.bootstrap.categories.find((item) => item.category === state.selectedCategory);
}

function activePalette() {
  return categoryPalettes[state.selectedCategory] || categoryPalettes.job_hub;
}

function sourceModeLabel(mode) {
  return mode === "api" ? "API-backed bundle" : "Sample bundle";
}

async function fetchJson(path) {
  const response = await fetch(path);
  if (!response.ok) throw new Error(`Failed to load ${path}`);
  return response.json();
}

function initMap(center, zoom) {
  state.map = L.map("map", {
    zoomControl: false,
    preferCanvas: true,
  }).setView(center, zoom);

  L.control.zoom({ position: "bottomright" }).addTo(state.map);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 18,
    attribution: "&copy; OpenStreetMap contributors",
  }).addTo(state.map);
}

function buildLegend(breaks) {
  dom.legendScale.innerHTML = "";
  const palette = activePalette();
  for (let index = 0; index < palette.length; index += 1) {
    const item = document.createElement("div");
    item.className = "legend-step";
    const min = breaks[index];
    const max = breaks[index + 1];
    item.innerHTML = `
      <span class="swatch" style="background:${palette[index]}"></span>
      <span>${min.toFixed(1)}-${max.toFixed(1)}</span>
    `;
    dom.legendScale.appendChild(item);
  }
}

function buildBreaks(features) {
  const scores = features
    .map((feature) => Number(feature.properties.category_metrics[state.selectedCategory].weighted_score || 0))
    .sort((a, b) => a - b);
  if (!scores.length) return [0, 0, 0, 0, 0, 0];
  const quantiles = [0, 0.2, 0.4, 0.6, 0.8, 1].map((quantile) => {
    const index = Math.min(scores.length - 1, Math.floor((scores.length - 1) * quantile));
    return scores[index];
  });
  quantiles[0] = 0;
  for (let index = 1; index < quantiles.length; index += 1) {
    quantiles[index] = Math.max(quantiles[index], quantiles[index - 1]);
  }
  return quantiles.map((value) => Number(value.toFixed(2)));
}

function colorForScore(score, breaks) {
  const palette = activePalette();
  for (let index = 0; index < palette.length; index += 1) {
    if (score <= breaks[index + 1]) return palette[index];
  }
  return palette[palette.length - 1];
}

function percentileValue(scores, percentile) {
  if (!scores.length) return 0;
  const ordered = [...scores].sort((a, b) => a - b);
  const index = Math.min(ordered.length - 1, Math.floor((ordered.length - 1) * percentile));
  return ordered[index];
}

function summaryCard(label, value, hint, accent) {
  return `
    <article class="summary-card">
      <div class="summary-top">
        <span class="summary-dot" style="background:${accent}"></span>
        <span class="summary-label">${label}</span>
      </div>
      <strong class="summary-value">${value}</strong>
      <p class="summary-hint">${hint}</p>
    </article>
  `;
}

function formatNearest(value) {
  return typeof value === "number" ? `${value} min` : "Not reached";
}

function renderSummaryCards(metrics) {
  dom.summaryGrid.innerHTML = state.bootstrap.categories
    .map((categoryMeta) => {
      const current = metrics[categoryMeta.category];
      return summaryCard(
        categoryMeta.label,
        `${current.count} reachable`,
        `Weighted score ${current.weighted_score.toFixed(1)} · nearest ${formatNearest(current.nearest_time_min)}`,
        categoryColors[categoryMeta.category],
      );
    })
    .join("");
}

function renderPoiList(opportunities) {
  const filtered = opportunities
    .filter(
      (poi) =>
        poi.category === state.selectedCategory &&
        poi.travel_time_min <= state.selectedDuration &&
        poi.changes <= state.selectedMaxChanges,
    )
    .sort((a, b) => a.travel_time_min - b.travel_time_min || b.weight - a.weight);

  dom.poiCount.textContent = String(filtered.length);
  dom.poiTitle.textContent = `${currentCategoryMeta().label} within ${state.selectedDuration} min`;

  if (!filtered.length) {
    dom.poiList.innerHTML = `<li class="poi-empty">No ${currentCategoryMeta().unit} are reached under the current transfer cap.</li>`;
    return;
  }

  dom.poiList.innerHTML = filtered
    .map(
      (poi) => `
        <li class="poi-item">
          <div class="poi-main">
            <strong>${poi.name}</strong>
            <span class="poi-meta">${poi.travel_time_min} min · ${poi.changes} changes · weight ${poi.weight}</span>
          </div>
          <span class="poi-chip" style="background:${categoryColors[poi.category]}">${poi.category_label}</span>
        </li>
      `,
    )
    .join("");
}

function renderInterpretation(originName, metrics) {
  const active = metrics[state.selectedCategory];
  const categoryMeta = currentCategoryMeta();
  const sign = active.delta_vs_median >= 0 ? "+" : "";
  dom.deltaTitle.textContent = `${categoryMeta.label} vs metro-area median`;
  dom.deltaCopy.textContent =
    `${originName} reaches ${active.count} ${categoryMeta.unit} within ${state.selectedDuration} minutes. ` +
    `Its weighted score is ${sign}${active.delta_vs_median.toFixed(1)} against the current layer median, ` +
    `placing it at the ${active.percentile.toFixed(1)}th percentile for this scenario.`;
}

function renderMunicipalityComparison(municipalityName) {
  const municipalitySummary = state.currentLayerPayload?.municipality_summary || [];
  if (!municipalitySummary.length) {
    dom.municipalityBadge.textContent = "-";
    dom.municipalityCopy.textContent = "Municipality aggregation is unavailable for the current layer.";
    dom.municipalityList.innerHTML = "";
    return;
  }

  const activeCategory = state.selectedCategory;
  const current = municipalitySummary.find((item) => item.municipality === municipalityName) || municipalitySummary[0];
  const currentMetrics = current.category_metrics[activeCategory];
  const ordered = [...municipalitySummary].sort(
    (a, b) =>
      b.category_metrics[activeCategory].avg_weighted_score - a.category_metrics[activeCategory].avg_weighted_score ||
      a.municipality.localeCompare(b.municipality),
  );
  const topRows = ordered.slice(0, 5);
  if (!topRows.find((row) => row.municipality === current.municipality)) {
    topRows.push(current);
  }

  dom.municipalityTitle.textContent = `${currentCategoryMeta().label} by municipality`;
  dom.municipalityBadge.textContent = `${currentMetrics.rank}/${currentMetrics.municipality_count}`;
  dom.municipalityCopy.textContent =
    `${current.municipality} averages ${currentMetrics.avg_weighted_score.toFixed(1)} weighted score and ` +
    `${currentMetrics.avg_count.toFixed(1)} reachable ${currentCategoryMeta().unit} across ${current.origin_count} origin cells. ` +
    `${currentMetrics.delta_vs_overall_avg >= 0 ? "+" : ""}${currentMetrics.delta_vs_overall_avg.toFixed(1)} versus the regional average.`;

  dom.municipalityList.innerHTML = topRows
    .map((row) => {
      const metrics = row.category_metrics[activeCategory];
      const isCurrent = row.municipality === current.municipality;
      return `
        <li class="municipality-item${isCurrent ? " current" : ""}" aria-current="${isCurrent ? "true" : "false"}">
          <div class="municipality-main">
            <div class="municipality-rank">#${metrics.rank}</div>
            <div>
              <strong>${row.municipality}</strong>
              <div class="municipality-meta">${metrics.avg_count.toFixed(1)} reachable · nearest ${formatNearest(metrics.avg_nearest_time_min)}</div>
            </div>
          </div>
          <div class="municipality-score">
            <strong>${metrics.avg_weighted_score.toFixed(1)}</strong>
            <span>${metrics.delta_vs_overall_avg >= 0 ? "+" : ""}${metrics.delta_vs_overall_avg.toFixed(1)} vs avg</span>
          </div>
        </li>
      `;
    })
    .join("");
}

function renderAnchorCard(origin) {
  if (!origin.origin_stop_id) {
    dom.originAnchorCard.innerHTML = "";
    return;
  }
  const walkPenaltyMin =
    typeof origin.origin_stop_lat === "number" && typeof origin.origin_stop_lon === "number"
      ? Math.max(
          0,
          Math.round(
            (Math.hypot(origin.lat - origin.origin_stop_lat, origin.lon - origin.origin_stop_lon) * 111000) / 80,
          ),
        )
      : 0;
  dom.originAnchorCard.innerHTML = `
    <div class="anchor-label">Anchor stop</div>
    <div class="anchor-main">
      <strong>${origin.origin_stop_name || origin.origin_stop_id}</strong>
      <span>${origin.origin_stop_id}</span>
    </div>
    <p>Live mode reuses the anchor stop reachability result and adds a local access penalty from the grid centroid to the station catchment.</p>
  `;
  if (walkPenaltyMin > 0) {
    dom.originAnchorCard.innerHTML += `<div class="anchor-chip">Approx. first-leg walk penalty baked into travel times</div>`;
  }
}

function renderSelectionMarker(feature) {
  if (state.selectionLayer) state.selectionLayer.remove();
  const centroid = feature?.properties?.centroid;
  if (!centroid) return;

  state.selectionLayer = L.layerGroup([
    L.circleMarker([centroid.lat, centroid.lon], {
      radius: 10,
      color: "#fffdf7",
      weight: 2,
      fillColor: "#18332d",
      fillOpacity: 0.12,
      interactive: false,
    }),
    L.circleMarker([centroid.lat, centroid.lon], {
      radius: 4,
      color: "#18332d",
      weight: 1,
      fillColor: "#18332d",
      fillOpacity: 0.95,
      interactive: false,
    }),
  ]).addTo(state.map);
}

async function loadOriginDetail(originId) {
  if (!state.detailCache.has(originId)) {
    const path = state.bootstrap.files.detail_template.replace("{origin_id}", originId);
    state.detailCache.set(originId, await fetchJson(path));
  }
  return state.detailCache.get(originId);
}

function findOriginCombination(detail) {
  return detail.combinations.find(
    (item) => item.scenario_id === state.selectedScenarioId && item.max_changes === state.selectedMaxChanges,
  );
}

async function selectOrigin(originId, fallbackMetrics) {
  state.selectedOriginId = originId;
  const detail = await loadOriginDetail(originId);
  const combo = findOriginCombination(detail);
  const metrics = fallbackMetrics || combo.metrics_by_duration[String(state.selectedDuration)];

  dom.originTitle.textContent = detail.origin.name;
  dom.originBadge.textContent = detail.origin.municipality;
  dom.originContext.textContent =
    `${detail.origin.neighborhood} in ${detail.origin.municipality}. ` +
    `Population weight ${detail.origin.population_weight.toFixed(2)} under the current resilience weighting.`;

  renderAnchorCard(detail.origin);
  renderSummaryCards(metrics);
  renderInterpretation(detail.origin.name, metrics);
  renderMunicipalityComparison(detail.origin.municipality);
  renderPoiList(combo.poi_opportunities);
}

function addPoiOverlay() {
  if (state.poiLayer) state.poiLayer.remove();
  const layer = L.layerGroup();
  state.bootstrap.pois.forEach((poi) => {
    const categoryMeta = state.bootstrap.categories.find((item) => item.category === poi.category);
    L.circleMarker([poi.lat, poi.lon], {
      radius: 5,
      color: "#fffdf7",
      weight: 1,
      fillColor: categoryColors[poi.category],
      fillOpacity: 0.95,
    })
      .bindTooltip(`${poi.name} · ${categoryMeta?.label || poi.category}`, { direction: "top" })
      .addTo(layer);
  });
  layer.addTo(state.map);
  state.poiLayer = layer;
}

async function renderLayer() {
  const key = layerKey();
  const path = layerPath();
  if (!path) throw new Error(`Missing layer for ${key}`);

  if (!state.layerCache.has(key)) {
    state.layerCache.set(key, await fetchJson(path));
  }
  state.currentLayerPayload = state.layerCache.get(key);
  const { features } = state.currentLayerPayload;
  const breaks = buildBreaks(features);
  const scores = features.map((feature) => Number(feature.properties.category_metrics[state.selectedCategory].weighted_score || 0));
  const medianScore = percentileValue(scores, 0.5);
  const topDecile = percentileValue(scores, 0.9);
  buildLegend(breaks);

  dom.layerTitle.textContent =
    `${currentCategoryMeta().label} resilience surface · ${state.selectedDuration} min · max ${state.selectedMaxChanges} changes`;
  dom.scenarioDescription.textContent = scenarioById(state.selectedScenarioId).description;
  dom.mapCaption.textContent =
    `${features.length} modeled catchments, fixed departure at ${scenarioById(state.selectedScenarioId).depart_at_local}, and a transit-first scoring model that keeps transfer budgets explicit.`;
  dom.originCountChip.textContent = String(features.length);
  dom.layerMedianChip.textContent = medianScore.toFixed(1);
  dom.layerTopChip.textContent = topDecile.toFixed(1);

  if (state.atlasLayer) state.atlasLayer.remove();
  state.atlasLayer = L.geoJSON(state.currentLayerPayload, {
    style: (feature) => {
      const score = Number(feature.properties.category_metrics[state.selectedCategory].weighted_score || 0);
      return {
        color: feature.properties.origin_id === state.selectedOriginId ? "#fffdf7" : "rgba(255,253,247,0.55)",
        weight: feature.properties.origin_id === state.selectedOriginId ? 2.4 : 0.8,
        fillColor: colorForScore(score, breaks),
        fillOpacity: feature.properties.origin_id === state.selectedOriginId ? 0.96 : 0.83,
      };
    },
    onEachFeature: (feature, layer) => {
      const metric = feature.properties.category_metrics[state.selectedCategory];
      layer.bindTooltip(
        `<strong>${feature.properties.name}</strong><br>${metric.count} reachable · score ${metric.weighted_score.toFixed(1)}<br>Nearest ${formatNearest(metric.nearest_time_min)}`,
        { sticky: true, className: "atlas-tooltip" },
      );
      layer.on("mouseover", () => {
        layer.setStyle({ weight: 2, color: "#fffdf7", fillOpacity: 0.96 });
        if (typeof layer.bringToFront === "function") layer.bringToFront();
      });
      layer.on("mouseout", () => {
        if (state.atlasLayer) state.atlasLayer.resetStyle(layer);
      });
      layer.on("click", async () => {
        await selectOrigin(feature.properties.origin_id, feature.properties.category_metrics);
        await renderLayer();
      });
    },
  }).addTo(state.map);

  if (!state._hasFitBounds && features.length) {
    state.map.fitBounds(state.atlasLayer.getBounds(), { padding: [20, 20] });
    state._hasFitBounds = true;
  }

  if (!state.selectedOriginId && features.length) {
    await selectOrigin(features[0].properties.origin_id, features[0].properties.category_metrics);
    renderSelectionMarker(features[0]);
  } else if (state.selectedOriginId) {
    const selectedFeature = features.find((feature) => feature.properties.origin_id === state.selectedOriginId);
    if (selectedFeature) {
      await selectOrigin(state.selectedOriginId, selectedFeature.properties.category_metrics);
      renderSelectionMarker(selectedFeature);
    }
  }

  if (!state.selectedOriginId && state.currentLayerPayload?.municipality_summary?.length) {
    renderMunicipalityComparison(state.currentLayerPayload.municipality_summary[0].municipality);
  }
}

function renderCategoryButtons() {
  dom.categoryButtons.innerHTML = "";
  state.bootstrap.categories.forEach((category) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `category-pill${state.selectedCategory === category.category ? " active" : ""}`;
    button.textContent = category.label;
    button.setAttribute("aria-pressed", state.selectedCategory === category.category ? "true" : "false");
    button.style.setProperty("--category-accent", categoryColors[category.category]);
    button.addEventListener("click", async () => {
      state.selectedCategory = category.category;
      renderCategoryButtons();
      addPoiOverlay();
      await renderLayer();
    });
    dom.categoryButtons.appendChild(button);
  });
}

function populateSelect(select, items, getValue, getLabel) {
  select.innerHTML = "";
  items.forEach((item) => {
    const option = document.createElement("option");
    option.value = String(getValue(item));
    option.textContent = getLabel(item);
    select.appendChild(option);
  });
}

function bindControls() {
  dom.scenarioSelect.addEventListener("change", async () => {
    state.selectedScenarioId = dom.scenarioSelect.value;
    await renderLayer();
  });
  dom.durationSelect.addEventListener("change", async () => {
    state.selectedDuration = Number(dom.durationSelect.value);
    await renderLayer();
  });
  dom.maxChangesSelect.addEventListener("change", async () => {
    state.selectedMaxChanges = Number(dom.maxChangesSelect.value);
    await renderLayer();
  });
}

async function bootstrap() {
  state.bootstrap = await fetchJson("./data/atlas_bootstrap.json");
  state.selectedScenarioId = state.bootstrap.defaults.scenario_id;
  state.selectedDuration = state.bootstrap.defaults.duration;
  state.selectedMaxChanges = state.bootstrap.defaults.max_changes;
  state.selectedCategory = state.bootstrap.defaults.category;

  dom.atlasTitle.textContent = state.bootstrap.title;
  dom.atlasSubtitle.textContent = state.bootstrap.subtitle;
  dom.boundaryLabel.textContent = state.bootstrap.operational_boundary_label;
  dom.bundleStatus.textContent = `${sourceModeLabel(state.bootstrap.source_mode)} · ${state.bootstrap.generated_at_utc.slice(0, 10)}`;
  dom.scenarioCount.textContent = String(state.bootstrap.scenarios.length);
  dom.categoryCount.textContent = String(state.bootstrap.categories.length);

  populateSelect(dom.scenarioSelect, state.bootstrap.scenarios, (item) => item.scenario_id, (item) => item.label);
  populateSelect(dom.durationSelect, state.bootstrap.durations, (item) => item, (item) => `${item} min`);
  populateSelect(dom.maxChangesSelect, state.bootstrap.max_changes_options, (item) => item, (item) => `${item}`);
  dom.scenarioSelect.value = state.selectedScenarioId;
  dom.durationSelect.value = String(state.selectedDuration);
  dom.maxChangesSelect.value = String(state.selectedMaxChanges);

  renderCategoryButtons();
  bindControls();
  initMap(state.bootstrap.map.center, state.bootstrap.map.zoom);
  addPoiOverlay();
  await renderLayer();
}

bootstrap().catch((error) => {
  dom.bundleStatus.textContent = "Failed";
  dom.originContext.textContent = error.message;
  console.error(error);
});
