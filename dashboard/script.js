/**
 * Dashboard Script — Chart.js visualizations with auto-polling.
 * NPS Lab 6th Sem — Adaptive Protocol Dashboard
 */

// ── Configuration ──
const POLL_INTERVAL = 3000; // ms - Increased to reduce glitch
const API_URL = '/api/logs';

// ── Chart Instances ──
let timelineChart = null;
let rttChart = null;
let outcomeChart = null;
let scoresChart = null;
let decisionBreakdownChart = null;

// ── State ──
let previousDataLength = 0;
let hasShownCompletionNotification = false;
let lastRequestId = 0;

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
    // 1. Protocol Timeline (bar chart with colored bars for TLS and TCP)
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
                barPercentage: 0.6,
                categoryPercentage: 0.7,
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
                            const protocol = ctx.raw.protocol;
                            return protocol === 'TLS' ? '🔒 TLS (Secure)' : '⚡ TCP (Fast)';
                        },
                    },
                },
            },
            scales: {
                ...commonOptions.scales,
                y: {
                    ...commonOptions.scales.y,
                    min: -0.2,
                    max: 1.2,
                    ticks: {
                        ...commonOptions.scales.y.ticks,
                        callback: (val) => val === 1 ? 'TLS' : val === 0 ? 'TCP' : '',
                        stepSize: 1,
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
                    pointRadius: 4,
                    pointHoverRadius: 6,
                    pointStyle: 'rect',
                    borderWidth: 2,
                },
                {
                    label: 'TCP RTT',
                    data: [],
                    borderColor: COLORS.tcp.main,
                    backgroundColor: COLORS.tcp.fill,
                    fill: true,
                    tension: 0.4,
                    pointRadius: 4,
                    pointHoverRadius: 6,
                    pointStyle: 'rect',
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

    // 3. Request Outcome (bar chart)
    const outCtx = document.getElementById('chart-outcome').getContext('2d');
    outcomeChart = new Chart(outCtx, {
        type: 'bar',
        data: {
            labels: [],
            datasets: [
                {
                    label: 'Outcome',
                    data: [],
                    backgroundColor: [],
                    borderColor: [],
                    borderWidth: 1,
                    borderRadius: 4,
                    barPercentage: 0.6,
                    categoryPercentage: 0.7,
                },
            ],
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
                            const val = ctx.raw;
                            return val === 1 ? 'Success' : 'Failed';
                        },
                    },
                },
            },
            scales: {
                ...commonOptions.scales,
                y: {
                    ...commonOptions.scales.y,
                    min: -0.2,
                    max: 1.2,
                    ticks: {
                        ...commonOptions.scales.y.ticks,
                        callback: (val) => val === 1 ? 'Success' : val === 0 ? 'Failed' : '',
                        stepSize: 1,
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
                    pointRadius: 4,
                    pointHoverRadius: 6,
                    pointStyle: 'rect',
                    borderWidth: 2,
                },
                {
                    label: 'TCP Score',
                    data: [],
                    borderColor: COLORS.tcp.main,
                    backgroundColor: COLORS.tcp.fill,
                    fill: true,
                    tension: 0.4,
                    pointRadius: 4,
                    pointHoverRadius: 6,
                    pointStyle: 'rect',
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

    // 5. Decision Component Breakdown (stacked bar chart)
    const decCtx = document.getElementById('chart-decision-breakdown').getContext('2d');
    decisionBreakdownChart = new Chart(decCtx, {
        type: 'bar',
        data: {
            labels: [],
            datasets: [
                {
                    label: 'Latency',
                    data: [],
                    backgroundColor: 'rgba(99, 102, 241, 0.7)',
                    borderColor: 'rgba(99, 102, 241, 1)',
                    borderWidth: 1,
                    borderRadius: 2,
                    stack: 'Stack 0',
                },
                {
                    label: 'Handshake',
                    data: [],
                    backgroundColor: 'rgba(168, 85, 247, 0.7)',
                    borderColor: 'rgba(168, 85, 247, 1)',
                    borderWidth: 1,
                    borderRadius: 2,
                    stack: 'Stack 0',
                },
                {
                    label: 'Payload',
                    data: [],
                    backgroundColor: 'rgba(6, 182, 212, 0.7)',
                    borderColor: 'rgba(6, 182, 212, 1)',
                    borderWidth: 1,
                    borderRadius: 2,
                    stack: 'Stack 0',
                },
                {
                    label: 'Security',
                    data: [],
                    backgroundColor: 'rgba(16, 185, 129, 0.7)',
                    borderColor: 'rgba(16, 185, 129, 1)',
                    borderWidth: 1,
                    borderRadius: 2,
                    stack: 'Stack 0',
                },
                {
                    label: 'Reliability',
                    data: [],
                    backgroundColor: 'rgba(245, 158, 11, 0.7)',
                    borderColor: 'rgba(245, 158, 11, 1)',
                    borderWidth: 1,
                    borderRadius: 2,
                    stack: 'Stack 0',
                },
            ],
        },
        options: {
            ...commonOptions,
            plugins: {
                ...commonOptions.plugins,
                legend: {
                    display: true,
                    position: 'top',
                    labels: {
                        color: COLORS.gridText,
                        font: { family: "'Inter', sans-serif", size: 11, weight: '500' },
                        boxWidth: 10,
                        boxHeight: 10,
                        borderRadius: 2,
                        useBorderRadius: true,
                        padding: 8,
                    },
                },
                tooltip: {
                    ...commonOptions.plugins.tooltip,
                    callbacks: {
                        footer: (tooltipItems) => {
                            let total = 0;
                            tooltipItems.forEach((item) => {
                                total += item.parsed.y || 0;
                            });
                            return `Total Score: ${total.toFixed(2)}`;
                        },
                    },
                },
            },
            scales: {
                x: { ...commonOptions.scales.x },
                y: { 
                    ...commonOptions.scales.y, 
                    stacked: true,
                    title: {
                        display: true,
                        text: 'Component Cost',
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
    const tlsScores = [];
    const tcpScores = [];
    const protocolValues = [];
    const protocolColors = [];
    const protocolBorders = [];
    const decisionComponents = [];
    const outcomes = [];
    const outcomeColors = [];
    const outcomeBorders = [];

    let switchCount = 0;
    let prevProto = null;
    let totalRtt = 0;

    logs.forEach((log) => {
        const isTLS = log.protocol === 'TLS';
        const isSuccess = log.status === 'ok';

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

        // Outcome
        outcomes.push(isSuccess ? 1 : 0);
        if (!isSuccess) {
            outcomeColors.push('rgba(239, 68, 68, 0.6)');
            outcomeBorders.push('rgba(239, 68, 68, 0.9)');
        } else {
            outcomeColors.push(isTLS ? 'rgba(99, 102, 241, 0.4)' : 'rgba(6, 182, 212, 0.4)');
            outcomeBorders.push(isTLS ? 'rgba(99, 102, 241, 0.8)' : 'rgba(6, 182, 212, 0.8)');
        }

        // Scores
        tlsScores.push(log.tls_score);
        tcpScores.push(log.tcp_score);

        // Count switches
        if (prevProto && log.protocol !== prevProto) switchCount++;
        prevProto = log.protocol;

        totalRtt += log.rtt_ms;
        
        // Decision components for breakdown chart — use logged components if available
        let comp = log.tls_components || log.tcp_components || {};
        let raw = comp.raw_metrics || {};
        let latencyCost = comp.latency_cost || (log.rtt_ms * 0.4);
        let handshakeCost = comp.handshake_cost || (log.handshake_time_ms * 0.3);
        let payloadCost = comp.payload_cost || (log.payload_size / 1000.0 * 0.1);
        let securityCost = comp.security_cost || (log.protocol === 'TLS' ? 0.1 : 0.3);
        let reliabilityCost = comp.reliability_cost || ((raw.error_rate || 0) * 100);
        
        decisionComponents.push({
            latency: latencyCost,
            handshake: handshakeCost,
            payload: payloadCost,
            security: securityCost,
            reliability: reliabilityCost
        });
    });

    const lastLog = logs[logs.length - 1];

    // ── Update Stats Cards ──
    document.getElementById('total-requests').textContent = logs.length;
    document.getElementById('current-protocol').textContent = lastLog.protocol;
    document.getElementById('avg-rtt').textContent = `${(totalRtt / logs.length).toFixed(1)}ms`;
    document.getElementById('protocol-switches').textContent = switchCount;
    
    // Update security and reliability scores from components if available
    let securityScore = lastLog.protocol === 'TLS' ? 0.100 : 0.300;
    let reliabilityScore = 1.000;
    
    if (lastLog.tls_components && lastLog.tls_components.raw_metrics) {
        reliabilityScore = 1 - lastLog.tls_components.raw_metrics.error_rate;
    } else if (lastLog.tcp_components && lastLog.tcp_components.raw_metrics) {
        reliabilityScore = 1 - lastLog.tcp_components.raw_metrics.error_rate;
    }
    
    document.getElementById('security-score').textContent = securityScore.toFixed(3);
    document.getElementById('reliability-score').textContent = reliabilityScore.toFixed(3);

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
    // Protocol Timeline - create single dataset with protocol data
    const timelineData = logs.map((log, i) => ({
        x: i + 1,
        y: 1,
        protocol: log.protocol
    }));
    
    timelineChart.data.labels = logs.map((_, i) => `#${i + 1}`);
    timelineChart.data.datasets[0].data = timelineData;
    timelineChart.data.datasets[0].backgroundColor = timelineData.map(d => 
        d.protocol === 'TLS' ? 'rgba(99, 102, 241, 0.3)' : 'rgba(6, 182, 212, 0.3)'
    );
    timelineChart.data.datasets[0].borderColor = timelineData.map(d => 
        d.protocol === 'TLS' ? 'rgba(99, 102, 241, 0.8)' : 'rgba(6, 182, 212, 0.8)'
    );
    timelineChart.update('none');

    // RTT
    rttChart.data.labels = labels;
    rttChart.data.datasets[0].data = tlsRtts;
    rttChart.data.datasets[1].data = tcpRtts;
    rttChart.update('none');

    // Outcome
    outcomeChart.data.labels = labels;
    outcomeChart.data.datasets[0].data = outcomes;
    outcomeChart.data.datasets[0].backgroundColor = outcomeColors;
    outcomeChart.data.datasets[0].borderColor = outcomeBorders;
    outcomeChart.update('none');

    // Scores
    scoresChart.data.labels = labels;
    scoresChart.data.datasets[0].data = tlsScores;
    scoresChart.data.datasets[1].data = tcpScores;
    scoresChart.update('none');
    
    // Decision Component Breakdown - stacked bar chart
    decisionBreakdownChart.data.labels = labels;
    decisionBreakdownChart.data.datasets[0].data = decisionComponents.map(c => c.latency);
    decisionBreakdownChart.data.datasets[1].data = decisionComponents.map(c => c.handshake);
    decisionBreakdownChart.data.datasets[2].data = decisionComponents.map(c => c.payload);
    decisionBreakdownChart.data.datasets[3].data = decisionComponents.map(c => c.security);
    decisionBreakdownChart.data.datasets[4].data = decisionComponents.map(c => c.reliability);
    decisionBreakdownChart.update('none');

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
        
        // Determine request type
        const requestType = log.request_type || (log.request_id <= 50 ? 'AUTO' : 'MANUAL');
        const typeClass = requestType === 'AUTO' ? 'type-auto' : 'type-manual';
        const typeIcon = requestType === 'AUTO' ? '🤖' : '👤';

        return `<tr>
            <td>${log.request_id}</td>
            <td>${time}</td>
            <td><span class="type-badge ${typeClass}">${typeIcon} ${requestType}</span></td>
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

    // Update dashboard during normal polling
    if (logs.length !== previousDataLength) {
        updateDashboard(logs);
        previousDataLength = logs.length;
        
        // Check for completion if auto-run is active
        if (isAutoRunning && logs.length > 0) {
            const lastLog = logs[logs.length - 1];
            // Check if we've reached 30 requests in the current session
            if (lastLog.request_id >= 30 && !hasShownCompletionNotification) {
                showNotification('30 requests completed!', 'success');
                hasShownCompletionNotification = true;
                isAutoRunning = false;
            }
        }
    }
    } catch (err) {
        // Silently handle errors (server might not be running yet)
        console.debug('Fetch error:', err.message);
    }
}

// ── Initialize Dashboard ──
document.addEventListener('DOMContentLoaded', () => {
    initCharts();
    
    // Start polling
    fetchLogs();
    setInterval(fetchLogs, POLL_INTERVAL);
    
    // Setup control buttons after DOM is ready
    setTimeout(() => {
        setupControls();
    }, 100);
});

// ── Control Panel Functions ──
let autoRunInterval = null;
let isAutoRunning = false;

function setupControls() {
    // Auto-run 30 requests button
    document.getElementById('run-auto-30').addEventListener('click', async () => {
        if (isAutoRunning) {
            showNotification('Auto-run already in progress', 'warning');
            return;
        }
        
        showNotification('Starting 30 automatic requests...', 'info');
        isAutoRunning = true;
        
        try {
            const response = await fetch('/api/run-auto', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ count: 30 })
            });
            
            if (response.ok) {
                showNotification('30 auto requests started!', 'success');
                // Start monitoring for completion
                hasShownCompletionNotification = false;
            } else {
                isAutoRunning = false;
                showNotification('Failed to start auto requests', 'error');
            }
        } catch (error) {
            isAutoRunning = false;
            showNotification('Failed to start auto requests', 'error');
        }
    });
    
    // Stop auto button
    document.getElementById('stop-auto').addEventListener('click', async () => {
        try {
            // First stop the backend auto-run
            const response = await fetch('/api/stop-auto', { method: 'POST' });
            if (response.ok) {
                // Then stop the frontend polling
                isAutoRunning = false;
                if (autoRunInterval) {
                    clearInterval(autoRunInterval);
                    autoRunInterval = null;
                }
                showNotification('Auto-run stopped', 'success');
            } else {
                showNotification('Failed to stop auto-run', 'error');
            }
        } catch (error) {
            showNotification('Failed to stop auto-run', 'error');
        }
    });
    
    // TLS Delay Button
    document.getElementById('apply-tls-delay').addEventListener('click', async () => {
        const delay = document.getElementById('tls-delay').value;
        try {
            const response = await fetch('/api/set-delay', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ protocol: 'tls', delay: parseFloat(delay) })
            });
            if (response.ok) {
                showNotification(`TLS delay set to ${delay}ms`, 'success');
            }
        } catch (error) {
            showNotification('Failed to set TLS delay', 'error');
        }
    });
    
    // TCP Delay Button
    document.getElementById('apply-tcp-delay').addEventListener('click', async () => {
        const delay = document.getElementById('tcp-delay').value;
        try {
            const response = await fetch('/api/set-delay', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ protocol: 'tcp', delay: parseFloat(delay) })
            });
            if (response.ok) {
                showNotification(`TCP delay set to ${delay}ms`, 'success');
            }
        } catch (error) {
            showNotification('Failed to set TCP delay', 'error');
        }
    });
    
    // Error Rate Button
    document.getElementById('apply-error-rate').addEventListener('click', async () => {
        const errorRate = document.getElementById('error-rate').value;
        try {
            const response = await fetch('/api/set-error-rate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ error_rate: parseFloat(errorRate) / 100 })
            });
            if (response.ok) {
                showNotification(`Error rate set to ${errorRate}%`, 'success');
            }
        } catch (error) {
            showNotification('Failed to set error rate', 'error');
        }
    });
    
    // Reset Delays Button
    document.getElementById('reset-delays').addEventListener('click', async () => {
        try {
            const response = await fetch('/api/reset-delays', { method: 'POST' });
            if (response.ok) {
                document.getElementById('tls-delay').value = 0;
                document.getElementById('tcp-delay').value = 0;
                document.getElementById('error-rate').value = 0;
                showNotification('Delays reset to default', 'success');
            }
        } catch (error) {
            showNotification('Failed to reset delays', 'error');
        }
    });
    
    // Probe Network Button
    document.getElementById('probe-network').addEventListener('click', async () => {
        try {
            const response = await fetch('/api/probe-network', { method: 'POST' });
            const result = await response.json();
            
            if (response.ok && result.success) {
                // Display network configuration
                displayNetworkConfig(result.data);
                showNotification('Network probed successfully', 'success');
            } else {
                showNotification(result.error || 'Failed to probe network', 'error');
            }
        } catch (error) {
            console.error('Probe error:', error);
            showNotification('Error probing network: ' + error.message, 'error');
        }
    });
    
    // Clear Logs Button
    document.getElementById('clear-logs').addEventListener('click', async () => {
        if (confirm('Are you sure you want to clear all logs? This cannot be undone.')) {
            try {
                const response = await fetch('/api/clear-logs', { method: 'POST' });
                if (response.ok) {
                    // Reset dashboard state
                    previousDataLength = 0;
                    hasShownCompletionNotification = false;
                    lastRequestId = 0;
                    // Clear all charts
                    if (timelineChart) {
                        timelineChart.data.labels = [];
                        timelineChart.data.datasets[0].data = [];
                        timelineChart.update();
                    }
                    if (rttChart) {
                        rttChart.data.labels = [];
                        rttChart.data.datasets[0].data = [];
                        rttChart.data.datasets[1].data = [];
                        rttChart.update();
                    }
                    if (outcomeChart) {
                        outcomeChart.data.labels = [];
                        outcomeChart.data.datasets[0].data = [];
                        outcomeChart.update();
                    }
                    if (scoresChart) {
                        scoresChart.data.labels = [];
                        scoresChart.data.datasets[0].data = [];
                        scoresChart.data.datasets[1].data = [];
                        scoresChart.update();
                    }
                    if (decisionBreakdownChart) {
                        decisionBreakdownChart.data.labels = [];
                        decisionBreakdownChart.data.datasets.forEach(ds => { ds.data = []; });
                        decisionBreakdownChart.update();
                    }
                    
                    // Reset stats cards
                    document.getElementById('total-requests').textContent = '0';
                    document.getElementById('current-protocol').textContent = '-';
                    document.getElementById('avg-rtt').textContent = '0ms';
                    document.getElementById('protocol-switches').textContent = '0';
                    document.getElementById('security-score').textContent = '0.000';
                    document.getElementById('reliability-score').textContent = '0.000';
                    
                    // Clear log table
                    document.getElementById('log-tbody').innerHTML = '';
                    
                    showNotification('All logs cleared successfully', 'success');
                } else {
                    showNotification('Failed to clear logs', 'error');
                }
            } catch (error) {
                showNotification('Failed to clear logs', 'error');
            }
        }
    });
}

function monitorProtocolSwitches() {
    // This function can be used for additional monitoring if needed
    // Completion monitoring is now handled in fetchLogs()
}

// ── Notification System ──
let activeNotifications = [];
const MAX_NOTIFICATIONS = 5;
const NOTIFICATION_SPACING = 80; // pixels between notifications

function showNotification(message, type = 'info') {
    // Remove old notifications if too many
    if (activeNotifications.length >= MAX_NOTIFICATIONS) {
        const oldest = activeNotifications.shift();
        removeNotification(oldest);
    }
    
    // Create notification element
    const notification = document.createElement('div');
    notification.className = `notification notification-${type}`;
    notification.textContent = message;
    
    // Calculate position based on existing notifications
    const notificationIndex = activeNotifications.length;
    const topPosition = 20 + (notificationIndex * NOTIFICATION_SPACING);
    
    // Style the notification
    Object.assign(notification.style, {
        position: 'fixed',
        top: `${topPosition}px`,
        right: '20px',
        padding: '1rem 1.5rem',
        borderRadius: '8px',
        color: 'white',
        fontFamily: 'Inter, sans-serif',
        fontSize: '0.875rem',
        fontWeight: '500',
        zIndex: '1000',
        opacity: '0',
        transform: 'translateX(100%)',
        transition: 'all 0.3s ease',
        minWidth: '300px',
        maxWidth: '400px',
        boxShadow: '0 4px 12px rgba(0, 0, 0, 0.3)'
    });
    
    // Set background color based on type
    const colors = {
        success: '#10b981',
        error: '#ef4444',
        info: '#6366f1',
        warning: '#f59e0b'
    };
    notification.style.background = colors[type] || colors.info;
    
    // Add to page
    document.body.appendChild(notification);
    activeNotifications.push(notification);
    
    // Animate in
    setTimeout(() => {
        notification.style.opacity = '1';
        notification.style.transform = 'translateX(0)';
    }, 100);
    
    // Remove after 4 seconds
    setTimeout(() => {
        removeNotification(notification);
    }, 4000);
}

function displayNetworkConfig(data) {
    // Update the configuration display
    document.getElementById('tls-rtt').textContent = `${data.tls_rtt?.toFixed(2) || '—'} ms`;
    document.getElementById('tcp-rtt').textContent = `${data.tcp_rtt?.toFixed(2) || '—'} ms`;
    document.getElementById('tls-handshake').textContent = `${data.tls_handshake?.toFixed(2) || '—'} ms`;
    document.getElementById('tcp-handshake').textContent = `${data.tcp_handshake?.toFixed(2) || '—'} ms`;
    document.getElementById('tls-score').textContent = (data.tls_score?.toFixed(2) || '—');
    document.getElementById('tcp-score').textContent = (data.tcp_score?.toFixed(2) || '—');
    
    // Show the configuration section
    const configSection = document.getElementById('network-config');
    configSection.style.display = 'block';
    
    // Hide after 10 seconds
    setTimeout(() => {
        configSection.style.display = 'none';
    }, 10000);
}

function removeNotification(notification) {
    const index = activeNotifications.indexOf(notification);
    if (index > -1) {
        activeNotifications.splice(index, 1);
    }
    
    // Animate out
    notification.style.opacity = '0';
    notification.style.transform = 'translateX(100%)';
    
    // Remove from DOM
    setTimeout(() => {
        if (notification.parentNode) {
            notification.parentNode.removeChild(notification);
        }
    }, 300);
    
    // Reposition remaining notifications
    repositionNotifications();
}

function repositionNotifications() {
    activeNotifications.forEach((notification, index) => {
        const newTopPosition = 20 + (index * NOTIFICATION_SPACING);
        notification.style.top = `${newTopPosition}px`;
    });
}
