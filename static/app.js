// ── State ──
let charts = {};
let dashboardData = null;

// ── Chart.js defaults ──
Chart.defaults.color = '#8888aa';
Chart.defaults.borderColor = '#2a2a4a';
Chart.defaults.font.family = 'system-ui, sans-serif';
Chart.defaults.plugins.legend.display = false;
Chart.defaults.animation.duration = 400;

const COLORS = {
    accent: '#4cc9f0',
    accent2: '#f72585',
    accent3: '#7209b7',
    accent4: '#4361ee',
    deep: '#3a0ca3',
    light: '#4895ef',
    rem: '#7209b7',
    awake: '#f72585',
    positive: '#06d6a0',
    negative: '#ef476f',
};

const TYPE_COLORS = {
    running: '#06d6a0',
    cycling: '#4cc9f0',
    swimming: '#4361ee',
    walking: '#f77f00',
    strength_training: '#f72585',
    hiking: '#7209b7',
    other: '#8888aa',
};

// ── Utilities ──
function fmt(n, decimals = 0) {
    if (n == null) return '—';
    return Number(n).toLocaleString(undefined, {
        minimumFractionDigits: decimals,
        maximumFractionDigits: decimals,
    });
}

function fmtDuration(seconds) {
    if (!seconds) return '—';
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    return h > 0 ? `${h}h ${m}m` : `${m}m`;
}

function fmtDistance(meters) {
    if (!meters) return '—';
    return (meters / 1000).toFixed(2) + ' km';
}

function fmtDate(iso) {
    if (!iso) return '—';
    return new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}

function fmtDateShort(iso) {
    if (!iso) return '';
    const d = new Date(iso);
    return `${d.getMonth() + 1}/${d.getDate()}`;
}

function getOrCreateChart(canvasId, config) {
    if (charts[canvasId]) {
        charts[canvasId].destroy();
    }
    const ctx = document.getElementById(canvasId);
    if (!ctx) return null;
    charts[canvasId] = new Chart(ctx, config);
    return charts[canvasId];
}

async function api(path, options = {}) {
    const res = await fetch(`/api${path}`, {
        headers: { 'Content-Type': 'application/json' },
        ...options,
    });
    if (!res.ok) throw new Error(`API error: ${res.status}`);
    return res.json();
}

// ── Tab Navigation ──
document.querySelectorAll('.tabs button').forEach(btn => {
    btn.addEventListener('click', () => {
        document.querySelectorAll('.tabs button').forEach(b => b.classList.remove('active'));
        document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
        btn.classList.add('active');
        document.getElementById(`tab-${btn.dataset.tab}`).classList.add('active');

        // Load data for tab on first visit
        if (btn.dataset.tab === 'activities') loadActivities();
        if (btn.dataset.tab === 'sleep') loadSleepTab();
        if (btn.dataset.tab === 'body') loadBodyTab();
        if (btn.dataset.tab === 'journal') loadJournal();
    });
});

// ── Sync ──
async function triggerSync() {
    const btn = document.getElementById('sync-btn');
    btn.disabled = true;
    btn.textContent = 'Syncing...';
    document.getElementById('sync-status').innerHTML = '<span class="spinner"></span>Syncing...';

    try {
        await api('/sync/all', { method: 'POST' });
        pollSyncStatus();
    } catch (e) {
        document.getElementById('sync-status').textContent = 'Sync failed: ' + e.message;
        btn.disabled = false;
        btn.textContent = 'Sync Now';
    }
}

let syncPollInterval = null;

function pollSyncStatus() {
    if (syncPollInterval) clearInterval(syncPollInterval);
    syncPollInterval = setInterval(async () => {
        try {
            const statuses = await api('/sync/status');
            const syncing = statuses.filter(s => s.status === 'syncing');
            const statusEl = document.getElementById('sync-status');

            if (syncing.length > 0) {
                const current = syncing[0];
                statusEl.innerHTML = `<span class="spinner"></span>${current.progress || 'Syncing ' + current.data_type + '...'}`;
            } else {
                clearInterval(syncPollInterval);
                syncPollInterval = null;
                const btn = document.getElementById('sync-btn');
                btn.disabled = false;
                btn.textContent = 'Sync Now';

                const errors = statuses.filter(s => s.status === 'error');
                if (errors.length > 0) {
                    statusEl.textContent = `Done with ${errors.length} error(s)`;
                } else if (statuses.length > 0) {
                    const latest = statuses
                        .filter(s => s.last_sync_at)
                        .sort((a, b) => new Date(b.last_sync_at) - new Date(a.last_sync_at))[0];
                    statusEl.textContent = latest
                        ? `Last sync: ${new Date(latest.last_sync_at).toLocaleString()}`
                        : 'Sync complete';
                } else {
                    statusEl.textContent = 'Sync complete';
                }
                // Refresh dashboard data
                loadDashboard();
            }
        } catch (e) {
            // ignore poll errors
        }
    }, 2000);
}

// ── Dashboard / Overview ──
async function loadDashboard() {
    const days = document.getElementById('overview-days').value;
    const customRange = document.getElementById('overview-custom-range');
    customRange.style.display = days === 'custom' ? '' : 'none';

    let url;
    if (days === 'custom') {
        const start = document.getElementById('overview-start').value;
        const end = document.getElementById('overview-end').value;
        if (!start && !end) return; // wait for user to pick dates
        url = '/dashboard?days=0';
        if (start) url += `&start=${start}`;
        if (end) url += `&end=${end}`;
    } else {
        url = `/dashboard?days=${days}`;
    }

    try {
        dashboardData = await api(url);
        renderSummaryCards(dashboardData);
        renderActivityChart(dashboardData.activities);
        renderSleepChart(dashboardData.sleep);
        renderHRChart(dashboardData.heart_rate, dashboardData.daily);
        renderStepsChart(dashboardData.daily);
        renderBatteryChart(dashboardData.daily);
    } catch (e) {
        console.error('Failed to load dashboard:', e);
    }
}

function renderSummaryCards(data) {
    const container = document.getElementById('summary-cards');
    const { activities, sleep, daily } = data;

    const now = new Date();
    const weekAgo = new Date(now - 7 * 86400000);
    const twoWeeksAgo = new Date(now - 14 * 86400000);

    // This week's stats
    const thisWeekActivities = activities.filter(a => new Date(a.start_time) >= weekAgo);
    const lastWeekActivities = activities.filter(a => {
        const d = new Date(a.start_time);
        return d >= twoWeeksAgo && d < weekAgo;
    });

    const thisWeekSteps = daily
        .filter(d => new Date(d.calendar_date) >= weekAgo)
        .reduce((sum, d) => sum + (d.steps || 0), 0);
    const lastWeekSteps = daily
        .filter(d => {
            const dt = new Date(d.calendar_date);
            return dt >= twoWeeksAgo && dt < weekAgo;
        })
        .reduce((sum, d) => sum + (d.steps || 0), 0);

    const recentSleep = sleep.filter(s => new Date(s.calendar_date) >= weekAgo);
    const prevSleep = sleep.filter(s => {
        const d = new Date(s.calendar_date);
        return d >= twoWeeksAgo && d < weekAgo;
    });

    const avgSleepThis = recentSleep.length
        ? recentSleep.reduce((s, x) => s + (x.total_sleep_seconds || 0), 0) / recentSleep.length
        : 0;
    const avgSleepPrev = prevSleep.length
        ? prevSleep.reduce((s, x) => s + (x.total_sleep_seconds || 0), 0) / prevSleep.length
        : 0;

    const recentHR = daily.filter(d => new Date(d.calendar_date) >= weekAgo && d.resting_hr);
    const avgHR = recentHR.length
        ? Math.round(recentHR.reduce((s, d) => s + d.resting_hr, 0) / recentHR.length)
        : null;

    function changeHtml(current, previous, unit = '', invert = false) {
        if (!previous || !current) return '';
        const diff = current - previous;
        const pct = previous !== 0 ? ((diff / previous) * 100).toFixed(0) : 0;
        const isPositive = invert ? diff < 0 : diff > 0;
        const cls = isPositive ? 'positive' : 'negative';
        const arrow = diff > 0 ? '&#9650;' : '&#9660;';
        return `<div class="change ${cls}">${arrow} ${Math.abs(pct)}% vs prev week</div>`;
    }

    container.innerHTML = `
        <div class="card">
            <div class="label">Weekly Steps</div>
            <div class="value">${fmt(thisWeekSteps)}</div>
            ${changeHtml(thisWeekSteps, lastWeekSteps)}
        </div>
        <div class="card">
            <div class="label">Activities (7d)</div>
            <div class="value">${thisWeekActivities.length}</div>
            ${changeHtml(thisWeekActivities.length, lastWeekActivities.length)}
        </div>
        <div class="card">
            <div class="label">Avg Sleep (7d)</div>
            <div class="value">${fmtDuration(avgSleepThis)}</div>
            ${changeHtml(avgSleepThis, avgSleepPrev)}
        </div>
        <div class="card">
            <div class="label">Resting HR</div>
            <div class="value">${avgHR ? avgHR + ' bpm' : '—'}</div>
        </div>
    `;
}

function renderActivityChart(activities) {
    // Group by date and type
    const byDate = {};
    const types = new Set();

    activities.forEach(a => {
        if (!a.start_time) return;
        const d = a.start_time.split('T')[0];
        const t = a.activity_type || 'other';
        types.add(t);
        if (!byDate[d]) byDate[d] = {};
        byDate[d][t] = (byDate[d][t] || 0) + (a.distance_meters || 0) / 1000;
    });

    const dates = Object.keys(byDate).sort();
    const datasets = Array.from(types).map(type => ({
        label: type.replace(/_/g, ' '),
        data: dates.map(d => byDate[d][type] || 0),
        backgroundColor: TYPE_COLORS[type] || TYPE_COLORS.other,
        borderRadius: 4,
    }));

    getOrCreateChart('chart-activities', {
        type: 'bar',
        data: { labels: dates.map(fmtDateShort), datasets },
        options: {
            responsive: true,
            plugins: { legend: { display: true, position: 'top' } },
            scales: {
                x: { stacked: true },
                y: { stacked: true, title: { display: true, text: 'km' } },
            },
        },
    });
}

function renderSleepChart(sleep) {
    const sorted = [...sleep].sort((a, b) => a.calendar_date.localeCompare(b.calendar_date));
    const labels = sorted.map(s => fmtDateShort(s.calendar_date));

    const toHours = s => (s || 0) / 3600;

    getOrCreateChart('chart-sleep', {
        type: 'bar',
        data: {
            labels,
            datasets: [
                { label: 'Deep', data: sorted.map(s => toHours(s.deep_seconds)), backgroundColor: COLORS.deep },
                { label: 'Light', data: sorted.map(s => toHours(s.light_seconds)), backgroundColor: COLORS.light },
                { label: 'REM', data: sorted.map(s => toHours(s.rem_seconds)), backgroundColor: COLORS.rem },
                { label: 'Awake', data: sorted.map(s => toHours(s.awake_seconds)), backgroundColor: COLORS.awake },
            ],
        },
        options: {
            responsive: true,
            plugins: { legend: { display: true, position: 'top' } },
            scales: {
                x: { stacked: true },
                y: { stacked: true, title: { display: true, text: 'hours' } },
            },
        },
    });
}

function renderHRChart(hrData, dailyData) {
    // Prefer heart_rate table, fall back to daily resting HR
    let source = hrData.filter(h => h.resting_hr);
    if (source.length === 0) {
        source = dailyData.filter(d => d.resting_hr).map(d => ({
            calendar_date: d.calendar_date,
            resting_hr: d.resting_hr,
        }));
    }
    const sorted = [...source].sort((a, b) => a.calendar_date.localeCompare(b.calendar_date));

    getOrCreateChart('chart-hr', {
        type: 'line',
        data: {
            labels: sorted.map(h => fmtDateShort(h.calendar_date)),
            datasets: [{
                label: 'Resting HR',
                data: sorted.map(h => h.resting_hr),
                borderColor: COLORS.accent2,
                backgroundColor: COLORS.accent2 + '33',
                fill: true,
                tension: 0.3,
                pointRadius: 2,
            }],
        },
        options: {
            responsive: true,
            scales: { y: { title: { display: true, text: 'bpm' } } },
        },
    });
}

function renderStepsChart(daily) {
    const sorted = [...daily].sort((a, b) => a.calendar_date.localeCompare(b.calendar_date));

    getOrCreateChart('chart-steps', {
        type: 'bar',
        data: {
            labels: sorted.map(d => fmtDateShort(d.calendar_date)),
            datasets: [{
                label: 'Steps',
                data: sorted.map(d => d.steps),
                backgroundColor: COLORS.accent4,
                borderRadius: 4,
            }],
        },
        options: {
            responsive: true,
            scales: { y: { title: { display: true, text: 'steps' } } },
        },
    });
}

function renderBatteryChart(daily) {
    const sorted = [...daily]
        .filter(d => d.body_battery_high != null)
        .sort((a, b) => a.calendar_date.localeCompare(b.calendar_date));

    getOrCreateChart('chart-battery', {
        type: 'line',
        data: {
            labels: sorted.map(d => fmtDateShort(d.calendar_date)),
            datasets: [
                {
                    label: 'High',
                    data: sorted.map(d => d.body_battery_high),
                    borderColor: COLORS.positive,
                    backgroundColor: COLORS.positive + '33',
                    fill: true,
                    tension: 0.3,
                    pointRadius: 2,
                },
                {
                    label: 'Low',
                    data: sorted.map(d => d.body_battery_low),
                    borderColor: COLORS.negative,
                    backgroundColor: COLORS.negative + '33',
                    fill: true,
                    tension: 0.3,
                    pointRadius: 2,
                },
            ],
        },
        options: {
            responsive: true,
            plugins: { legend: { display: true } },
            scales: { y: { min: 0, max: 100, title: { display: true, text: 'battery' } } },
        },
    });
}

// ── Activities Tab ──
async function loadActivities() {
    const type = document.getElementById('activity-type-filter').value;
    const start = document.getElementById('activity-start').value;
    const end = document.getElementById('activity-end').value;

    let url = '/activities?limit=200';
    if (type) url += `&type=${type}`;
    if (start) url += `&start=${start}`;
    if (end) url += `&end=${end}`;

    try {
        const activities = await api(url);
        const tbody = document.getElementById('activities-table');

        // Populate type filter if empty
        const filter = document.getElementById('activity-type-filter');
        if (filter.options.length <= 1 && activities.length > 0) {
            const types = [...new Set(activities.map(a => a.activity_type).filter(Boolean))].sort();
            types.forEach(t => {
                const opt = document.createElement('option');
                opt.value = t;
                opt.textContent = t.replace(/_/g, ' ');
                filter.appendChild(opt);
            });
        }

        if (activities.length === 0) {
            tbody.innerHTML = '<tr><td colspan="8" class="empty-state">No activities found. Try syncing first.</td></tr>';
            return;
        }

        tbody.innerHTML = activities.map(a => `
            <tr>
                <td>${fmtDate(a.start_time)}</td>
                <td>${(a.activity_type || '').replace(/_/g, ' ')}</td>
                <td>${a.activity_name || '—'}</td>
                <td>${fmtDuration(a.duration_seconds)}</td>
                <td>${fmtDistance(a.distance_meters)}</td>
                <td>${a.avg_hr || '—'}</td>
                <td>${fmt(a.calories)}</td>
                <td>${a.vo2max ? fmt(a.vo2max, 1) : '—'}</td>
            </tr>
        `).join('');
    } catch (e) {
        console.error('Failed to load activities:', e);
    }
}

// ── Sleep Tab ──
async function loadSleepTab() {
    const days = parseInt(document.getElementById('sleep-days').value);
    let url = '/sleep?limit=1000';
    if (days > 0) {
        const start = new Date(Date.now() - days * 86400000).toISOString().split('T')[0];
        url += `&start=${start}`;
    }

    try {
        const sleep = await api(url);
        const sorted = [...sleep].sort((a, b) => a.calendar_date.localeCompare(b.calendar_date));

        // Sleep score trend
        const withScore = sorted.filter(s => s.sleep_score);
        getOrCreateChart('chart-sleep-score', {
            type: 'line',
            data: {
                labels: withScore.map(s => fmtDateShort(s.calendar_date)),
                datasets: [{
                    label: 'Sleep Score',
                    data: withScore.map(s => s.sleep_score),
                    borderColor: COLORS.accent,
                    backgroundColor: COLORS.accent + '33',
                    fill: true,
                    tension: 0.3,
                    pointRadius: 3,
                }],
            },
            options: {
                responsive: true,
                scales: { y: { min: 0, max: 100, title: { display: true, text: 'score' } } },
            },
        });

        // Average sleep by day of week
        const dayNames = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
        const byDow = Array(7).fill(null).map(() => []);
        sorted.forEach(s => {
            if (s.total_sleep_seconds) {
                const dow = new Date(s.calendar_date).getDay();
                byDow[dow].push(s.total_sleep_seconds / 3600);
            }
        });
        const avgByDow = byDow.map(arr => arr.length ? arr.reduce((a, b) => a + b, 0) / arr.length : 0);

        getOrCreateChart('chart-sleep-dow', {
            type: 'bar',
            data: {
                labels: dayNames,
                datasets: [{
                    label: 'Avg Sleep (hours)',
                    data: avgByDow,
                    backgroundColor: COLORS.accent3,
                    borderRadius: 4,
                }],
            },
            options: {
                responsive: true,
                scales: { y: { title: { display: true, text: 'hours' } } },
            },
        });

        // Sleep duration trend
        getOrCreateChart('chart-sleep-duration', {
            type: 'line',
            data: {
                labels: sorted.map(s => fmtDateShort(s.calendar_date)),
                datasets: [{
                    label: 'Total Sleep',
                    data: sorted.map(s => (s.total_sleep_seconds || 0) / 3600),
                    borderColor: COLORS.accent4,
                    backgroundColor: COLORS.accent4 + '33',
                    fill: true,
                    tension: 0.3,
                    pointRadius: 2,
                }],
            },
            options: {
                responsive: true,
                scales: { y: { title: { display: true, text: 'hours' } } },
            },
        });
    } catch (e) {
        console.error('Failed to load sleep tab:', e);
    }
}

// ── Body Tab ──
async function loadBodyTab() {
    const days = parseInt(document.getElementById('body-days').value);
    let url = '/body?limit=1000';
    if (days > 0) {
        const start = new Date(Date.now() - days * 86400000).toISOString().split('T')[0];
        url += `&start=${start}`;
    }

    try {
        const body = await api(url);
        const sorted = [...body].sort((a, b) => a.calendar_date.localeCompare(b.calendar_date));
        const withWeight = sorted.filter(b => b.weight_kg);

        getOrCreateChart('chart-weight', {
            type: 'line',
            data: {
                labels: withWeight.map(b => fmtDateShort(b.calendar_date)),
                datasets: [{
                    label: 'Weight (kg)',
                    data: withWeight.map(b => b.weight_kg),
                    borderColor: COLORS.accent,
                    backgroundColor: COLORS.accent + '33',
                    fill: true,
                    tension: 0.3,
                    pointRadius: 3,
                }],
            },
            options: {
                responsive: true,
                scales: { y: { title: { display: true, text: 'kg' } } },
            },
        });

        const withFat = sorted.filter(b => b.body_fat_pct);
        getOrCreateChart('chart-bodyfat', {
            type: 'line',
            data: {
                labels: withFat.map(b => fmtDateShort(b.calendar_date)),
                datasets: [{
                    label: 'Body Fat %',
                    data: withFat.map(b => b.body_fat_pct),
                    borderColor: COLORS.accent2,
                    tension: 0.3,
                    pointRadius: 3,
                }],
            },
            options: {
                responsive: true,
                scales: { y: { title: { display: true, text: '%' } } },
            },
        });

        const withBmi = sorted.filter(b => b.bmi);
        getOrCreateChart('chart-bmi', {
            type: 'line',
            data: {
                labels: withBmi.map(b => fmtDateShort(b.calendar_date)),
                datasets: [{
                    label: 'BMI',
                    data: withBmi.map(b => b.bmi),
                    borderColor: COLORS.accent3,
                    tension: 0.3,
                    pointRadius: 3,
                }],
            },
            options: {
                responsive: true,
                scales: { y: { title: { display: true, text: 'BMI' } } },
            },
        });
    } catch (e) {
        console.error('Failed to load body tab:', e);
    }
}

// ── Journal ──
async function loadJournal() {
    try {
        const entries = await api('/journal?limit=100');
        const container = document.getElementById('journal-entries');

        if (entries.length === 0) {
            container.innerHTML = '<div class="empty-state">No journal entries yet. Add one above.</div>';
            return;
        }

        container.innerHTML = entries.map(e => `
            <div class="journal-entry">
                <div class="content">
                    <div class="meta">
                        ${fmtDate(e.entry_date)}
                        <span class="badge">${e.category}</span>
                        ${e.rating ? '&nbsp; ' + '★'.repeat(Math.min(e.rating, 10)) : ''}
                        ${e.tags ? '&nbsp; ' + e.tags.split(',').map(t => `<span class="badge">${t.trim()}</span>`).join('') : ''}
                    </div>
                    <div>${e.content}</div>
                </div>
                <div class="actions">
                    <button class="secondary" onclick="editJournal(${e.id})">Edit</button>
                    <button class="secondary" onclick="deleteJournal(${e.id})">Delete</button>
                </div>
            </div>
        `).join('');
    } catch (e) {
        console.error('Failed to load journal:', e);
    }
}

async function saveJournal() {
    const id = document.getElementById('journal-edit-id').value;
    const body = {
        entry_date: document.getElementById('journal-date').value || new Date().toISOString().split('T')[0],
        category: document.getElementById('journal-category').value,
        content: document.getElementById('journal-content').value,
        rating: document.getElementById('journal-rating').value
            ? parseInt(document.getElementById('journal-rating').value)
            : null,
        tags: document.getElementById('journal-tags').value || null,
    };

    try {
        if (id) {
            await api(`/journal/${id}`, { method: 'PUT', body: JSON.stringify(body) });
        } else {
            await api('/journal', { method: 'POST', body: JSON.stringify(body) });
        }
        resetJournalForm();
        loadJournal();
    } catch (e) {
        console.error('Failed to save journal:', e);
    }
}

async function editJournal(id) {
    try {
        const entries = await api('/journal?limit=500');
        const entry = entries.find(e => e.id === id);
        if (!entry) return;

        document.getElementById('journal-edit-id').value = entry.id;
        document.getElementById('journal-date').value = entry.entry_date;
        document.getElementById('journal-category').value = entry.category;
        document.getElementById('journal-content').value = entry.content;
        document.getElementById('journal-rating').value = entry.rating || '';
        document.getElementById('journal-tags').value = entry.tags || '';
        document.getElementById('journal-form-title').textContent = 'Edit Entry';
    } catch (e) {
        console.error('Failed to load journal entry:', e);
    }
}

async function deleteJournal(id) {
    if (!confirm('Delete this journal entry?')) return;
    try {
        await api(`/journal/${id}`, { method: 'DELETE' });
        loadJournal();
    } catch (e) {
        console.error('Failed to delete journal:', e);
    }
}

function resetJournalForm() {
    document.getElementById('journal-edit-id').value = '';
    document.getElementById('journal-date').value = new Date().toISOString().split('T')[0];
    document.getElementById('journal-category').value = 'general';
    document.getElementById('journal-content').value = '';
    document.getElementById('journal-rating').value = '';
    document.getElementById('journal-tags').value = '';
    document.getElementById('journal-form-title').textContent = 'New Entry';
}

// ── Init ──
async function init() {
    // Set default journal date
    document.getElementById('journal-date').value = new Date().toISOString().split('T')[0];

    // Load sync status
    try {
        const statuses = await api('/sync/status');
        if (statuses.length > 0) {
            const latest = statuses
                .filter(s => s.last_sync_at)
                .sort((a, b) => new Date(b.last_sync_at) - new Date(a.last_sync_at))[0];
            if (latest) {
                document.getElementById('sync-status').textContent =
                    `Last sync: ${new Date(latest.last_sync_at).toLocaleString()}`;
            }
            // Check if any are still syncing
            if (statuses.some(s => s.status === 'syncing')) {
                pollSyncStatus();
            }
        }
    } catch (e) {
        // No sync status yet
    }

    // Load dashboard
    loadDashboard();
}

init();
