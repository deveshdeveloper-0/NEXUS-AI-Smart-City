const $ = (selector) => document.querySelector(selector);
let liveCitySlugs = new Set();
const escapeHtml = (value) => String(value).replace(/[&<>"']/g, (char) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
})[char]);

async function getJSON(url, options) {
  const response = await fetch(url, options);
  if (!response.ok) {
    let detail = `API error ${response.status}`;
    try {
      const body = await response.json();
      if (body.detail) {
        detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
      }
    } catch (error) {
      console.warn("Could not read API error response", error);
    }
    throw new Error(detail);
  }
  return response.json();
}

function metricCard(label, value, unit) {
  return `<div class="metric"><label>${escapeHtml(label)}</label><strong>${escapeHtml(value)}</strong><small>${escapeHtml(unit)}</small></div>`;
}

function drawTrend(traffic, aqi) {
  const canvas = $("#trend");
  const context = canvas.getContext("2d");
  const { width, height } = canvas;
  const padding = 35;
  context.clearRect(0, 0, width, height);
  context.strokeStyle = "#26384b";
  context.lineWidth = 1;
  for (let index = 0; index < 5; index += 1) {
    const y = padding + index * (height - 2 * padding) / 4;
    context.beginPath();
    context.moveTo(padding, y);
    context.lineTo(width - padding, y);
    context.stroke();
  }
  function drawLine(values, color, max) {
    context.strokeStyle = color;
    context.lineWidth = 3;
    context.beginPath();
    values.forEach((value, index) => {
      const x = padding + index * (width - 2 * padding) / (values.length - 1);
      const y = height - padding - value / max * (height - 2 * padding);
      index ? context.lineTo(x, y) : context.moveTo(x, y);
    });
    context.stroke();
  }
  drawLine(traffic, "#20d7df", 100);
  drawLine(aqi.map((value) => value / 1.6), "#a78bfa", 100);
}

async function loadDashboard() {
  try {
    const dashboard = await getJSON("/api/dashboard");
    $("#metrics").innerHTML = dashboard.indicators
      .map((indicator) => metricCard(indicator.name, indicator.value, indicator.unit))
      .join("");
    drawTrend(dashboard.traffic_history, dashboard.aqi_history);
  } catch (error) {
    $("#metrics").innerHTML = `<p class="muted">Could not load backend: ${escapeHtml(error.message)}. Check that the server is running.</p>`;
  }
}

function renderStatuses(statusResponse) {
  $("#agent-status").innerHTML = statusResponse.agents.map((agent) => `
    <article class="agent">
      <span class="status ${escapeHtml(agent.status)}">${escapeHtml(agent.status.toUpperCase())}</span>
      <h3>${escapeHtml(agent.name)}</h3>
      ${agent.error ? `<p class="error-text">${escapeHtml(agent.error)}</p>` : ""}
      ${agent.updated_at ? `<p class="muted small">Updated ${escapeHtml(new Date(agent.updated_at).toLocaleTimeString())}</p>` : ""}
    </article>`).join("");
}

function renderResults(results) {
  $("#agent-results").innerHTML = results.map((result) => `
    <article class="agent">
      <span class="status ${escapeHtml(result.severity)}">${escapeHtml(result.status.toUpperCase())} · ${escapeHtml(result.severity.toUpperCase())}</span>
      <h3>${escapeHtml(result.name)}</h3>
      ${result.findings.map((finding) => `<p>${escapeHtml(finding)}</p>`).join("")}
      ${result.recommendations.map((recommendation) => `<p><b>Recommendation:</b> ${escapeHtml(recommendation)}</p>`).join("")}
      ${Object.keys(result.observed_data).length
        ? `<p class="muted small"><b>Observed:</b> ${escapeHtml(JSON.stringify(result.observed_data))}</p>` : ""}
      ${result.warnings.map((warning) => `<p class="error-text">${escapeHtml(warning)}</p>`).join("")}
      ${result.error ? `<p class="error-text">${escapeHtml(result.error)}</p>` : ""}
    </article>`).join("");
}

function renderReport(report) {
  $("#combined-report").innerHTML = `
    <p><span class="status ${escapeHtml(report.status)}">${escapeHtml(report.status.toUpperCase())}</span></p>
    <p>${escapeHtml(report.summary)}</p>
    <p class="muted small">Source: ${escapeHtml(report.data_source)} (${escapeHtml(report.data_mode)})</p>
    <p class="muted small">Started: ${escapeHtml(new Date(report.started_at).toLocaleString())} · Completed: ${escapeHtml(new Date(report.completed_at).toLocaleString())} · ${escapeHtml(report.duration_ms)} ms</p>
    <p class="muted small"><b>Input indicators:</b> ${escapeHtml(JSON.stringify(report.input_data))}</p>
    <p class="muted small"><b>Limitations:</b> ${report.limitations.map(escapeHtml).join(" · ")}</p>`;
}

function statusBadge(status) {
  const value = escapeHtml(status || "DATA_UNAVAILABLE");
  return `<span class="status ${value.toLowerCase()}">${value}</span>`;
}

function providerList(providers) {
  $("#provider-status").innerHTML = providers.map((provider) => `
    <article class="provider-status">
      ${statusBadge(provider.status)}
      <b>${escapeHtml(provider.provider)}</b>
      <p class="muted small">${escapeHtml(provider.message)}</p>
    </article>`).join("");
}

function lastUpdated(value) {
  return value ? `Last updated: ${escapeHtml(new Date(value).toLocaleString())}` : "Last updated: unavailable";
}

function formatRouteDistance(meters) {
  if (typeof meters !== "number" || !Number.isFinite(meters) || meters < 0) {
    return "Unavailable";
  }
  if (meters < 1000) {
    return `${Math.round(meters)} m`;
  }
  return `${(meters / 1000).toLocaleString(undefined, { maximumFractionDigits: 1 })} km`;
}

function formatRouteDuration(value) {
  const match = typeof value === "string" && /^(\d+(?:\.\d+)?)s$/.exec(value);
  if (!match) {
    return "Unavailable";
  }
  const seconds = Number(match[1]);
  if (!Number.isSafeInteger(Math.round(seconds)) || seconds < 0) {
    return "Unavailable";
  }
  let remaining = Math.round(seconds);
  const hours = Math.floor(remaining / 3600);
  remaining %= 3600;
  const minutes = Math.floor(remaining / 60);
  const finalSeconds = remaining % 60;
  const parts = [];
  if (hours) parts.push(`${hours} hr`);
  if (minutes) parts.push(`${minutes} min`);
  if (finalSeconds || !parts.length) parts.push(`${finalSeconds} sec`);
  return parts.join(" ");
}

function renderAQI(result) {
  const readings = result.station_observations || [];
  const value = result.value === null || result.value === undefined
    ? "AQI unavailable"
    : `${escapeHtml(result.value)} ${escapeHtml(result.unit || "")}`;
  const stationRows = readings.map((reading) => {
    const pollutants = Object.entries(reading.pollutants || {})
      .map(([name, values]) => `${escapeHtml(name)}: ${escapeHtml(values.average ?? "unavailable")}`)
      .join(" · ");
    return `<li><b>${escapeHtml(reading.station || "Unnamed station")}</b>
      ${reading.aqi === null ? "" : ` · AQI ${escapeHtml(reading.aqi)}`}
      ${pollutants ? `<br><span class="muted small">${pollutants}</span>` : ""}
      ${reading.latitude !== null && reading.longitude !== null
        ? `<br><span class="muted small">Location ${escapeHtml(reading.latitude)}, ${escapeHtml(reading.longitude)}</span>` : ""}
      ${reading.observed_at ? `<br><span class="muted small">Observed ${escapeHtml(reading.observed_at)}</span>` : ""}
    </li>`;
  }).join("");
  $("#live-aqi").innerHTML = `
    ${statusBadge(result.status)}
    <strong class="live-value">${value}</strong>
    <p>${escapeHtml(result.message || "Station-level CPCB reading; no city-wide average is calculated.")}</p>
    ${readings.length ? `<ul class="observation-list">${stationRows}</ul>` : ""}
    <p class="muted small">Source: ${escapeHtml(result.source || "Unavailable")}
      · ${lastUpdated(result.fetched_at)}</p>`;
}

function renderWeather(result) {
  const current = result.current;
  const forecastUnits = result.forecast_units || {};
  const forecastRows = (result.forecast || []).map((day) => `
    <tr><td>${escapeHtml(day.date)}</td><td>${escapeHtml(day.temperature_max ?? "—")} / ${escapeHtml(day.temperature_min ?? "—")}</td>
      <td>${escapeHtml(day.precipitation_sum ?? "—")}</td><td>${escapeHtml(day.wind_speed_max ?? "—")}</td></tr>`).join("");
  $("#live-weather").innerHTML = `
    ${statusBadge(result.status)}
    <p>${escapeHtml(result.message || "")}</p>
    ${current ? `<dl class="weather-values">
      <div><dt>Temperature</dt><dd>${escapeHtml(current.temperature ?? "—")} ${escapeHtml(current.temperature_unit || "")}</dd></div>
      <div><dt>Humidity</dt><dd>${escapeHtml(current.humidity ?? "—")} ${escapeHtml(current.humidity_unit || "")}</dd></div>
      <div><dt>Wind</dt><dd>${escapeHtml(current.wind_speed ?? "—")} ${escapeHtml(current.wind_speed_unit || "")}</dd></div>
      <div><dt>Precipitation</dt><dd>${escapeHtml(current.precipitation ?? "—")} ${escapeHtml(current.precipitation_unit || "")}</dd></div>
    </dl><p class="muted small">Model valid time: ${escapeHtml(current.valid_at || "unavailable")} · ${escapeHtml(result.timezone || "")}</p>` : ""}
    ${forecastRows ? `<div class="forecast-wrap"><table class="forecast-table"><thead><tr><th>Date</th><th>Max / min (${escapeHtml(forecastUnits.temperature_2m_max || "provider unit")})</th><th>Rain (${escapeHtml(forecastUnits.precipitation_sum || "provider unit")})</th><th>Wind max (${escapeHtml(forecastUnits.wind_speed_10m_max || "provider unit")})</th></tr></thead><tbody>${forecastRows}</tbody></table></div>` : ""}
    <p class="muted small">Source: ${escapeHtml(result.source || "Unavailable")} · Data type: ${escapeHtml(result.data_type)}
      · ${lastUpdated(result.fetched_at)}</p>`;
}

function renderUnavailableMetric(target, result) {
  $(target).innerHTML = `
    ${statusBadge(result.status)}
    <p class="live-value">Data unavailable</p>
    <p>${escapeHtml(result.message || "No verified provider data is available.")}</p>
    <p class="muted small">Source: ${escapeHtml(result.source || "Unavailable")} · ${lastUpdated(result.fetched_at)}</p>`;
}

async function loadLiveCities() {
  const select = $("#live-city");
  try {
    const cities = await getJSON("/api/live/cities");
    liveCitySlugs = new Set(cities.map((city) => city.slug));
    select.innerHTML = cities.map((city) =>
      `<option value="${escapeHtml(city.slug)}">${escapeHtml(city.name)}, ${escapeHtml(city.state)}</option>`
    ).join("");
    if (cities.length && $("#live-mode-button").getAttribute("aria-pressed") === "true") {
      await refreshLiveData();
    }
  } catch (error) {
    select.innerHTML = '<option value="">Cities unavailable</option>';
    $("#live-api-status").textContent = `City list unavailable: ${error.message}`;
  }
}

async function refreshProviderStatus() {
  try {
    const data = await getJSON("/api/live/status");
    $("#api-connection").innerHTML = `<i></i> BACKEND API ${escapeHtml(data.api_status)}`;
    $("#live-api-status").textContent =
      `Backend API ${data.api_status}; provider readiness does not claim that external data is live.`;
    providerList(data.providers);
  } catch (error) {
    $("#api-connection").innerHTML = '<i></i> BACKEND API OFFLINE';
    $("#live-api-status").innerHTML = `<span class="error-text">Backend API unavailable: ${escapeHtml(error.message)}</span>`;
  }
}

async function refreshLiveData() {
  const citySlug = $("#live-city").value;
  if (!liveCitySlugs.has(citySlug)) return;
  const refresh = $("#refresh-live");
  refresh.disabled = true;
  $("#live-aqi").innerHTML = '<p class="muted">Requesting station data…</p>';
  $("#live-weather").innerHTML = '<p class="muted">Requesting model-based weather data…</p>';
  try {
    const overview = await getJSON(`/api/live/${encodeURIComponent(citySlug)}/overview`);
    renderAQI(overview.aqi);
    renderWeather(overview.weather);
    renderUnavailableMetric("#live-energy", overview.energy);
    renderUnavailableMetric("#live-city-traffic", overview.traffic);
    $("#live-overall-status").textContent =
      `${overview.city.name} overview: ${overview.status}. Refreshed ${new Date(overview.fetched_at).toLocaleString()}.`;
    await refreshProviderStatus();
  } catch (error) {
    $("#live-aqi").innerHTML = `<p class="error-text">AQI request failed: ${escapeHtml(error.message)}</p>`;
    $("#live-weather").innerHTML = `<p class="error-text">Weather request failed: ${escapeHtml(error.message)}</p>`;
    $("#live-overall-status").textContent = `Live data request failed: ${error.message}`;
  } finally {
    refresh.disabled = false;
  }
}

function setDataMode(mode) {
  const showLive = mode === "live";
  $("#live-mode-content").hidden = !showLive;
  $("#demo-mode-content").hidden = showLive;
  $("#live-mode-button").classList.toggle("active", showLive);
  $("#live-mode-button").setAttribute("aria-pressed", String(showLive));
  $("#demo-mode-button").classList.toggle("active", !showLive);
  $("#demo-mode-button").setAttribute("aria-pressed", String(!showLive));
  if (showLive) refreshLiveData();
}

async function refreshStatuses() {
  try {
    renderStatuses(await getJSON("/api/agents/status"));
  } catch (error) {
    $("#agent-status").innerHTML = `<p class="error-text">Could not load agent status: ${escapeHtml(error.message)}</p>`;
  }
}

async function loadLatestReport() {
  try {
    const report = await getJSON("/api/agents/report");
    renderResults(report.results);
    renderReport(report);
  } catch (error) {
    if (!error.message.startsWith("No agent report is available")) {
      $("#combined-report").innerHTML = `<p class="error-text">Could not load report: ${escapeHtml(error.message)}</p>`;
    }
  }
}

$("#run-agents").addEventListener("click", async () => {
  const button = $("#run-agents");
  const message = $("#execution-message");
  button.disabled = true;
  button.textContent = "Agents Running…";
  message.textContent = "Executing independent agents, then synthesizing their outputs…";
  $("#agent-results").innerHTML = '<p class="muted">Waiting for agent results…</p>';
  const polling = window.setInterval(refreshStatuses, 500);
  try {
    const report = await getJSON("/api/agents/run", { method: "POST" });
    renderStatuses(await getJSON("/api/agents/status"));
    renderResults(report.results);
    renderReport(report);
    message.textContent = `Execution finished with status: ${report.status}.`;
  } catch (error) {
    message.innerHTML = `<span class="error-text">Execution failed: ${escapeHtml(error.message)}</span>`;
  } finally {
    window.clearInterval(polling);
    button.disabled = false;
    button.textContent = "Run All Agents ↗";
    await refreshStatuses();
  }
});

$("#demo-mode-button").addEventListener("click", () => setDataMode("demo"));
$("#live-mode-button").addEventListener("click", () => setDataMode("live"));
$("#refresh-live").addEventListener("click", refreshLiveData);
$("#live-city").addEventListener("change", refreshLiveData);
$("#route-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = $("#route-form button");
  const resultElement = $("#route-result");
  const selectedCity = $("#live-city").value;
  button.disabled = true;
  resultElement.innerHTML = '<p class="muted">Requesting traffic-aware route ETA…</p>';
  try {
    const result = await getJSON("/api/live/traffic/route", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        origin: $("#route-origin").value,
        destination: $("#route-destination").value,
        city_slug: liveCitySlugs.has(selectedCity) ? selectedCity : null
      })
    });
    resultElement.innerHTML = `
      <p><b>Provider status:</b> ${statusBadge(result.status)}</p>
      <dl class="route-result-metrics">
        <div><dt>Route distance</dt><dd>${escapeHtml(formatRouteDistance(result.distanceMeters))}</dd></div>
        <div><dt>Estimated travel duration (traffic-aware)</dt><dd>${escapeHtml(formatRouteDuration(result.duration))}</dd></div>
        <div><dt>Static duration</dt><dd>${escapeHtml(formatRouteDuration(result.staticDuration))}</dd></div>
      </dl>
      <p class="muted small">The Google Routes <code>duration</code> is the traffic-aware ETA; <code>staticDuration</code> is the non-traffic baseline.</p>
      <p><b>Origin:</b> ${escapeHtml(result.origin)} · <b>Destination:</b> ${escapeHtml(result.destination)}</p>
      <p>${escapeHtml(result.message || "")}</p>
      <p class="muted small">Source: ${escapeHtml(result.source || "Unavailable")} · Route-level only, not city-wide traffic · ${lastUpdated(result.fetched_at)}</p>`;
    await refreshProviderStatus();
  } catch (error) {
    resultElement.innerHTML = `
      <p><b>Provider status:</b> ${statusBadge("DATA_UNAVAILABLE")}</p>
      <p class="error-text">Route request failed: ${escapeHtml(error.message)}</p>
      <p class="muted small">No route values were returned. Source: unavailable · ${lastUpdated(null)}</p>`;
  } finally {
    button.disabled = false;
  }
});

loadDashboard();
refreshStatuses();
loadLatestReport();
refreshProviderStatus();
loadLiveCities();
