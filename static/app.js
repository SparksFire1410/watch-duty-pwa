let selectedStates = new Set();
let knownCallIds = new Set();
let highlightedCalls = new Set();
let isAlertActive = false;
let alertBorder = null;
let audioContext = null;
let faviconBlinkInterval = null;
let faviconSolidTimeout = null;
let tabHasAlert = false;
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
    // Send initial state selection to backend
    updateBackendStateFilter();
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

function initAudioContext() {
    if (!audioContext) {
        audioContext = new (window.AudioContext || window.webkitAudioContext)();
    }
    if (audioContext.state === 'suspended') {
        audioContext.resume();
    }
}

function saveSelectedStates() {
    localStorage.setItem('selectedStates', JSON.stringify([...selectedStates]));
    updateBackendStateFilter();
}

async function updateBackendStateFilter() {
    try {
        const response = await fetch('/api/state-filter', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                states: [...selectedStates]
            })
        });
        
        const data = await response.json();
        if (data.success) {
            console.log(`State filter updated: ${data.selected_count} states, removed ${data.removed_from_queue} from queue`);
        }
    } catch (error) {
        console.error('Error updating backend state filter:', error);
    }
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
    try {
        if (!audioContext) {
            audioContext = new (window.AudioContext || window.webkitAudioContext)();
        }
        
        if (audioContext.state === 'suspended') {
            audioContext.resume();
        }
        
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
    } catch (error) {
        console.error('Error playing alert sound:', error);
    }
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
    const favicon = document.querySelector("link[rel*='icon']");
    
    if (faviconBlinkInterval) {
        clearInterval(faviconBlinkInterval);
    }
    if (faviconSolidTimeout) {
        clearTimeout(faviconSolidTimeout);
    }
    
    let isRed = false;
    tabHasAlert = true;
    
    faviconBlinkInterval = setInterval(() => {
        isRed = !isRed;
        favicon.href = isRed ? faviconRed : faviconNormal;
    }, 500);
    
    faviconSolidTimeout = setTimeout(() => {
        clearInterval(faviconBlinkInterval);
        faviconBlinkInterval = null;
        favicon.href = faviconRed;
    }, 5000);
}

function clearFaviconAlert() {
    if (faviconBlinkInterval) {
        clearInterval(faviconBlinkInterval);
        faviconBlinkInterval = null;
    }
    if (faviconSolidTimeout) {
        clearTimeout(faviconSolidTimeout);
        faviconSolidTimeout = null;
    }
    
    const favicon = document.querySelector("link[rel*='icon']");
    favicon.href = faviconNormal;
    tabHasAlert = false;
}

document.addEventListener('click', () => {
    if (tabHasAlert) {
        clearFaviconAlert();
    }
});

document.addEventListener('visibilitychange', () => {
    if (!document.hidden) {
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

function unhighlightCall(callId) {
    highlightedCalls.delete(callId);
    const callCard = document.querySelector(`[data-call-id="${callId}"]`);
    if (callCard) {
        callCard.classList.remove('highlighted');
    }
}

async function dismissCall(callId) {
    try {
        const response = await fetch(`/api/fire-calls/${encodeURIComponent(callId)}`, {
            method: 'DELETE'
        });
        
        if (response.ok) {
            knownCallIds.delete(callId);
            highlightedCalls.delete(callId);
            checkForNewCalls();
        } else {
            console.error('Failed to dismiss call');
        }
    } catch (error) {
        console.error('Error dismissing call:', error);
    }
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
    
    // Get existing call IDs in the DOM
    const existingCallIds = new Set(
        Array.from(callsList.querySelectorAll('.call-card')).map(card => card.dataset.callId)
    );
    
    const currentCallIds = new Set(filteredCalls.map(call => call.id));
    
    // Remove calls that no longer exist
    existingCallIds.forEach(id => {
        if (!currentCallIds.has(id)) {
            const card = callsList.querySelector(`[data-call-id="${id}"]`);
            if (card) card.remove();
        }
    });
    
    // Add or update calls
    filteredCalls.forEach((call, index) => {
        let callCard = callsList.querySelector(`[data-call-id="${call.id}"]`);
        const isNew = !knownCallIds.has(call.id);
        const isHighlighted = highlightedCalls.has(call.id);
        
        if (!callCard) {
            // Create new call card
            const cardHTML = `
                <div class="call-card ${isNew ? 'new' : ''} ${isHighlighted ? 'highlighted' : ''}" 
                     data-call-id="${call.id}" 
                     onclick="unhighlightCall('${call.id.replace(/'/g, "\\'")}')">
                    <button class="dismiss-btn" onclick="event.stopPropagation(); dismissCall('${call.id.replace(/'/g, "\\'")}')">✕</button>
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
                            <audio controls preload="none" data-call-id="${call.id}">
                                <source src="${call.audio_url}" type="audio/mpeg">
                                Your browser does not support audio playback.
                            </audio>
                        </div>
                    ` : ''}
                </div>
            `;
            
            // Insert at correct position
            const existingCards = callsList.querySelectorAll('.call-card');
            if (index < existingCards.length) {
                existingCards[index].insertAdjacentHTML('beforebegin', cardHTML);
            } else {
                callsList.insertAdjacentHTML('beforeend', cardHTML);
            }
            
            // Add play event listener to audio element
            if (call.audio_url) {
                const newCard = callsList.querySelector(`[data-call-id="${call.id}"]`);
                const audioElement = newCard.querySelector('audio');
                if (audioElement) {
                    audioElement.setAttribute('data-listener-attached', 'true');
                    audioElement.addEventListener('play', (e) => {
                        e.stopPropagation();
                        unhighlightCall(call.id);
                    });
                }
            }
        } else {
            // Update existing card's classes without recreating it
            callCard.className = `call-card ${isNew ? 'new' : ''} ${isHighlighted ? 'highlighted' : ''}`;
            
            // Ensure correct position
            const existingCards = Array.from(callsList.querySelectorAll('.call-card'));
            const currentIndex = existingCards.indexOf(callCard);
            if (currentIndex !== index && existingCards[index]) {
                callsList.insertBefore(callCard, existingCards[index]);
            }
            
            // Make sure audio element has play event listener
            if (call.audio_url) {
                const audioElement = callCard.querySelector('audio');
                if (audioElement && !audioElement.hasAttribute('data-listener-attached')) {
                    audioElement.setAttribute('data-listener-attached', 'true');
                    audioElement.addEventListener('play', (e) => {
                        e.stopPropagation();
                        unhighlightCall(call.id);
                    });
                }
            }
        }
    });
}

async function checkForNewCalls() {
    try {
        const response = await fetch('/api/fire-calls');
        const data = await response.json();
        
        const statusEl = document.getElementById('status');
        const checkStartEl = document.getElementById('checkStart');
        const checkFinishEl = document.getElementById('checkFinish');
        const queueStatusEl = document.getElementById('queueStatus');
        
        statusEl.textContent = '✓ Active';
        statusEl.className = 'active';
        
        if (data.check_start) {
            const checkStartTime = new Date(data.check_start);
            const startString = checkStartTime.toLocaleString(undefined, {
                hour: 'numeric',
                minute: '2-digit',
                second: '2-digit',
                hour12: true
            });
            checkStartEl.textContent = `Check Start: ${startString}`;
        }
        
        if (data.check_finish) {
            const checkFinishTime = new Date(data.check_finish);
            const finishString = checkFinishTime.toLocaleString(undefined, {
                hour: 'numeric',
                minute: '2-digit',
                second: '2-digit',
                hour12: true
            });
            checkFinishEl.textContent = `Check Finish: ${finishString}`;
        } else {
            checkFinishEl.textContent = 'Check Finish: Processing...';
        }
        
        // Update queue status
        const queueSize = data.queue_size || 0;
        queueStatusEl.textContent = `Queue: ${queueSize}`;
        if (queueSize > 0) {
            queueStatusEl.className = 'queue-active';
        } else {
            queueStatusEl.className = '';
        }
        
        const filteredCalls = filterCallsByState(data.calls);
        const newCalls = filteredCalls.filter(call => !knownCallIds.has(call.id));
        
        if (newCalls.length > 0) {
            newCalls.forEach(call => highlightedCalls.add(call.id));
            
            playAlertSound();
            startVisualAlert();
            startFaviconBlink();
            
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
    
    document.addEventListener('click', initAudioContext, { once: true });
    document.addEventListener('keydown', initAudioContext, { once: true });
    
    checkForNewCalls();
    setInterval(checkForNewCalls, 5000);
}

document.addEventListener('DOMContentLoaded', initializeApp);
