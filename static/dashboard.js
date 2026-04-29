// Read configuration from HTML data attributes
const gpuSupported = document.body.dataset.gpuSupported === 'true';

const ctx = document.getElementById('cpuChart').getContext('2d');

const datasets = [
    {
        label: 'CPU %',
        data: Array(60).fill(0),
        borderColor: '#4ade80',
        backgroundColor: 'rgba(74, 222, 128, 0.1)',
        fill: true,
        tension: 0.2,
        cubicInterpolationMode: 'monotone',
        pointRadius: 0,
        clip: false,
        yAxisID: 'y'
    },
    {
        label: 'RAM %',
        data: Array(60).fill(0),
        borderColor: '#3b82f6',
        backgroundColor: 'rgba(59, 130, 246, 0.1)',
        fill: true,
        tension: 0.2,
        cubicInterpolationMode: 'monotone',
        pointRadius: 0,
        clip: false,
        yAxisID: 'y'
    }
];

const yAxes = {
    y: { 
        min: 0, 
        max: 100, 
        grid: { color: '#374151' },
        ticks: { color: '#9ca3af' },
        title: { display: true, text: 'CPU/RAM %', color: '#9ca3af', font: { size: 10 } }
    }
};

if (gpuSupported) {
    datasets.push({
        label: 'GPU %',
        data: Array(60).fill(0),
        borderColor: '#f97316',
        backgroundColor: 'rgba(249, 115, 22, 0.1)',
        fill: true,
        tension: 0.2,
        cubicInterpolationMode: 'monotone',
        pointRadius: 0,
        clip: false,
        yAxisID: 'y1'
    });
    yAxes.y1 = {
        min: 0,
        max: 100,
        position: 'right',
        grid: { drawOnChartArea: false },
        ticks: { color: '#f97316' },
        title: { display: true, text: 'GPU %', color: '#f97316', font: { size: 10 } }
    };
}

const cpuChart = new Chart(ctx, {
    type: 'line',
    data: { labels: Array(60).fill(''), datasets: datasets },
    options: {
        responsive: true,
        maintainAspectRatio: false,
        layout: {
            padding: { left: 10, right: 0, top: 10, bottom: 0 }
        },
        scales: { ...yAxes, x: { display: false } },
        plugins: {
            legend: { 
                display: true,
                labels: {
                    color: '#9ca3af',
                    boxWidth: 12,
                    font: { size: 10 }
                }
            }
        },
        animation: {
            duration: 0,
            easing: 'linear'
        }
    }
});

function createSparkline(elementId, color, max = 100) {
    const canvas = document.getElementById(elementId);
    if (!canvas) return null;
    return new Chart(canvas.getContext('2d'), {
        type: 'line',
        data: {
            labels: Array(60).fill(''),
            datasets: [{
                data: Array(60).fill(0),
                borderColor: color,
                borderWidth: 1.5,
                fill: false,
                tension: 0.4,
                pointRadius: 0,
                clip: 2
            }]
        },
        options: {
            maintainAspectRatio: false,
            plugins: { legend: { display: false }, tooltip: { enabled: false } },
            scales: { 
                x: { display: false }, 
                y: { display: false, min: 0, max: max === 'auto' ? undefined : max } 
            },
            animation: { duration: 0 }
        }
    });
}

const cpuSpark = createSparkline('cpuSparkline', '#f97316'); // Orange
const ramSpark = createSparkline('ramSparkline', '#3b82f6'); // Blue
const diskSpark = createSparkline('diskSparkline', '#22c55e'); // Green
const powerSpark = createSparkline('powerSparkline', '#eab308', 'auto'); // Yellow
const netDownSpark = createSparkline('netDownSparkline', '#3b82f6', 'auto');
const netUpSpark = createSparkline('netUpSparkline', '#a855f7', 'auto');

function updateSpark(chart, value) {
    if (!chart) return;
    chart.data.datasets[0].data.push(value);
    chart.data.datasets[0].data.shift();
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
    document.getElementById('cpu-sub').innerText = data.temp + (data.cpu_freq ? ` • ${data.cpu_freq} GHz` : '');
    document.getElementById('ram-usage').innerText = data.ram + '%';
    document.getElementById('disk-usage').innerText = data.disk + '%';
    document.getElementById('disk-details').innerText = data.disk_free + ' GB Free / ' + data.disk_total + ' GB';
    document.getElementById('net-up').innerText = data.net_up;
    document.getElementById('net-down').innerText = data.net_down;
    document.getElementById('ram-details').innerText = data.ram_used + ' GB / ' + data.ram_total + ' GB';

    if (data.power) {
        document.getElementById('power-watts').innerText = data.power.watts + ' W';
        let subParts = [`${data.power.voltage}V`, `${data.power.amps}A` ];
        
        if (data.power.fan_rpm > 0) subParts.push(`${data.power.fan_rpm} RPM`);
        if (data.power.gpu_temp > 0) subParts.push(`GPU: ${data.power.gpu_temp}°C`);
        
        document.getElementById('power-sub').innerText = subParts.join(' • ');
        updateSpark(powerSpark, data.power.watts);
    }

    updateSpark(cpuSpark, data.cpu);
    updateSpark(ramSpark, data.ram);
    updateSpark(diskSpark, data.disk);
    updateSpark(netDownSpark, data.net_down_raw);
    updateSpark(netUpSpark, data.net_up_raw);

    document.getElementById('system-uptime').innerText = data.system_uptime;
    document.getElementById('app-uptime').innerText = data.app_uptime;
    
    const gpuUsageElem = document.getElementById('gpu-usage');
    if (gpuUsageElem) gpuUsageElem.innerText = data.gpu_load !== null ? data.gpu_load + '%' : 'N/A';

    const extPingElem = document.getElementById('internet-ping');
    if (data.internet_ping !== null) {
        extPingElem.innerText = data.internet_ping + 'ms';
        if (data.internet_ping < 100) extPingElem.className = "font-mono text-green-400";
        else if (data.internet_ping < 300) extPingElem.className = "font-mono text-yellow-400";
        else extPingElem.className = "font-mono text-red-400";
    } else {
        extPingElem.innerText = 'Offline';
        extPingElem.className = "font-mono text-red-600";
    }

    const processTable = document.getElementById('process-table');
    processTable.innerHTML = data.processes.map(p => `
        <tr class="border-b border-gray-700/50 last:border-0 hover:bg-gray-700 transition-colors">
            <td class="px-4 py-1.5 text-gray-400">${p.pid}</td>
            <td class="px-4 py-1.5 truncate max-w-[120px]">${p.name}</td>
            <td class="px-4 py-1.5 text-right text-green-400">${p.memory_str}</td>
        </tr>
    `).join('');

    cpuChart.data.datasets[0].data.push(data.cpu);
    cpuChart.data.datasets[0].data.shift();
    cpuChart.data.datasets[1].data.push(data.ram);
    cpuChart.data.datasets[1].data.shift();
    
    if (gpuSupported) {
        const gpuVal = data.gpu_load ?? 0;
        cpuChart.data.datasets[2].data.push(gpuVal);
        cpuChart.data.datasets[2].data.shift();
    }
    
    cpuChart.update();
});