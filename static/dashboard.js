// Read configuration from HTML data attributes
const gpuSupported = document.body.dataset.gpuSupported === 'true';
const gridColor = document.body.dataset.gridColor;
const textColor = document.body.dataset.textColor;
const cpuColor = document.body.dataset.cpuColor;
const ramColor = document.body.dataset.ramColor;
const gpuColor = document.body.dataset.gpuColor;
const diskColor = document.body.dataset.diskColor;
const powerColor = document.body.dataset.powerColor;
const netUpColor = document.body.dataset.netUpColor;
const netDownColor = document.body.dataset.netDownColor;

// Custom HTML Tooltip Implementation for Blur and Rounded Corners
const externalTooltipHandler = (context) => {
    const {chart, tooltip} = context;
    const container = chart.canvas.closest('.relative') || chart.canvas.parentNode;
    let tooltipEl = container.querySelector('div.chart-custom-tooltip');

    if (!tooltipEl) {
        tooltipEl = document.createElement('div');
        tooltipEl.classList.add('chart-custom-tooltip');
        // Smooth gliding transition between data points
        tooltipEl.style.transition = 'opacity 0.15s ease, left 0.3s cubic-bezier(0.2, 1, 0.2, 1), top 0.3s cubic-bezier(0.2, 1, 0.2, 1)';
        container.appendChild(tooltipEl);
    }

    if (tooltip.opacity === 0) {
        tooltipEl.style.opacity = 0;
        return;
    }

    if (tooltip.body) {
        const titleLines = tooltip.title || [];
        const bodyLines = tooltip.body.map(b => b.lines);
        let innerHtml = '';

        titleLines.forEach(title => {
            innerHtml += `<div class="text-[10px] text-gray-400 font-bold mb-1 uppercase tracking-tight">${title}</div>`;
        });

        bodyLines.forEach((body, i) => {
            const colors = tooltip.labelColors[i];
            const style = `color: ${colors.borderColor || 'inherit'}`;
            innerHtml += `<div class="text-[11px] font-mono flex items-center gap-2 whitespace-nowrap" style="${style}">${body}</div>`;
        });

        tooltipEl.innerHTML = innerHtml;
    }

    const {offsetLeft: positionX, offsetTop: positionY} = chart.canvas;
    tooltipEl.style.opacity = 1;
    // Position at caret with vertical offset
    tooltipEl.style.left = (positionX + tooltip.caretX) + 'px';
    tooltipEl.style.top = (positionY + tooltip.caretY - 10) + 'px';
};

// Smart Icon Mapper based on process keywords
function getAppIcon(name) {
    const n = name.toLowerCase();
    const icons = {
        browser: '<svg class="w-3 h-3 text-blue-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 12a9 9 0 01-9 9m9-9a9 9 0 00-9-9m9 9H3m9 9a9 9 0 01-9-9m9 9c1.657 0 3-4.03 3-9s-1.343-9-3-9m0 18c-1.657 0-3-4.03-3-9s1.343-9 3-9m-9 9a9 9 0 019-9" /></svg>',
        code: '<svg class="w-3 h-3 text-purple-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4" /></svg>',
        python: '<svg class="w-3 h-3 text-yellow-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.642.257a2 2 0 01-1.589 0l-.642-.257a6 6 0 00-3.86-.517l-2.387.477a2 2 0 00-1.022.547l-.34.34a2 2 0 000 2.828l1.245 1.245a2 2 0 002.828 0l.34-.34a2 2 0 00.547-1.022l.477-2.387a6 6 0 00-.517-3.86l-.257-.642a2 2 0 010-1.589l.257-.642a6 6 0 00.517-3.86l-.477-2.387a2 2 0 00-.547-1.022l-.34-.34a2 2 0 00-2.828 0l-1.245 1.245a2 2 0 000 2.828l.34.34z" /></svg>',
        terminal: '<svg class="w-3 h-3 text-green-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 9l3 3-3 3m5 0h3M5 20h14a2 2 0 002-2V6a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" /></svg>',
        system: '<svg class="w-3 h-3 text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6V4m0 2a2 2 0 100 4m0-4a2 2 0 110 4m-6 8a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4m6 6v10m6-2a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4" /></svg>',
        generic: '<svg class="w-3 h-3 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2m2 6h-2M7 19h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 00-2 2v10a2 2 0 002 2zM9 9h6v6H9V9z" /></svg>'
    };

    if (n.includes('chrome') || n.includes('firefox') || n.includes('edge') || n.includes('safari') || n.includes('browser')) return icons.browser;
    if (n.includes('code') || n.includes('visual') || n.includes('studio') || n.includes('sublime')) return icons.code;
    if (n.includes('python') || n.includes('conda')) return icons.python;
    if (n.includes('cmd') || n.includes('powershell') || n.includes('bash') || n.includes('term') || n.includes('conhost')) return icons.terminal;
    if (n.includes('system') || n.includes('svchost') || n.includes('kernel') || n.includes('service') || n.includes('wininit')) return icons.system;
    
    return icons.generic;
}

function formatBytes(size) {
    const units = ['B', 'KB', 'MB', 'GB', 'TB'];
    for (let i = 0; i < units.length; i++) {
        if (size < 1024) return size.toFixed(1) + ' ' + units[i];
        size /= 1024;
    }
    return size.toFixed(1) + ' PB';
}

function createSparkline(elementId, color, max = 100, unit = '%') {
    const canvas = document.getElementById(elementId);
    if (!canvas) return null;
    return new Chart(canvas.getContext('2d'), {
        type: 'line',
        data: {
            labels: Array(60).fill(''),
            datasets: [{
                data: Array(60).fill(0),
                borderColor: color,
                backgroundColor: (context) => {
                    const chart = context.chart;
                    const {ctx, chartArea} = chart;
                    if (!chartArea) return null;
                    // Create a vertical gradient from the top of the chart area to the bottom
                    const gradient = ctx.createLinearGradient(0, chartArea.top, 0, chartArea.bottom);
                    gradient.addColorStop(0, color + '60'); // Vibrant peak
                    gradient.addColorStop(1, color + '00'); // Fade to transparent
                    return gradient;
                },
                borderWidth: 1.5,
                fill: true,
                tension: 0.4,
                pointRadius: 0,
                clip: 2
            }]
        },
        options: {
            maintainAspectRatio: false,
            plugins: { 
                legend: { display: false }, 
                tooltip: { 
                    enabled: false,
                    external: externalTooltipHandler,
                    mode: 'index',
                    intersect: false,
                    callbacks: { 
                        label: (ctx) => {
                            const val = ctx.parsed.y;
                            return `Value: ${unit === 'W' ? val.toFixed(1) + ' W' : val.toFixed(1) + unit}`;
                        }
                    }
                } 
            },
            scales: { 
                x: { display: false }, 
                y: { display: false, min: 0, max: max === 'auto' ? undefined : max } 
            },
            animation: { duration: 0 }
        }
    });
}

function createDualSparkline(elementId, color1, color2, unit = 'bytes') {
    const canvas = document.getElementById(elementId);
    if (!canvas) return null;
    return new Chart(canvas.getContext('2d'), {
        type: 'line',
        data: {
            labels: Array(60).fill(''),
            datasets: [
                {
                    label: 'Download',
                    data: Array(60).fill(0),
                    borderColor: color1,
                    backgroundColor: (context) => {
                        const chart = context.chart;
                        const {ctx, chartArea} = chart;
                        if (!chartArea) return null;
                        const gradient = ctx.createLinearGradient(0, chartArea.top, 0, chartArea.bottom);
                        gradient.addColorStop(0, color1 + '60');
                        gradient.addColorStop(1, color1 + '00');
                        return gradient;
                    },
                    borderWidth: 1.5, fill: true, tension: 0.4, pointRadius: 0, clip: 2
                },
                {
                    label: 'Upload',
                    data: Array(60).fill(0),
                    borderColor: color2,
                    backgroundColor: (context) => {
                        const chart = context.chart;
                        const {ctx, chartArea} = chart;
                        if (!chartArea) return null;
                        const gradient = ctx.createLinearGradient(0, chartArea.top, 0, chartArea.bottom);
                        gradient.addColorStop(0, color2 + '40');
                        gradient.addColorStop(1, color2 + '00');
                        return gradient;
                    },
                    borderWidth: 1.5, fill: true, tension: 0.4, pointRadius: 0, clip: 2
                }
            ]
        },
        options: {
            maintainAspectRatio: false,
            plugins: { 
                legend: { display: false }, 
                tooltip: { 
                    enabled: false,
                    external: externalTooltipHandler,
                    mode: 'index',
                    intersect: false,
                    callbacks: { 
                        label: (ctx) => 
                            `${ctx.dataset.label}: ${unit === 'bytes' ? formatBytes(ctx.parsed.y) + '/s' : ctx.parsed.y.toFixed(1)}`
                    }
                } 
            },
            scales: { x: { display: false }, y: { display: false } },
            animation: { duration: 0 }
        }
    });
}

const cpuSpark = createSparkline('cpuSparkline', cpuColor);
const ramSpark = createSparkline('ramSparkline', ramColor);
const gpuSpark = createSparkline('gpuSparkline', gpuColor);
const diskSpark = createSparkline('diskSparkline', diskColor);
const powerSpark = createSparkline('powerSparkline', powerColor, 'auto', 'W');
const netSpark = createDualSparkline('netSparkline', netDownColor, netUpColor, 'bytes');

function updateSpark(chart, value) {
    if (!chart) return;
    const now = new Date().toLocaleTimeString([], { hour12: false });
    chart.data.labels.push(now);
    chart.data.labels.shift();
    chart.data.datasets[0].data.push(value);
    chart.data.datasets[0].data.shift();
    chart.update();
}

function updateDualSpark(chart, val1, val2) {
    if (!chart) return;
    const now = new Date().toLocaleTimeString([], { hour12: false });
    chart.data.labels.push(now);
    chart.data.labels.shift();
    chart.data.datasets[0].data.push(val1);
    chart.data.datasets[0].data.shift();
    chart.data.datasets[1].data.push(val2);
    chart.data.datasets[1].data.shift();
    chart.update();
}

window.switchTab = function(tab) {
    const wrapper = document.getElementById('tab-wrapper');
    const indicator = document.getElementById('tab-indicator');
    const procBtn = document.getElementById('btn-processes');
    const sysBtn = document.getElementById('btn-system');

    if (tab === 'processes') {
        wrapper.style.transform = 'translateX(0%)';
        indicator.style.left = '0%';
        procBtn.classList.add('text-green-400');
        procBtn.classList.remove('text-gray-400');
        sysBtn.classList.add('text-gray-400');
        sysBtn.classList.remove('text-green-400');
    } else {
        wrapper.style.transform = 'translateX(-50%)';
        indicator.style.left = '50%';
        sysBtn.classList.add('text-green-400');
        sysBtn.classList.remove('text-gray-400');
        procBtn.classList.add('text-gray-400');
        procBtn.classList.remove('text-green-400');
    }
}

window.handleToggleMaximize = async function() {
    const isMaximized = await window.pywebview.api.toggle_maximize();
    const btn = document.getElementById('maximize-btn');
    if (isMaximized) {
        btn.title = "Restore";
        btn.innerHTML = `<svg class="w-3.5 h-3.5 text-gray-500 group-hover:text-gray-200" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M7 3h14v14M3 7h14v14H3z" /></svg>`;
    } else {
        btn.title = "Maximize";
        btn.innerHTML = `<svg class="w-3.5 h-3.5 text-gray-500 group-hover:text-gray-200" fill="none" stroke="currentColor" viewBox="0 0 24 24"><rect x="3" y="3" width="18" height="18" rx="2" stroke-width="2.5" stroke="currentColor" fill="none" /></svg>`;
    }
}

const socket = io();

socket.on('connect', () => {
    // Update Live Indicator
    document.getElementById('status-text').innerText = 'Live';
    document.getElementById('status-text').classList.replace('text-red-500', 'text-gray-400');
    document.getElementById('status-ping').classList.replace('bg-red-400', 'bg-green-400');
    document.getElementById('status-dot').classList.replace('bg-red-500', 'bg-green-500');
});

socket.on('disconnect', () => {
    // Update Live Indicator
    document.getElementById('status-text').innerText = 'Offline';
    document.getElementById('status-text').classList.replace('text-gray-400', 'text-red-500');
    document.getElementById('status-ping').classList.replace('bg-green-400', 'bg-red-400');
    document.getElementById('status-dot').classList.replace('bg-green-500', 'bg-red-500');
});

setInterval(() => {
    socket.emit('ping_server', { startTime: performance.now() });
}, 2000);

socket.on('pong_client', (data) => {
    const ping = Math.round(performance.now() - data.startTime);
    const latencyElem = document.getElementById('latency');
    latencyElem.innerText = ping + 'ms';
    
    if (ping < 100) latencyElem.className = "font-mono text-green-400";
    else if (ping < 300) latencyElem.className = "font-mono text-yellow-400";
    else latencyElem.className = "font-mono text-red-400";
});

socket.on('stats_response', (data) => {
    const loader = document.getElementById('loading-overlay');
    if (loader) {
        loader.style.opacity = '0';
        setTimeout(() => {
            loader.remove();
            document.body.style.overflow = 'auto';
        }, 500);
    }

    document.getElementById('cpu-usage').innerText = data.cpu + '%';
    const tempText = data.temp || '--°C';
    const freqText = data.cpu_freq ? ` • ${data.cpu_freq} GHz` : '';
    document.getElementById('cpu-sub').innerText = tempText + freqText;
    document.getElementById('ram-usage').innerText = data.ram + '%';
    document.getElementById('disk-usage').innerText = data.disk + '%';
    document.getElementById('disk-details').innerText = `${data.disk_free} / ${data.disk_total}`;
    document.getElementById('net-up').innerText = data.net_up;
    document.getElementById('net-down').innerText = data.net_down;
    document.getElementById('ram-details').innerText = `${data.ram_used} / ${data.ram_total}`;

    if (data.power) {
        document.getElementById('power-watts').innerText = data.power.watts_str;
        let subParts = [data.power.voltage_str, data.power.amps_str];
        
        if (data.power.fan_str) subParts.push(data.power.fan_str);
        if (data.power.gpu_temp_str) subParts.push(data.power.gpu_temp_str);
        
        document.getElementById('power-sub').innerText = subParts.join(' • ');
        updateSpark(powerSpark, data.power.watts);
    }

    if (data.storage_list) {
        const listContainer = document.getElementById('storage-list-container');
        if (listContainer) {
            listContainer.innerHTML = data.storage_list.map(drive => {
                const healthBadge = drive.health !== null ? 
                    `<span class="px-1 rounded-[3px] text-[9px] font-bold border ${drive.health < 30 ? 'bg-red-500/10 text-red-400 border-red-500/30' : drive.health < 80 ? 'bg-yellow-500/10 text-yellow-400 border-yellow-500/30' : 'bg-green-500/10 text-green-400 border-green-500/30'}">${Math.round(drive.health)}% LIFE</span>` : '';
                
                const throughput = [];
                if (drive.read) throughput.push(`<span class="text-gray-500">R: <span class="text-blue-400/80">${drive.read}/s</span></span>`);
                if (drive.write) throughput.push(`<span class="text-gray-500">W: <span class="text-purple-400/80">${drive.write}/s</span></span>`);
                if (drive.tbw) throughput.push(`<span class="text-gray-500">TBW: <span class="text-gray-400">${drive.tbw}</span></span>`);

                const capStr = drive.total_gb ? ` - ${drive.free_str} / ${drive.total_str}` : '';

                return `
                    <div class="flex flex-col border-l border-gray-600 pl-2">
                        <div class="flex justify-between items-center text-[11px] text-gray-400">
                            <span class="truncate font-bold max-w-[180px]">${drive.name}${capStr}</span>
                            <div class="flex gap-2 items-center shrink-0">
                                ${healthBadge}
                                ${drive.temp ? `<span class="text-orange-400">${drive.temp}°C</span>` : ''}
                            </div>
                        </div>
                        ${throughput.length > 0 ? `<div class="flex gap-3 text-[10px] font-mono mt-0.5">${throughput.join('')}</div>` : ''}
                    </div>
                `;
            }).join('');
        }
        const totalMain = document.getElementById('storage-total-main');
        if (totalMain) totalMain.innerText = `${data.storage_free} / ${data.storage_total}`;
    }

    updateSpark(cpuSpark, data.cpu);
    updateSpark(ramSpark, data.ram);
    updateSpark(diskSpark, data.disk);
    updateDualSpark(netSpark, data.net_down_raw, data.net_up_raw);

    document.getElementById('system-uptime').innerText = data.system_uptime;
    document.getElementById('app-uptime').innerText = data.app_uptime;
    
    const gpuUsageElem = document.getElementById('gpu-usage');
    if (gpuUsageElem) gpuUsageElem.innerText = data.gpu_load || 'N/A';

    const extPingElem = document.getElementById('internet-ping');
    if (data.internet_ping) {
        extPingElem.innerText = data.internet_ping.display;
        extPingElem.className = "font-mono " + data.internet_ping.color;
    }

    const procCountBadge = document.getElementById('process-count-badge');
    if (procCountBadge) procCountBadge.innerText = data.processes.count;

    const processTable = document.getElementById('process-table');
    processTable.innerHTML = data.processes.list.map(p => `
        <tr class="border-b border-gray-700/50 last:border-0 hover:bg-gray-700 transition-colors">
            <td class="px-4 py-1 flex items-center gap-2 min-w-[160px]">
                <div class="shrink-0 w-4 h-4 flex items-center justify-center">${getAppIcon(p.name)}</div>
                <span class="truncate max-w-[120px] font-bold text-gray-200">${p.name}</span>
                <span class="text-[9px] text-gray-500 font-mono">(${p.count})</span>
            </td>
            <td class="px-4 py-1 text-right text-orange-400 font-mono">${p.cpu.toFixed(1)}%</td>
            <td class="px-4 py-1 text-right text-blue-400 font-mono">${p.memory_str}</td>
            <td class="px-4 py-1 text-right text-green-400 font-mono">${p.disk_str}</td>
        </tr>
    `).join('');

    const gpuCardUsage = document.getElementById('gpu-card-usage');
    if (gpuCardUsage) gpuCardUsage.innerText = data.gpu_load || 'N/A';
    updateSpark(gpuSpark, data.gpu_load_raw ?? 0);
});