/* ─── State ──────────────────────────────────────────────── */
let currentLoc  = 'Ahmedabad';
let acIndex     = -1;
let recent      = JSON.parse(localStorage.getItem('wxRecent') || '[]');
let compareList = [];

/* ─── DOM refs ───────────────────────────────────────────── */
const input       = document.getElementById('locationInput');
const clearBtn    = document.getElementById('clearBtn');
const predictBtn  = document.getElementById('predictBtn');
const acDropdown  = document.getElementById('acDropdown');
const distList    = document.getElementById('districtList');
const recentBlock = document.getElementById('recentBlock');
const recentChips = document.getElementById('recentChips');
const cmpChips    = document.getElementById('compareChips');
const runCmpBtn   = document.getElementById('runCompareBtn');
const addCmpBtn   = document.getElementById('addCompareBtn');
const loadOverlay = document.getElementById('loadingOverlay');
const cmpPanel    = document.getElementById('comparePanel');
const cmpGrid     = document.getElementById('compareGrid');

/* ─── Boot ───────────────────────────────────────────────── */
document.addEventListener('DOMContentLoaded', () => {
    renderRecent();
    predict('Ahmedabad');
    bindEvents();
});

function bindEvents() {
    input.addEventListener('input', onInput);
    input.addEventListener('keydown', onKeydown);
    clearBtn.addEventListener('click', clearInput);
    predictBtn.addEventListener('click', triggerPredict);
    addCmpBtn.addEventListener('click', addToCompare);
    runCmpBtn.addEventListener('click', runComparison);
    document.getElementById('closeCmpBtn').addEventListener('click', () => {
        cmpPanel.style.display = 'none';
    });
    document.addEventListener('click', e => {
        if (!e.target.closest('.search-block')) closeAC();
    });
    distList.addEventListener('click', e => {
        const item = e.target.closest('.d-item');
        if (item) selectLocation(item.dataset.loc);
    });
}

/* ════════════════════════════════════════════════════════════
   INPUT & AUTOCOMPLETE
   ════════════════════════════════════════════════════════════ */

function onInput() {
    const q = input.value;
    clearBtn.style.display = q ? 'flex' : 'none';
    showAC(q.trim());
    filterList(q.trim());
}

function onKeydown(e) {
    const items = acDropdown.querySelectorAll('.ac-item');
    if (e.key === 'ArrowDown') {
        e.preventDefault();
        acIndex = Math.min(acIndex + 1, items.length - 1);
        highlightAC(items);
    } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        acIndex = Math.max(acIndex - 1, 0);
        highlightAC(items);
    } else if (e.key === 'Enter') {
        e.preventDefault();
        if (acIndex >= 0 && items[acIndex]) {
            pickAC(items[acIndex].dataset.loc);
        } else {
            triggerPredict();
        }
    } else if (e.key === 'Escape') {
        closeAC();
    }
}

function showAC(q) {
    acIndex = -1;
    if (!q) { acDropdown.innerHTML = ''; acDropdown.style.display = 'none'; return; }
    const ql = q.toLowerCase();
    const matches = LOCATIONS.filter(l => l.toLowerCase().includes(ql)).slice(0, 8);
    if (!matches.length) {
        acDropdown.innerHTML = `<li class="ac-empty"><i class="fa-solid fa-circle-question"></i> No matching district</li>`;
        acDropdown.style.display = 'block';
        return;
    }
    acDropdown.innerHTML = matches.map((loc, i) => {
        const idx = loc.toLowerCase().indexOf(ql);
        const hi  = loc.substring(0, idx) + `<strong>${loc.substring(idx, idx + ql.length)}</strong>` + loc.substring(idx + ql.length);
        return `<li class="ac-item" data-loc="${loc}" data-i="${i}">
            <i class="fa-solid fa-location-dot"></i>
            <span>${hi}</span>
            <span class="ac-state">Gujarat</span>
        </li>`;
    }).join('');
    acDropdown.style.display = 'block';
    acDropdown.querySelectorAll('.ac-item').forEach(el => {
        el.addEventListener('click', () => pickAC(el.dataset.loc));
        el.addEventListener('mouseenter', () => { acIndex = +el.dataset.i; highlightAC(acDropdown.querySelectorAll('.ac-item')); });
    });
}

function highlightAC(items) {
    items.forEach((el, i) => el.classList.toggle('ac-on', i === acIndex));
}

function pickAC(loc) {
    input.value = loc;
    clearBtn.style.display = 'flex';
    closeAC();
    selectLocation(loc);
}

function closeAC() {
    acDropdown.innerHTML = '';
    acDropdown.style.display = 'none';
    acIndex = -1;
}

function clearInput() {
    input.value = '';
    clearBtn.style.display = 'none';
    closeAC();
    filterList('');
    input.focus();
}

function triggerPredict() {
    const raw = input.value.trim();
    if (!raw) {
        showToast('Please type a district name first', 'error');
        input.focus();
        return;
    }
    closeAC();
    const ql = raw.toLowerCase();
    let matched = LOCATIONS.find(l => l.toLowerCase() === ql)
                || LOCATIONS.find(l => l.toLowerCase().startsWith(ql))
                || LOCATIONS.find(l => l.toLowerCase().includes(ql))
                || LOCATIONS.find(l => ql.includes(l.toLowerCase()));
    if (matched) {
        selectLocation(matched);
    } else {
        selectLocation(raw); // server will fuzzy match
    }
}

/* ════════════════════════════════════════════════════════════
   DISTRICT LIST
   ════════════════════════════════════════════════════════════ */

function filterList(q) {
    const ql = q.toLowerCase();
    let count = 0;
    distList.querySelectorAll('.d-item').forEach(el => {
        const show = !ql || el.dataset.loc.toLowerCase().includes(ql);
        el.style.display = show ? '' : 'none';
        if (show) count++;
    });
    document.getElementById('districtCount').textContent = count;
}

function selectLocation(name) {
    currentLoc = name;
    input.value = name;
    clearBtn.style.display = 'flex';
    distList.querySelectorAll('.d-item').forEach(el => {
        const active = el.dataset.loc === name;
        el.classList.toggle('active', active);
        if (active) el.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    });
    addRecent(name);
    predict(name);
}

/* ════════════════════════════════════════════════════════════
   RECENT SEARCHES
   ════════════════════════════════════════════════════════════ */

function addRecent(name) {
    recent = recent.filter(r => r !== name);
    recent.unshift(name);
    if (recent.length > 6) recent.pop();
    localStorage.setItem('wxRecent', JSON.stringify(recent));
    renderRecent();
}

function renderRecent() {
    if (!recent.length) { recentBlock.style.display = 'none'; return; }
    recentBlock.style.display = 'block';
    recentChips.innerHTML = recent.map(loc =>
        `<button class="chip" data-loc="${loc}"><i class="fa-solid fa-clock-rotate-left"></i> ${loc}</button>`
    ).join('');
    recentChips.querySelectorAll('.chip').forEach(btn =>
        btn.addEventListener('click', () => selectLocation(btn.dataset.loc))
    );
}

/* ════════════════════════════════════════════════════════════
   COMPARE
   ════════════════════════════════════════════════════════════ */

function addToCompare() {
    if (!currentLoc) return;
    if (compareList.includes(currentLoc)) { showToast(`${currentLoc} already in compare list`, 'error'); return; }
    if (compareList.length >= 5) { showToast('Max 5 locations for comparison', 'error'); return; }
    compareList.push(currentLoc);
    renderCompareChips();
    showToast(`Added ${currentLoc}`, 'success');
}

function renderCompareChips() {
    if (!compareList.length) {
        cmpChips.innerHTML = '<span class="empty-hint">Click <b>+</b> to add a location</span>';
        runCmpBtn.style.display = 'none';
        return;
    }
    cmpChips.innerHTML = compareList.map(loc =>
        `<span class="chip chip-cyan">
            <i class="fa-solid fa-location-dot"></i> ${loc}
            <button class="chip-remove" data-loc="${loc}"><i class="fa-solid fa-xmark"></i></button>
        </span>`
    ).join('');
    cmpChips.querySelectorAll('.chip-remove').forEach(btn =>
        btn.addEventListener('click', e => {
            e.stopPropagation();
            compareList = compareList.filter(l => l !== btn.dataset.loc);
            renderCompareChips();
        })
    );
    runCmpBtn.style.display = compareList.length >= 2 ? 'flex' : 'none';
}

async function runComparison() {
    if (compareList.length < 2) { showToast('Add at least 2 locations', 'error'); return; }
    loadOverlay.classList.add('show');
    const results = [];
    for (const loc of compareList) {
        try {
            const res = await fetch('/api/predict', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ location: loc, image_path: '' })
            });
            const d = await res.json();
            if (!d.error) results.push(d);
        } catch (_) {}
    }
    loadOverlay.classList.remove('show');
    if (results.length < 2) { showToast('Could not fetch enough results', 'error'); return; }
    renderCmpPanel(results);
}

function renderCmpPanel(results) {
    cmpGrid.innerHTML = results.map(d => `
        <div class="cmp-card border-${d.badge_class}">
            <div class="cmp-city">${d.location}</div>
            <span class="badge badge-${d.badge_class}"><i class="fa-solid ${d.icon}"></i> ${d.condition}</span>
            <div class="cmp-rain">${d.predicted_rainfall_mm.toFixed(2)}<span class="cmp-unit">mm</span></div>
            <div class="cmp-metrics">
                <span><i class="fa-solid fa-droplet"></i> ${d.rain_probability}%</span>
                <span><i class="fa-solid fa-temperature-half"></i> ${d.temperature_c}°C</span>
                <span><i class="fa-solid fa-wind"></i> ${d.wind_speed_kmh} km/h</span>
                <span><i class="fa-solid fa-water"></i> ${d.humidity_pct}%</span>
            </div>
            <p class="cmp-advisory">${d.advisory}</p>
        </div>
    `).join('');
    cmpPanel.style.display = 'block';
    cmpPanel.scrollIntoView({ behavior: 'smooth' });
}

/* ════════════════════════════════════════════════════════════
   PREDICTION
   ════════════════════════════════════════════════════════════ */

async function predict(location) {
    loadOverlay.classList.add('show');
    try {
        const res  = await fetch('/api/predict', {
            method:  'POST',
            headers: { 'Content-Type': 'application/json' },
            body:    JSON.stringify({ location, image_path: '' })
        });
        const data = await res.json();
        if (data.error) { showToast(data.error, 'error'); return; }
        renderResult(data);
    } catch (_) {
        showToast('Cannot reach server. Is Flask running?', 'error');
    } finally {
        loadOverlay.classList.remove('show');
    }
}

function renderResult(d) {
    const mm = d.predicted_rainfall_mm;

    /* Hero */
    setText('heroLoc',    d.location);
    setText('coordText',  `${d.latitude}° N, ${d.longitude}° E`);
    const badge = document.getElementById('heroBadge');
    badge.innerHTML   = `<i class="fa-solid ${d.icon}"></i> ${d.condition}`;
    badge.className   = `hero-badge badge-${d.badge_class}`;
    setText('rainVal', mm.toFixed(2));

    /* Gauge */
    const pct = Math.min(100, (mm / 100) * 100);
    const fill = document.getElementById('gaugeFill');
    fill.style.width      = pct + '%';
    fill.style.background = rainColor(mm);
    setText('gaugeNum', mm.toFixed(2) + ' mm');

    /* Metrics */
    setText('mProb',     d.rain_probability + '%');
    setText('mTemp',     d.temperature_c + '°C');
    setText('mWind',     d.wind_speed_kmh + ' km/h');
    setText('mHumidity', d.humidity_pct + '%');
    setText('mCloud',    d.cloud_cover_pct + '%');
    setText('mUV',       d.uv_index + ' / 10');

    /* Advisory */
    setText('advisoryBody', d.advisory);
    const box  = document.getElementById('advisoryBox');
    const icon = document.getElementById('advisoryIcon');
    box.className  = `advisory-box adv-${d.badge_class}`;
    const iMap = { success: 'fa-leaf', info: 'fa-umbrella', warning: 'fa-cloud-showers-heavy', danger: 'fa-triangle-exclamation' };
    icon.className = `fa-solid ${iMap[d.badge_class] || 'fa-circle-info'} advisory-icon`;

    /* Satellite */
    const satFrame = document.getElementById('satFrame');
    satFrame.classList.add('loading');
    const img = document.getElementById('satImg');
    img.onload = () => satFrame.classList.remove('loading');
    img.src = `/api/image_preview?img=${encodeURIComponent(d.image_path)}&loc=${encodeURIComponent(d.location)}&t=${Date.now()}`;
    setText('satTag', `${d.sensor} · ${d.time}`);

    /* Sidebar rain values */
    if (d.district_scan) {
        distList.querySelectorAll('.d-item').forEach(el => {
            const match = d.district_scan.find(x => x.district === el.dataset.loc);
            const span  = el.querySelector('.d-rain');
            if (span && match) {
                span.textContent  = match.rainfall_mm.toFixed(1) + ' mm';
                span.style.color  = rainColor(match.rainfall_mm);
            }
        });
    }

    showToast(`${d.location} — ${d.condition}`, 'success');
}

/* ─── Helpers ────────────────────────────────────────────── */
function rainColor(mm) {
    if (mm === 0)  return '#10b981';
    if (mm < 7.5)  return '#06b6d4';
    if (mm < 35.5) return '#f59e0b';
    if (mm < 64.5) return '#ef4444';
    return '#8b5cf6';
}

function showToast(msg, type) {
    const t = document.getElementById('toast');
    document.getElementById('toastMsg').textContent  = msg;
    document.getElementById('toastIcon').className   =
        type === 'error' ? 'fa-solid fa-circle-exclamation' : 'fa-solid fa-circle-check';
    t.className = `toast ${type} show`;
    clearTimeout(t._t);
    t._t = setTimeout(() => t.classList.remove('show'), 3500);
}

function setText(id, val) {
    const el = document.getElementById(id);
    if (el) el.textContent = val;
}
