let selectedStates = new Set();
let knownCallIds = new Set();
let isAlertActive = false;
let alertBorder = null;
let alertSound = null;
let faviconBlinkInterval = null;
let filterCollapsed = false;

const faviconRed = 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFBQIAX8jx0gAAAABJRU5ErkJggg==';
const faviconNormal = 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M/wHwAEBgIApD5fRAAAAABJRU5ErkJggg==';

function loadSelectedStates() {
    const saved = localStorage.getItem('selectedStates');
    if (saved) {
        selectedStates = new Set(JSON.parse(saved));
    } else {
        selectedStates = new Set();
    }
}

function toggleStateFilter() {
    const filterContent = document.getElementById('filterContent');
    const collapseIcon = document.getElementById('collapseIcon');
    const collapseBtn = document.getElementById('collapseBtn');
    
    filterCollapsed = !filterCollapsed;
    
    if (filterCollapsed) {
        filterContent.classList.add('collapsed');
        collapseIcon.textContent = '▶';
        collapseBtn.innerHTML = '<span id="collapseIcon">▶</span> Expand';
    } else {
        filterContent.classList.remove('collapsed');
        collapseIcon.textContent = '▼';
        collapseBtn.innerHTML = '<span id="collapseIcon">▼</span> Minimize';
    }
    
    localStorage.setItem('filterCollapsed', filterCollapsed);
}

function loadFilterState() {
    const saved = localStorage.getItem('filterCollapsed');
    if (saved === 'true') {
        filterCollapsed = true;
        const filterContent = document.getElementById('filterContent');
        const collapseIcon = document.getElementById('collapseIcon');
        const collapseBtn = document.getElementById('collapseBtn');
        
        filterContent.classList.add('collapsed');
        collapseIcon.textContent = '▶';
        collapseBtn.innerHTML = '<span id="collapseIcon">▶</span> Expand';
    }
}

function saveSelectedStates() {
    localStorage.setItem('selectedStates', JSON.stringify([...selectedStates]));
}

function selectAllStates() {
    const checkboxes = document.querySelectorAll('.state-checkbox input[type="checkbox"]');
    checkboxes.forEach(cb => {
        cb.checked = true;
        selectedStates.add(cb.value);
    });
    saveSelectedStates();
    updateCallsDisplay();
}

function deselectAllStates() {
    const checkboxes = document.querySelectorAll('.state-checkbox input[type="checkbox"]');
    checkboxes.forEach(cb => {
        cb.checked = false;
        selectedStates.delete(cb.value);
    });
    saveSelectedStates();
    updateCallsDisplay();
}

function handleStateChange(state, checked) {
    if (checked) {
        selectedStates.add(state);
    } else {
        selectedStates.delete(state);
    }
    saveSelectedStates();
    updateCallsDisplay();
}

async function loadStates() {
    try {
        const response = await fetch('/api/states');
        const data = await response.json();
        const stateGrid = document.getElementById('stateGrid');
        
        data.states.forEach(state => {
            const div = document.createElement('div');
            div.className = 'state-checkbox';
            
            const checkbox = document.createElement('input');
            checkbox.type = 'checkbox';
            checkbox.value = state;
            checkbox.id = `state-${state}`;
            checkbox.checked = selectedStates.has(state);
            checkbox.onchange = (e) => handleStateChange(state, e.target.checked);
            
            const label = document.createElement('label');
            label.htmlFor = `state-${state}`;
            label.textContent = state;
            
            div.appendChild(checkbox);
            div.appendChild(label);
            stateGrid.appendChild(div);
        });
    } catch (error) {
        console.error('Error loading states:', error);
    }
}

function playAlertSound() {
    const audioContext = new (window.AudioContext || window.webkitAudioContext)();
    const oscillator = audioContext.createOscillator();
    const gainNode = audioContext.createGain();
    
    oscillator.connect(gainNode);
    gainNode.connect(audioContext.destination);
    
    oscillator.frequency.value = 800;
    oscillator.type = 'sine';
    
    gainNode.gain.setValueAtTime(0, audioContext.currentTime);
    gainNode.gain.linearRampToValueAtTime(0.3, audioContext.currentTime + 0.1);
    gainNode.gain.linearRampToValueAtTime(0.3, audioContext.currentTime + 0.4);
    gainNode.gain.linearRampToValueAtTime(0, audioContext.currentTime + 0.5);
    
    oscillator.start(audioContext.currentTime);
    oscillator.stop(audioContext.currentTime + 0.5);
    
    setTimeout(() => {
        oscillator.disconnect();
        gainNode.disconnect();
    }, 600);
}

function startVisualAlert() {
    if (!alertBorder) {
        alertBorder = document.getElementById('alertBorder');
    }
    
    alertBorder.classList.add('blinking');
    isAlertActive = true;
    
    if (!document.hidden) {
        setTimeout(() => {
            alertBorder.classList.remove('blinking');
            isAlertActive = false;
        }, 5000);
    }
}

function startFaviconBlink() {
    if (faviconBlinkInterval) return;
    
    let isRed = false;
    const favicon = document.querySelector("link[rel*='icon']");
    
    faviconBlinkInterval = setInterval(() => {
        isRed = !isRed;
        favicon.href = isRed ? faviconRed : faviconNormal;
    }, 500);
}

function stopFaviconBlink() {
    if (faviconBlinkInterval) {
        clearInterval(faviconBlinkInterval);
        faviconBlinkInterval = null;
        const favicon = document.querySelector("link[rel*='icon']");
        favicon.href = faviconNormal;
    }
}

document.addEventListener('visibilitychange', () => {
    if (!document.hidden) {
        stopFaviconBlink();
        if (alertBorder && isAlertActive) {
            alertBorder.classList.remove('blinking');
            isAlertActive = false;
        }
    }
});

function filterCallsByState(calls) {
    if (selectedStates.size === 0) {
        return calls;
    }
    
    return calls.filter(call => selectedStates.has(call.state));
}

function updateCallsDisplay(calls = []) {
    const callsList = document.getElementById('callsList');
    const callCount = document.getElementById('callCount');
    
    const filteredCalls = filterCallsByState(calls);
    
    callCount.textContent = `(${filteredCalls.length})`;
    
    if (filteredCalls.length === 0) {
        callsList.innerHTML = '<div class="no-calls">No active fire calls matching your filters</div>';
        return;
    }
    
    callsList.innerHTML = filteredCalls.map(call => {
        const isNew = !knownCallIds.has(call.id);
        
        return `
            <div class="call-card ${isNew ? 'new' : ''}">
                <div class="call-header">
                    <div class="incident-type">${call.agency}</div>
                    <div class="timestamp">${call.timestamp}</div>
                </div>
                <div class="call-details">
                    <div class="location">📍 ${call.location}</div>
                    <span class="state-badge">${call.state}</span>
                </div>
                ${call.transcript ? `<div class="transcript">📝 ${call.transcript}</div>` : ''}
                ${call.audio_url ? `
                    <div class="audio-player">
                        <audio controls preload="none">
                            <source src="${call.audio_url}" type="audio/mpeg">
                            Your browser does not support audio playback.
                        </audio>
                    </div>
                ` : ''}
            </div>
        `;
    }).join('');
}

async function checkForNewCalls() {
    try {
        const response = await fetch('/api/fire-calls');
        const data = await response.json();
        
        const statusEl = document.getElementById('status');
        const lastCheckEl = document.getElementById('lastCheck');
        
        statusEl.textContent = '✓ Active';
        statusEl.className = 'active';
        
        if (data.last_check) {
            const lastCheckTime = new Date(data.last_check);
            const timeString = lastCheckTime.toLocaleString(undefined, {
                hour: 'numeric',
                minute: '2-digit',
                second: '2-digit',
                hour12: true
            });
            lastCheckEl.textContent = `Last check: ${timeString}`;
        }
        
        const filteredCalls = filterCallsByState(data.calls);
        const newCalls = filteredCalls.filter(call => !knownCallIds.has(call.id));
        
        if (newCalls.length > 0) {
            playAlertSound();
            startVisualAlert();
            
            if (document.hidden) {
                startFaviconBlink();
            }
            
            if (Notification.permission === 'granted') {
                newCalls.forEach(call => {
                    new Notification('🔥 New Fire Call!', {
                        body: `${call.agency} - ${call.location}, ${call.state}`,
                        icon: faviconRed,
                        tag: call.id
                    });
                });
            }
        }
        
        data.calls.forEach(call => knownCallIds.add(call.id));
        
        updateCallsDisplay(data.calls);
        
    } catch (error) {
        console.error('Error checking for calls:', error);
        document.getElementById('status').textContent = '✗ Error';
    }
}

function requestNotificationPermission() {
    if ('Notification' in window && Notification.permission === 'default') {
        Notification.requestPermission();
    }
}

function initializeApp() {
    loadSelectedStates();
    loadFilterState();
    loadStates();
    
    requestNotificationPermission();
    
    checkForNewCalls();
    setInterval(checkForNewCalls, 5000);
}

document.addEventListener('DOMContentLoaded', initializeApp);
