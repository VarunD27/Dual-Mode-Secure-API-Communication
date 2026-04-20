/**
 * Dashboard Script — Chart.js visualizations with auto-polling.
 * NPS Lab 6th Sem — Adaptive Protocol Dashboard
 */

// ── Configuration ──
const POLL_INTERVAL = 2000; // ms
const API_URL = '/api/logs';

// ── Chart Instances ──
let timelineChart = null;
let rttChart = null;
let handshakeChart = null;
let scoresChart = null;

// ── State ──
let previousDataLength = 0;

// ── Color Palette ──
const COLORS = {
    tls: {
        main: 'rgba(99, 102, 241, 1)',
        fill: 'rgba(99, 102, 241, 0.15)',
        border: 'rgba(99, 102, 241, 0.8)',
    },
    tcp: {
        main: 'rgba(6, 182, 212, 1)',
        fill: 'rgba(6, 182, 212, 0.15)',
        border: 'rgba(6, 182, 212, 0.8)',
    },
    amber: {
        main: 'rgba(245, 158, 11, 1)',
        fill: 'rgba(245, 158, 11, 0.15)',
    },
    green: {
        main: 'rgba(16, 185, 129, 1)',
        fill: 'rgba(16, 185, 129, 0.15)',
    },
    grid: 'rgba(255, 255, 255, 0.05)',
    gridText: 'rgba(148, 163, 184, 0.7)',
};


// ── Common Chart Options ──
const commonOptions = {
    responsive: true,
    maintainAspectRatio: false,
    animation: {
        duration: 600,
        easing: 'easeOutQuart',
    },
    interaction: {
        intersect: false,
        mode: 'index',
    },
    plugins: {
        legend: {
            display: true,
            position: 'top',
            align: 'end',
            labels: {
                color: COLORS.gridText,
                font: { family: "'Inter', sans-serif", size: 11, weight: '500' },
                boxWidth: 12,
                boxHeight: 12,
                borderRadius: 3,
                useBorderRadius: true,
                padding: 16,
            },
        },
        tooltip: {
            backgroundColor: 'rgba(15, 15, 46, 0.95)',
            titleColor: '#e2e8f0',
            bodyColor: '#94a3b8',
            borderColor: 'rgba(255, 255, 255, 0.1)',
            borderWidth: 1,
            cornerRadius: 8,
            padding: 12,
            titleFont: { family: "'Inter', sans-serif", size: 12, weight: '600' },
            bodyFont: { family: "'JetBrains Mono', monospace", size: 11 },
            displayColors: true,
        },
    },
    scales: {
        x: {
            grid: { color: COLORS.grid, drawBorder: false },
            ticks: {
                color: COLORS.gridText,
                font: { family: "'JetBrains Mono', monospace", size: 10 },
                maxRotation: 0,
            },
            border: { display: false },
        },
        y: {
            grid: { color: COLORS.grid, drawBorder: false },
            ticks: {
                color: COLORS.gridText,
                font: { family: "'JetBrains Mono', monospace", size: 10 },
            },
            border: { display: false },
        },
    },
};


// ── Initialize Charts ──
function initCharts() {
    // 1. Protocol Timeline (bar chart showing which protocol per request)
    const tlCtx = document.getElementById('chart-timeline').getContext('2d');
    timelineChart = new Chart(tlCtx, {
        type: 'bar',
        data: {
            labels: [],
            datasets: [{
                label: 'Protocol',
                data: [],
                backgroundColor: [],
                borderColor: [],
                borderWidth: 1,
                borderRadius: 4,
                barPercentage: 0.7,
            }],
        },
        options: {
            ...commonOptions,
            plugins: {
                ...commonOptions.plugins,
                legend: { display: false },
                tooltip: {
                    ...commonOptions.plugins.tooltip,
                    callbacks: {
                        label: (ctx) => {
                            return ctx.raw === 1 ? '🔒 TLS (Secure)' : '⚡ TCP (Fast)';
                        },
                    },
                },
            },
            scales: {
                ...commonOptions.scales,
                y: {
                    ...commonOptions.scales.y,
                    min: 0,
                    max: 1.5,
                    ticks: {
                        ...commonOptions.scales.y.ticks,
                        callback: (val) => val === 1 ? 'TLS' : val === 0 ? 'TCP' : '',
                        stepSize: 1,
                    },
                },
                x: {
                    ...commonOptions.scales.x,
                    ticks: {
                        ...commonOptions.scales.x.ticks,
                        maxTicksLimit: 20,
                    },
                },
            },
        },
    });

    // 2. RTT Comparison (line chart)
    const rttCtx = document.getElementById('chart-rtt').getContext('2d');
    rttChart = new Chart(rttCtx, {
        type: 'line',
        data: {
            labels: [],
            datasets: [
                {
                    label: 'TLS RTT',
                    data: [],
                    borderColor: COLORS.tls.main,
                    backgroundColor: COLORS.tls.fill,
                    fill: true,
                    tension: 0.4,
                    pointRadius: 3,
                    pointHoverRadius: 6,
                    borderWidth: 2,
                },
                {
                    label: 'TCP RTT',
                    data: [],
                    borderColor: COLORS.tcp.main,
                    backgroundColor: COLORS.tcp.fill,
                    fill: true,
                    tension: 0.4,
                    pointRadius: 3,
                    pointHoverRadius: 6,
                    borderWidth: 2,
                },
            ],
        },
        options: {
            ...commonOptions,
            scales: {
                ...commonOptions.scales,
                y: {
                    ...commonOptions.scales.y,
                    title: {
                        display: true,
                        text: 'RTT (ms)',
                        color: COLORS.gridText,
                        font: { size: 11 },
                    },
                },
            },
        },
    });

    // 3. Handshake Overhead (bar chart)
    const hsCtx = document.getElementById('chart-handshake').getContext('2d');
    handshakeChart = new Chart(hsCtx, {
        type: 'bar',
        data: {
            labels: [],
            datasets: [
                {
                    label: 'TLS Handshake',
                    data: [],
                    backgroundColor: COLORS.tls.fill,
                    borderColor: COLORS.tls.border,
                    borderWidth: 1,
                    borderRadius: 4,
                },
                {
                    label: 'TCP Handshake',
                    data: [],
                    backgroundColor: COLORS.tcp.fill,
                    borderColor: COLORS.tcp.border,
                    borderWidth: 1,
                    borderRadius: 4,
                },
            ],
        },
        options: {
            ...commonOptions,
            scales: {
                ...commonOptions.scales,
                y: {
                    ...commonOptions.scales.y,
                    title: {
                        display: true,
                        text: 'Time (ms)',
                        color: COLORS.gridText,
                        font: { size: 11 },
                    },
                },
                x: {
                    ...commonOptions.scales.x,
                    ticks: {
                        ...commonOptions.scales.x.ticks,
                        maxTicksLimit: 15,
                    },
                },
            },
        },
    });

    // 4. Score Divergence (line chart)
    const scCtx = document.getElementById('chart-scores').getContext('2d');
    scoresChart = new Chart(scCtx, {
        type: 'line',
        data: {
            labels: [],
            datasets: [
                {
                    label: 'TLS Score',
                    data: [],
                    borderColor: COLORS.tls.main,
                    backgroundColor: COLORS.tls.fill,
                    fill: true,
                    tension: 0.4,
                    pointRadius: 3,
                    pointHoverRadius: 6,
                    borderWidth: 2,
                },
                {
                    label: 'TCP Score',
                    data: [],
                    borderColor: COLORS.tcp.main,
                    backgroundColor: COLORS.tcp.fill,
                    fill: true,
                    tension: 0.4,
                    pointRadius: 3,
                    pointHoverRadius: 6,
                    borderWidth: 2,
                },
            ],
        },
        options: {
            ...commonOptions,
            scales: {
                ...commonOptions.scales,
                y: {
                    ...commonOptions.scales.y,
                    title: {
                        display: true,
                        text: 'Cost Score',
                        color: COLORS.gridText,
                        font: { size: 11 },
                    },
                },
            },
        },
    });
}


// ── Update Dashboard ──
function updateDashboard(logs) {
    if (!logs || logs.length === 0) return;

    const labels = logs.map(l => `#${l.request_id}`);
    const tlsRtts = [];
    const tcpRtts = [];
    const tlsHandshakes = [];
    const tcpHandshakes = [];
    const tlsScores = [];
    const tcpScores = [];
    const protocolValues = [];
    const protocolColors = [];
    const protocolBorders = [];

    let switchCount = 0;
    let prevProto = null;
    let totalRtt = 0;

    logs.forEach((log) => {
        const isTLS = log.protocol === 'TLS';

        // Protocol timeline
        protocolValues.push(isTLS ? 1 : 0);
        protocolColors.push(isTLS ? COLORS.tls.fill : COLORS.tcp.fill);
        protocolBorders.push(isTLS ? COLORS.tls.main : COLORS.tcp.main);

        // RTT — split by protocol
        if (isTLS) {
            tlsRtts.push(log.rtt_ms);
            tcpRtts.push(null);
        } else {
            tcpRtts.push(log.rtt_ms);
            tlsRtts.push(null);
        }

        // Handshake
        tlsHandshakes.push(isTLS ? log.handshake_time_ms : null);
        tcpHandshakes.push(!isTLS ? log.handshake_time_ms : null);

        // Scores
        tlsScores.push(log.tls_score);
        tcpScores.push(log.tcp_score);

        // Count switches
        if (prevProto && log.protocol !== prevProto) switchCount++;
        prevProto = log.protocol;

        totalRtt += log.rtt_ms;
    });

    const lastLog = logs[logs.length - 1];

    // ── Update Stats Cards ──
    document.getElementById('total-requests').textContent = logs.length;
    document.getElementById('current-protocol').textContent = lastLog.protocol;
    document.getElementById('avg-rtt').textContent = `${(totalRtt / logs.length).toFixed(1)}ms`;
    document.getElementById('switch-count').textContent = switchCount;

    // Update status badge
    const statusDot = document.querySelector('.status-dot');
    const statusText = document.querySelector('.status-text');
    statusDot.classList.add('active');
    statusText.textContent = `${lastLog.protocol} Active — ${logs.length} requests`;

    // Color the protocol stat card
    const protoCard = document.getElementById('stat-protocol');
    if (lastLog.protocol === 'TLS') {
        protoCard.style.borderColor = 'rgba(99, 102, 241, 0.3)';
    } else {
        protoCard.style.borderColor = 'rgba(6, 182, 212, 0.3)';
    }

    // ── Update Charts ──
    // Timeline
    timelineChart.data.labels = labels;
    timelineChart.data.datasets[0].data = protocolValues;
    timelineChart.data.datasets[0].backgroundColor = protocolColors;
    timelineChart.data.datasets[0].borderColor = protocolBorders;
    timelineChart.update('none');

    // RTT
    rttChart.data.labels = labels;
    rttChart.data.datasets[0].data = tlsRtts;
    rttChart.data.datasets[1].data = tcpRtts;
    rttChart.update('none');

    // Handshake
    handshakeChart.data.labels = labels;
    handshakeChart.data.datasets[0].data = tlsHandshakes;
    handshakeChart.data.datasets[1].data = tcpHandshakes;
    handshakeChart.update('none');

    // Scores
    scoresChart.data.labels = labels;
    scoresChart.data.datasets[0].data = tlsScores;
    scoresChart.data.datasets[1].data = tcpScores;
    scoresChart.update('none');

    // ── Update Log Table ──
    updateLogTable(logs);
}


// ── Update Log Table ──
function updateLogTable(logs) {
    const tbody = document.getElementById('log-tbody');

    // Show last 50 logs, most recent first
    const recentLogs = logs.slice(-50).reverse();

    tbody.innerHTML = recentLogs.map(log => {
        const isTLS = log.protocol === 'TLS';
        const protoClass = isTLS ? 'proto-tls' : 'proto-tcp';
        const protoIcon = isTLS ? '🔒' : '⚡';
        const statusClass = log.status === 'ok' ? 'status-ok' : 'status-error';
        const time = new Date(log.timestamp * 1000).toLocaleTimeString();

        return `<tr>
            <td>${log.request_id}</td>
            <td>${time}</td>
            <td><span class="proto-badge ${protoClass}">${protoIcon} ${log.protocol}</span></td>
            <td>${log.action}</td>
            <td>${log.rtt_ms.toFixed(1)}</td>
            <td>${log.handshake_time_ms.toFixed(1)}</td>
            <td>${log.payload_size}</td>
            <td>${log.tls_score.toFixed(2)}</td>
            <td>${log.tcp_score.toFixed(2)}</td>
            <td class="${statusClass}">${log.status}</td>
        </tr>`;
    }).join('');
}


// ── Fetch and Refresh ──
async function fetchLogs() {
    try {
        const response = await fetch(API_URL);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const logs = await response.json();

        if (logs.length !== previousDataLength) {
            updateDashboard(logs);
            previousDataLength = logs.length;
        }
    } catch (err) {
        // Silently handle errors (server might not be running yet)
        console.debug('Fetch error:', err.message);
    }
}


// ── Main ──
document.addEventListener('DOMContentLoaded', () => {
    initCharts();
    fetchLogs();
    setInterval(fetchLogs, POLL_INTERVAL);
});
