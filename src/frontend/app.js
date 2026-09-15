/**
 * GridGuard - Operator Dashboard Controller
 * Pure Vanilla JavaScript Client
 * Manual sync via SYNC NOW button — no background auto-polling.
 *
 * Environment config (mirrors src/.env.example):
 *   DJANGO_API_ORIGIN  — full origin of the Django server (default: http://127.0.0.1:8000)
 *   DJANGO_PORT        — port used when the page is served over HTTP  (default: 8000)
 *   FRONTEND_PORT      — port of the static file server               (default: 5500)
 *
 * For a vanilla HTML/JS build there is no runtime dotenv loader, so values
 * are defined once here in CONFIG.  To override for a different environment,
 * change only these two constants — every URL below derives from them.
 */

const CONFIG = {
    // ── Origin resolution ──────────────────────────────────────────────────
    // When opened as a local file:// the browser cannot reach a relative host,
    // so we fall back to the loopback address with the configured port.
    // When served over HTTP (Live Server, nginx, etc.) we mirror the page's
    // own protocol + hostname and append DJANGO_PORT.
    DJANGO_PORT:    8000,   // matches DJANGO_PORT in src/.env.example
    FRONTEND_PORT:  5500,   // matches FRONTEND_PORT in src/.env.example

    get API_ORIGIN() {
        return window.location.protocol === "file:"
            ? `http://127.0.0.1:${this.DJANGO_PORT}`
            : `${window.location.protocol}//${window.location.hostname}:${this.DJANGO_PORT}`;
    },

    // ── API endpoint URLs (all derived — never edit these directly) ────────
    get API_PREDICTIONS_URL() { return `${this.API_ORIGIN}/api/predictions/`; },
    get API_INCIDENTS_URL()   { return `${this.API_ORIGIN}/api/incidents/enriched/`; },
    get API_WEATHER_URL()     { return `${this.API_ORIGIN}/api/weather/`; },

    POLL_INTERVAL_MS: 10000, // kept for reference; auto-polling is disabled
};

// Application State
let currentPredictions = [];
let currentIncidents = [];
let currentWeather = [];
let pollTimer = null;

// DOM Elements
const dom = {
    totalAssetsCount: document.getElementById("totalAssetsCount"),
    highRiskCount: document.getElementById("highRiskCount"),
    highRiskRatio: document.getElementById("highRiskRatio"),
    activeWeatherWarnings: document.getElementById("activeWeatherWarnings"),
    weatherStatusTag: document.getElementById("weatherStatusTag"),
    syncStatus: document.getElementById("syncStatus"),
    syncIndicator: document.getElementById("syncIndicator"),
    lastUpdated: document.getElementById("lastUpdated"),
    assetTableBody: document.getElementById("assetTableBody"),
    dispatchTableBody: document.getElementById("dispatchTableBody"),
    dispatchCount: document.getElementById("dispatchCount"),
    manualRefreshBtn: document.getElementById("manualRefreshBtn"),
    assetSearchInput: document.getElementById("assetSearchInput"),
    incidentTableBody: document.getElementById("incidentTableBody"),
    incidentCount: document.getElementById("incidentCount"),
    incidentSearchInput: document.getElementById("incidentSearchInput"),
    weatherTableBody: document.getElementById("weatherTableBody"),
    weatherCount: document.getElementById("weatherCount"),
};

/**
 * Format timestamp into HH:MM:SS
 */
function formatTime(date = new Date()) {
    return date.toTimeString().split(" ")[0];
}

/**
 * Map risk category to CSS classes and human readable labels
 */
function getSeverityMeta(category, score) {
    const cat = (category || "").toUpperCase();
    if (cat === "HIGH" || score >= 75) {
        return {
            classKey: "high",
            label: "HIGH",
            badgeClass: "badge-high",
            fillClass: "high",
        };
    } else if (cat === "MEDIUM" || (score >= 40 && score < 75)) {
        return {
            classKey: "medium",
            label: "MEDIUM",
            badgeClass: "badge-warning",
            fillClass: "medium",
        };
    } else {
        return {
            classKey: "low",
            label: "LOW",
            badgeClass: "badge-low",
            fillClass: "low",
        };
    }
}

/**
 * Fetch latest risk predictions from Django REST backend
 */
async function fetchPredictions() {
    try {
        if (dom.syncStatus) dom.syncStatus.textContent = "SYNCING...";
        if (dom.syncIndicator) dom.syncIndicator.className = "status-indicator";

        const response = await fetch(CONFIG.API_PREDICTIONS_URL, {
            method: "GET",
            headers: {
                "Accept": "application/json",
            },
            cache: "no-cache",
        });

        if (!response.ok) {
            throw new Error(`HTTP Error ${response.status}: ${response.statusText}`);
        }

        const data = await response.json();
        currentPredictions = Array.isArray(data) ? data : [];

        // Update UI
        updateSummaryKPIs(currentPredictions);
        renderAssetTable(currentPredictions);
        renderCrewDispatchPlan(currentPredictions);

        // Update connection status — timestamp is set by manualSync after all promises resolve
        if (dom.syncStatus) dom.syncStatus.textContent = "CONNECTED";
        if (dom.syncIndicator) dom.syncIndicator.className = "status-indicator";
        if (dom.lastUpdated) dom.lastUpdated.textContent = formatTime();
    } catch (error) {
        console.error("Failed to fetch grid predictions:", error);
        if (dom.syncStatus) dom.syncStatus.textContent = "OFFLINE (RETRYING...)";
        if (dom.syncIndicator) dom.syncIndicator.className = "status-indicator error";

        // Show offline state in tables if no data cached
        if (currentPredictions.length === 0 && dom.assetTableBody && dom.dispatchTableBody) {
            dom.assetTableBody.innerHTML = `
                <tr>
                    <td colspan="7" class="empty-cell">
                        Unable to connect to backend at ${CONFIG.API_PREDICTIONS_URL}.<br>
                        Ensure Django server is running: <span class="mono-text">python manage.py runserver</span>
                    </td>
                </tr>
            `;
            dom.dispatchTableBody.innerHTML = `
                <tr>
                    <td colspan="6" class="empty-cell">
                        No dispatch telemetry available offline.
                    </td>
                </tr>
            `;
        }
    }
}

/**
 * Fetch historical incident records for the audit trail.
 */
async function fetchIncidents() {
    try {
        const response = await fetch(CONFIG.API_INCIDENTS_URL, {
            method: "GET",
            headers: { "Accept": "application/json" },
            cache: "no-cache",
        });

        if (!response.ok) {
            throw new Error(`HTTP Error ${response.status}: ${response.statusText}`);
        }

        const data = await response.json();
        currentIncidents = Array.isArray(data) ? data : [];
        renderIncidentTable(currentIncidents);
        renderDispatchTimeline(currentIncidents);
    } catch (error) {
        console.error("Failed to fetch incident logs:", error);
        if (document.getElementById("dispatchTimeline")) {
            renderDispatchTimeline([]);
        }
        if (!dom.incidentCount || !dom.incidentTableBody) return;
        dom.incidentCount.textContent = "UNAVAILABLE";
        dom.incidentTableBody.innerHTML = `
            <tr>
                <td colspan="9" class="empty-cell">Unable to load historical incident records.</td>
            </tr>
        `;
    }
}

async function fetchWeather() {
    if (!dom.weatherTableBody) return;
    try {
        const response = await fetch(CONFIG.API_WEATHER_URL, { headers: { "Accept": "application/json" }, cache: "no-cache" });
        if (!response.ok) throw new Error(`HTTP Error ${response.status}`);
        currentWeather = await response.json();
        renderWeatherTable(currentWeather);
    } catch (error) {
        console.error("Failed to fetch weather forecasts:", error);
        dom.weatherCount.textContent = "UNAVAILABLE";
        dom.weatherTableBody.innerHTML = '<tr><td colspan="7" class="empty-cell">Unable to load weather forecasts.</td></tr>';
    }
}

/**
 * Update the 3 summary metric cards
 */
function updateSummaryKPIs(predictions) {
    if (!dom.totalAssetsCount) return;
    const totalAssets = predictions.length;
    const highRiskAssets = predictions.filter(
        (item) => item.risk_category === "HIGH" || item.risk_score >= 75
    );
    const highRiskCount = highRiskAssets.length;
    const ratio = totalAssets > 0 ? Math.round((highRiskCount / totalAssets) * 100) : 0;

    const weatherExposedAssets = predictions
        .filter((item) => Number(item.storm_severity || 0) >= 4)
        .slice(0, 4);

    // Update DOM
    dom.totalAssetsCount.textContent = totalAssets;
    dom.highRiskCount.textContent = highRiskCount;
    dom.highRiskRatio.textContent = `${ratio}% OF GRID`;

    dom.activeWeatherWarnings.textContent = Math.min(weatherExposedAssets.length, 4);
    dom.weatherStatusTag.textContent = weatherExposedAssets.length > 0 ? "ELEVATED" : "CLEAR";
}

/**
 * Render dynamic rows for Table 1: Asset Risk Standings using template literals
 */
function renderAssetTable(predictions) {
    if (!dom.assetTableBody || !dom.assetSearchInput) return;
    const searchTerm = (dom.assetSearchInput.value || "").trim().toLowerCase();

    const filtered = predictions.filter((asset) => {
        if (!searchTerm) return true;
        const idMatch = (asset.asset_id || "").toLowerCase().includes(searchTerm);
        const cityMatch = (asset.city_name || "").toLowerCase().includes(searchTerm);
        const zoneMatch = (asset.zone_name || asset.crew_preposition_zone || "").toLowerCase().includes(searchTerm);
        const causeMatch = (asset.root_cause || "").toLowerCase().includes(searchTerm);
        const catMatch = (asset.risk_category || "").toLowerCase().includes(searchTerm);
        return idMatch || cityMatch || zoneMatch || causeMatch || catMatch;
    });

    if (filtered.length === 0) {
        dom.assetTableBody.innerHTML = `
            <tr>
                <td colspan="7" class="empty-cell">
                    No grid assets match search criteria "${searchTerm}".
                </td>
            </tr>
        `;
        return;
    }

    const rowsHtml = filtered
        .map((asset, index) => {
            const rank = asset.urgency_rank || index + 1;
            const score = Number(asset.risk_score).toFixed(2);
            const meta = getSeverityMeta(asset.risk_category, asset.risk_score);
            const zoneDisplay = asset.city_name && asset.zone_name 
                ? `${asset.city_name} <span style="opacity: 0.65; font-size: 0.85em;">(${asset.zone_name})</span>`
                : (asset.zone_name || asset.zone || "N/A");
            const cause = asset.root_cause || "Nominal operation";
            const action = asset.next_action_description || asset.recommended_action || "Routine monitoring";

            return `
                <tr>
                    <td class="mono-cell" style="color: var(--text-tertiary);">#${rank.toString().padStart(2, "0")}</td>
                    <td class="mono-cell asset-id-cell">${asset.asset_id}</td>
                    <td><span class="zone-tag">${zoneDisplay}</span></td>
                    <td class="cause-cell">${cause}</td>
                    <td>
                        <div class="risk-bar-container">
                            <div class="risk-bar-track">
                                <div class="risk-bar-fill ${meta.fillClass}" style="width: ${Math.min(score, 100)}%;"></div>
                            </div>
                            <span class="risk-score-num">${score}</span>
                        </div>
                    </td>
                    <td>
                        <span class="status-badge ${meta.classKey}">
                            ${meta.label}
                        </span>
                    </td>
                    <td class="action-cell">${action}</td>
                </tr>
            `;
        })
        .join("");

    dom.assetTableBody.innerHTML = rowsHtml;
}

/**
 * Render dynamic rows for Table 2: Crew Dispatch Plan using template literals
 */
function renderCrewDispatchPlan(predictions) {
    if (!dom.dispatchTableBody || !dom.dispatchCount) return;
    // Filter HIGH risk assets that require emergency or immediate dispatch
    const highRiskAssets = [];
    const dispatchCities = new Set();
    for (const asset of predictions) {
        const city = asset.city_name || asset.city || "Unknown City";
        if ((asset.risk_category === "HIGH" || asset.risk_score >= 75) &&
            (!dispatchCities.has(city) || highRiskAssets.length === 0)) {
            highRiskAssets.push(asset);
            dispatchCities.add(city);
        }
        if (dispatchCities.size >= 3) break;
    }

    dom.dispatchCount.textContent = `${highRiskAssets.length} dispatch${
        highRiskAssets.length === 1 ? "" : "s"
    } pending`;

    if (highRiskAssets.length === 0) {
        dom.dispatchTableBody.innerHTML = `
            <tr>
                <td colspan="6" class="empty-cell" style="color: var(--risk-low);">
                    All monitored transformers currently operating within safe degradation tolerances. No emergency crew pre-positioning required.
                </td>
            </tr>
        `;
        return;
    }

    const rowsHtml = highRiskAssets
        .map((asset, index) => {
            const priorityRank = `P-${index + 1}`;
            const city = asset.city_name || asset.city || "Unknown City";
            const zoneDisplay = asset.city_name && asset.zone_name 
                ? `${asset.city_name} (${asset.zone_name})` 
                : (asset.zone_name || asset.zone || "UNASSIGNED");
            const score = Number(asset.risk_score).toFixed(2);
            const cause = asset.root_cause || "High asset degradation";
            const directive = asset.next_action_description || asset.recommended_action ||
                `Dispatch crew to ${zoneDisplay} for ${asset.asset_id} and restore power after repair.`;

            return `
                <tr>
                    <td class="mono-cell" style="color: var(--risk-high); font-weight: 700;">${priorityRank}</td>
                    <td class="mono-cell asset-id-cell">${asset.asset_id}</td>
                    <td><span class="zone-tag dispatch-zone dispatch-destination" style="display: grid; gap: 3px;">${city}<small style="display: block;">${zoneDisplay}</small></span></td>
                    <td class="mono-cell" style="color: var(--risk-high);">${score} / 100</td>
                    <td class="directive-cell"><strong>ISSUE:</strong> ${cause}<br>${directive}</td>
                    <td>
                        <span class="status-badge high">STAGE 1 DISPATCH</span>
                    </td>
                </tr>
            `;
        })
        .join("");

    dom.dispatchTableBody.innerHTML = rowsHtml;
}

/**
 * Render searchable historical outage records.
 */
function renderIncidentTable(incidents) {
    if (!dom.incidentTableBody || !dom.incidentSearchInput || !dom.incidentCount) return;
    const searchTerm = (dom.incidentSearchInput.value || "").trim().toLowerCase();
    const filtered = incidents.filter((incident) => {
        if (!searchTerm) return true;
        return [
            incident.incident_id,
            incident.asset_id,
            incident.city,
            incident.zone,
            incident.failure_type,
            incident.date,
        ].some((value) => String(value || "").toLowerCase().includes(searchTerm));
    });

    dom.incidentCount.textContent = `${filtered.length} record${filtered.length === 1 ? "" : "s"}`;
    if (filtered.length === 0) {
        dom.incidentTableBody.innerHTML = `
            <tr><td colspan="9" class="empty-cell">No incident records match "${searchTerm}".</td></tr>
        `;
        return;
    }

    dom.incidentTableBody.innerHTML = filtered.map((incident) => {
        // Live weather cells — show value with unit or a muted "—" if unavailable
        const isLive   = incident.live_source === "live";
        const tempCell = isLive && incident.live_temp_c   != null
            ? `${Number(incident.live_temp_c).toFixed(1)} °C`
            : '<span style="color:var(--outline)">—</span>';
        const windCell = isLive && incident.live_wind_kmh != null
            ? `${Number(incident.live_wind_kmh).toFixed(1)} km/h`
            : '<span style="color:var(--outline)">—</span>';
        return `
        <tr>
            <td class="mono-cell asset-id-cell">${incident.incident_id || "N/A"}</td>
            <td class="mono-cell">${incident.date || "N/A"}</td>
            <td class="mono-cell">${incident.asset_id || "N/A"}</td>
            <td><span class="zone-tag">${incident.city || "N/A"}<br><small>${incident.zone || "N/A"}</small></span></td>
            <td class="cause-cell">${incident.failure_type || "Unclassified"}</td>
            <td class="mono-cell">${Number(incident.downtime_hours || 0).toFixed(1)} h</td>
            <td class="mono-cell">${Number(incident.affected_consumers || 0).toLocaleString()}</td>
            <td class="mono-cell">${tempCell}</td>
            <td class="mono-cell">${windCell}</td>
        </tr>`;
    }).join("");
}

/**
 * Render the animated vertical timeline on field-dispatch.html.
 * Silently exits on any page that lacks #dispatchTimeline.
 * Driven by /api/incidents/ payload (currentIncidents).
 *
 * Tier classification per incident:
 *   critical  → downtime ≥ 40 h  OR  affected_consumers ≥ 30 000
 *   urgent    → downtime ≥ 15 h  OR  affected_consumers ≥ 10 000
 *   normal    → everything else
 *
 * Three dispatch vectors per card:
 *   Origin      — derived grid hub for the incident's zone
 *   Target      — asset_id + city
 *   Diagnostic  — failure_type
 */
function renderDispatchTimeline(incidents) {
    const container  = document.getElementById("dispatchTimeline");
    const countEl    = document.getElementById("dispatchCount");
    if (!container) return;

    // Zone → staging grid hub mapping (mirrors grid_assets.json grid_hub values)
    const ZONE_HUB = {
        "Central Gujarat": "Vadodara Grid Hub",
        "South Gujarat":   "Surat Grid Hub",
        "Saurashtra":      "Rajkot Grid Hub",
        "North Gujarat":   "Mehsana Grid Hub",
        "Kutch":           "Bhuj Grid Hub",
    };

    if (!incidents || incidents.length === 0) {
        container.innerHTML = '<div class="tl-empty">No active dispatch incidents found.</div>';
        if (countEl) countEl.textContent = "0 missions";
        return;
    }

    // Sort newest → oldest so the pipeline reads chronologically top-down
    const sorted = [...incidents].sort((a, b) => new Date(b.date) - new Date(a.date));

    if (countEl) countEl.textContent = `${sorted.length} mission${sorted.length === 1 ? "" : "s"} active`;

    container.innerHTML = sorted.map((inc, idx) => {
        const downtime   = Number(inc.downtime_hours   || 0);
        const consumers  = Number(inc.affected_consumers || 0);

        // Tier classification
        const isCritical = downtime >= 40 || consumers >= 30000;
        const isUrgent   = !isCritical && (downtime >= 15 || consumers >= 10000);
        const tier       = isCritical ? "critical" : isUrgent ? "urgent" : "normal";

        // Tier badge label
        const tierLabel  = isCritical ? "CRITICAL" : isUrgent ? "URGENT" : "ROUTINE";

        // Vector data
        const hub    = ZONE_HUB[inc.zone] || `${inc.zone || "Unknown Zone"} Hub`;
        const origin = hub;
        const target = `${inc.asset_id || "UNKNOWN"} in ${inc.city || "Unknown City"}`;
        const diag   = inc.failure_type || "Unclassified fault";

        // Staggered reveal delay so entries slide in sequentially
        const delay  = idx * 80;

        return `
<div class="tl-entry" style="transition-delay:${delay}ms" data-idx="${idx}">
  <div class="tl-node-col">
    <div class="tl-node ${tier}"></div>
  </div>
  <div class="tl-card">
    <div class="tl-card-head ${tier}">
      <div style="display:flex;align-items:center;gap:10px;">
        <span class="tl-seq">MISSION ${String(idx + 1).padStart(2, "0")}</span>
        <span class="tl-asset-id">${inc.incident_id || "INC-UNKNOWN"}</span>
      </div>
      <div style="display:flex;align-items:center;gap:8px;">
        <span class="status-badge ${tier === "critical" ? "high" : tier === "urgent" ? "medium" : "low"}">${tierLabel}</span>
        <span class="tl-date">${inc.date || "--"}</span>
      </div>
    </div>
    <div class="tl-card-body">
      <div class="tl-vector">
        <span class="tl-vector-label">
          <span class="tl-vector-icon origin"></span>Origin — Crew Starting Base
        </span>
        <div class="tl-vector-value">${origin}</div>
        <span class="tl-vector-sub">${inc.zone || "Unknown Zone"}</span>
      </div>
      <div class="tl-vector">
        <span class="tl-vector-label">
          <span class="tl-vector-icon target"></span>Target — Active Transit Vector
        </span>
        <div class="tl-vector-value">${target}</div>
        <span class="tl-vector-sub">Asset ID: ${inc.asset_id || "--"}</span>
      </div>
      <div class="tl-vector">
        <span class="tl-vector-label">
          <span class="tl-vector-icon diag"></span>Diagnostic — Failure Payload
        </span>
        <div class="tl-vector-value">${diag}</div>
        <span class="tl-vector-sub">Outage incident</span>
      </div>
    </div>
    <div class="tl-card-foot">
      <span class="tl-consumers">Affected: <strong>${consumers.toLocaleString()} consumers</strong></span>
      <span class="tl-downtime">Downtime: <strong>${downtime.toFixed(1)} h</strong></span>
    </div>
  </div>
</div>`;
    }).join("");

    // Trigger staggered reveal animation on next frame
    requestAnimationFrame(() => {
        container.querySelectorAll(".tl-entry").forEach((el) => {
            const delay = parseInt(el.style.transitionDelay) || 0;
            setTimeout(() => el.classList.add("revealed"), delay);
        });
    });
}

function renderWeatherTable(forecasts) {
    dom.weatherCount.textContent = `${forecasts.length} zones`;
    dom.weatherTableBody.innerHTML = forecasts.map((item) => {
        const forecast = item.forecast || {};
        const severity = Number(forecast.storm_severity_scale || 0);
        const riskClass = severity >= 4 ? "high" : severity >= 2 ? "medium" : "low";
        return `<tr>
            <td class="asset-id-cell">${item.zone || "N/A"}</td>
            <td>${forecast.condition || "N/A"}</td>
            <td class="mono-cell">${Number(forecast.ambient_temperature_c || 0).toFixed(1)} C</td>
            <td class="mono-cell">${Number(forecast.humidity_percentage || 0).toFixed(1)}%</td>
            <td class="mono-cell">${Number(forecast.wind_speed_kmh || 0).toFixed(1)} km/h</td>
            <td class="mono-cell">${Number(forecast.precipitation_mm || 0).toFixed(1)} mm</td>
            <td><span class="status-badge ${riskClass}">LEVEL ${severity}</span></td>
        </tr>`;
    }).join("");
}

// ─── Manual Sync ────────────────────────────────────────────────────────────

/**
 * Fires all three fetch chains simultaneously.
 * Transitions the status badge to "REFRESHING DATA..." while requests are in
 * flight, then restores it to "CONNECTED" with the current timestamp once
 * every promise has settled (resolved or rejected).
 */
async function manualSync() {
    if (dom.syncStatus)    dom.syncStatus.textContent = "REFRESHING DATA...";
    if (dom.syncIndicator) dom.syncIndicator.className = "status-indicator syncing";
    if (dom.manualRefreshBtn) dom.manualRefreshBtn.disabled = true;

    await Promise.allSettled([
        fetchPredictions(),
        fetchIncidents(),
        fetchWeather(),
    ]);

    if (dom.syncIndicator) dom.syncIndicator.className = "status-indicator";
    if (dom.syncStatus)    dom.syncStatus.textContent = "CONNECTED";
    if (dom.lastUpdated)   dom.lastUpdated.textContent = formatTime();
    if (dom.manualRefreshBtn) dom.manualRefreshBtn.disabled = false;
}

// Event Listeners
if (dom.manualRefreshBtn) dom.manualRefreshBtn.addEventListener("click", manualSync);

if (dom.assetSearchInput) dom.assetSearchInput.addEventListener("input", () => renderAssetTable(currentPredictions));

if (dom.incidentSearchInput) dom.incidentSearchInput.addEventListener("input", () => renderIncidentTable(currentIncidents));

// ─── Startup ─────────────────────────────────────────────────────────────────

/**
 * Runs once on DOMContentLoaded — fires all three fetches in parallel and
 * goes through the same status-badge lifecycle as a manual sync so the header
 * never stays stuck on "CONNECTING...".
 * Auto-polling (setInterval) remains disabled; every subsequent refresh is
 * operator-triggered via SYNC NOW.
 */
async function startPolling() {
    if (dom.syncStatus)    dom.syncStatus.textContent = "REFRESHING DATA...";
    if (dom.syncIndicator) dom.syncIndicator.className = "status-indicator syncing";
    if (dom.manualRefreshBtn) dom.manualRefreshBtn.disabled = true;

    await Promise.allSettled([
        fetchPredictions(),
        fetchIncidents(),
        fetchWeather(),
    ]);

    // Restore button; status text + timestamp are already set by fetchPredictions
    // (CONNECTED on success, OFFLINE on failure) — only re-enable the button here.
    if (dom.manualRefreshBtn) dom.manualRefreshBtn.disabled = false;

    // Auto-polling disabled: setInterval removed intentionally.
    // pollTimer = setInterval(fetchPredictions, CONFIG.POLL_INTERVAL_MS);
}

// Start application
window.addEventListener("DOMContentLoaded", startPolling);

// ─── Satellite Rainfall Prediction ───────────────────────────────────────────

const SATELLITE_PREDICT_URL = `${CONFIG.API_ORIGIN}/api/satellite-predict/`;

/**
 * Wire drag-and-drop and file-picker events on weather-storm.html.
 * Exits silently on any other page where the elements are absent.
 */
function initSatelliteUpload() {
    const dropZone  = document.getElementById("satelliteDropZone");
    const fileInput = document.getElementById("satelliteFileInput");
    const locSelect = document.getElementById("satelliteLocation");
    const statusEl  = document.getElementById("satelliteStatus");

    if (!dropZone || !fileInput) return;   // not on weather-storm.html — do nothing

    // Click on the drop zone opens the file picker (ignore clicks on the <label> itself,
    // which the browser already handles natively via for="satelliteFileInput")
    dropZone.addEventListener("click", (e) => {
        if (e.target.tagName !== "LABEL") fileInput.click();
    });

    dropZone.addEventListener("dragover", (e) => {
        e.preventDefault();
        dropZone.style.borderColor = "var(--accent, #3b82d4)";
    });

    dropZone.addEventListener("dragleave", () => {
        dropZone.style.borderColor = "var(--border)";
    });

    dropZone.addEventListener("drop", (e) => {
        e.preventDefault();
        dropZone.style.borderColor = "var(--border)";
        const file = e.dataTransfer.files[0];
        // locSelect always has a selected value — the first <option> is pre-selected by the browser
        if (file) runSatellitePrediction(file, locSelect.value, statusEl);
    });

    fileInput.addEventListener("change", () => {
        const file = fileInput.files[0];
        if (file) runSatellitePrediction(file, locSelect.value, statusEl);
    });
}

/**
 * POST the .tif file + location to /api/satellite-predict/ as multipart FormData,
 * then write the response values into the three metric cards.
 *
 * FormData key alignment:
 *   FormData.append("file", ...)     → request.FILES["file"]  in Django view
 *   FormData.append("location", ...) → request.POST["location"] in Django view
 */
async function runSatellitePrediction(file, location, statusEl) {
    if (statusEl) statusEl.textContent = "PROCESSING...";

    // Reset cards to a neutral "loading" state before the request so stale
    // values from a previous upload are never shown alongside a new error.
    _setSatelliteCards({ predicted_rainfall_mm: "…", weather_condition: "Analysing…", pixel_value: "…", coordinates: "…", image: file.name });

    const formData = new FormData();
    formData.append("file", file);           // key must match request.FILES.get("file")
    formData.append("location", location);   // key must match request.POST.get("location")

    try {
        const response = await fetch(SATELLITE_PREDICT_URL, {
            method: "POST",
            // Do NOT set Content-Type manually — the browser sets it automatically
            // with the correct multipart boundary when body is a FormData object.
            headers: { "Accept": "application/json" },
            body: formData,
        });

        const data = await response.json();

        if (!response.ok) {
            // Surface the human-readable backend message (covers InvalidSatelliteImageError,
            // bad location name, missing zip, etc.) directly in the cards so nothing is
            // left showing "-- mm".
            const msg = data.message || data.error || `Request failed (HTTP ${response.status})`;
            _setSatelliteCards(null, msg);
            if (statusEl) statusEl.textContent = `ERROR ${response.status}`;
            console.error("Satellite prediction error:", msg);
            return;
        }

        _setSatelliteCards(data);
        if (statusEl) statusEl.textContent = "PREDICTION COMPLETE";

    } catch (err) {
        // Network-level failure (Django server not running, CORS block, etc.)
        _setSatelliteCards(null, "Backend unreachable. Is Django running on port 8000?");
        if (statusEl) statusEl.textContent = "OFFLINE";
        console.error("Failed to reach satellite prediction endpoint:", err);
    }
}

/**
 * Write prediction values into the three metric cards, or an error message.
 * Passing `data = null` and an `errorMsg` string puts the error in all fields.
 *
 * @param {Object|null} data         - Successful response dict from the backend.
 * @param {string}      [errorMsg]   - Error string shown when data is null.
 */
function _setSatelliteCards(data, errorMsg) {
    const rainfallEl  = document.getElementById("satRainfall");
    const conditionEl = document.getElementById("satCondition");
    const pixelEl     = document.getElementById("satPixel");
    const coordsEl    = document.getElementById("satCoords");
    const imageEl     = document.getElementById("satImage");

    if (data) {
        if (rainfallEl)  rainfallEl.textContent = `${data.predicted_rainfall_mm} mm`;
        if (conditionEl) conditionEl.textContent = data.weather_condition || "--";
        if (pixelEl)     pixelEl.textContent     = data.pixel_value != null ? data.pixel_value : "--";
        if (coordsEl)    coordsEl.textContent    = data.coordinates || "--";
        if (imageEl)     imageEl.textContent     = data.image || "--";
        _setRiskCradle(data);
    } else {
        // Error state — populate rainfall card with the message, clear the rest
        if (rainfallEl)  rainfallEl.textContent = "Error";
        if (conditionEl) conditionEl.textContent = errorMsg || "Unknown error";
        if (pixelEl)     pixelEl.textContent     = "--";
        if (coordsEl)    coordsEl.textContent    = "--";
        if (imageEl)     imageEl.textContent     = "--";
        _hideRiskCradle();
    }
}

// Risk label → CSS colour mapping
const _RISK_COLOURS = { "Low Risk": "#16a34a", "Medium Risk": "#d97706", "High Alert": "#dc2626" };

// Warning copy per risk tier
const _RISK_WARNINGS = {
    "Low Risk":    "Grid conditions are stable. No pre-emptive crew deployment required. Continue routine telemetry monitoring.",
    "Medium Risk": "Elevated storm-infrastructure coupling detected. Consider scheduling maintenance within 48 hours and monitoring telemetry closely.",
    "High Alert":  "Critical outage risk. Immediate crew pre-positioning recommended. Activate emergency response protocols for affected zone.",
};

/**
 * Populate and reveal the Risk Assessment Cradle below the metric cards.
 * @param {Object} data - Successful response from /api/satellite-predict/
 */
function _setRiskCradle(data) {
    const cradle  = document.getElementById("riskCradle");
    const pctEl   = document.getElementById("riskPct");
    const labelEl = document.getElementById("riskLabel");
    const warnEl  = document.getElementById("riskWarning");
    const badgeEl = document.getElementById("riskSourceBadge");

    if (!cradle) return;

    const score  = data.risk_score_pct;
    const label  = data.risk_label  || "Unknown";
    const source = data.risk_source || "Unknown Source";
    const colour = _RISK_COLOURS[label] || "#57606a";

    if (pctEl) {
        pctEl.textContent = `${score}%`;
        pctEl.style.color = colour;
    }
    if (labelEl) {
        labelEl.textContent = label;
        labelEl.style.color = colour;
    }
    if (warnEl)  warnEl.textContent  = _RISK_WARNINGS[label] || "";
    if (badgeEl) {
        badgeEl.textContent = `Source: ${source}`;
        // Distinguish proximity fallback with a subtle amber tint
        badgeEl.style.background = source.includes("Fallback") ? "#fffbeb" : "#fff";
        badgeEl.style.borderColor = source.includes("Fallback") ? "#d97706" : "var(--border)";
        badgeEl.style.color       = source.includes("Fallback") ? "#92400e" : "inherit";
    }

    cradle.style.display = "block";
}

function _hideRiskCradle() {
    const cradle = document.getElementById("riskCradle");
    if (cradle) cradle.style.display = "none";
}

// Wire on DOM ready — safe no-op on every page except weather-storm.html
window.addEventListener("DOMContentLoaded", initSatelliteUpload);
