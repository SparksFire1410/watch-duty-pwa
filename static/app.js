let audioContext = null;
let selectedStates = new Set(["New Jersey", "New York", "Texas", "Illinois"]);
const states = [
    "Alabama", "Alaska", "Arizona", "Arkansas", "California", "Colorado", "Connecticut", "Delaware",
    "Florida", "Georgia", "Hawaii", "Idaho", "Illinois", "Indiana", "Iowa", "Kansas", "Kentucky",
    "Louisiana", "Maine", "Maryland", "Massachusetts", "Michigan", "Minnesota", "Mississippi",
    "Missouri", "Montana", "Nebraska", "Nevada", "New Hampshire", "New Jersey", "New Mexico",
    "New York", "North Carolina", "North Dakota", "Ohio", "Oklahoma", "Oregon", "Pennsylvania",
    "Rhode Island", "South Carolina", "South Dakota", "Tennessee", "Texas", "Utah", "Vermont",
    "Virginia", "Washington", "West Virginia", "Wisconsin", "Wyoming"
];

let previousUnackCount = 0; // Tracks unacknowledged calls for tab alerts
let playingAudios = new Map(); // Tracks currently playing audio elements by call ID
let activeBlinkInterval = null; // For blinking active title
const normalTitle = 'ED4WD - Fire Call Monitor'; // Default tab title with ED4WD
const blinkTitle = '🔥 NEW CALL! ED4WD'; // Blink title with ED4WD
const activeTitle = '🔥 ACTIVE CALL - ED4WD - Fire Call Monitor'; // Active title with ED4WD

function formatTimestamp(isoString) {
    if (!isoString) return 'Never';
    try {
        const date = new Date(isoString.replace(/Z$/, '')); // Remove 'Z' if present
        if (isNaN(date.getTime())) throw new Error('Invalid date');
        return date.toLocaleString('en-US', { timeZoneName: 'short' });
    } catch (e) {
        console.error('Error parsing timestamp:', isoString, e);
        return 'Invalid Date';
    }
}

function initAudioContext() {
    if (!audioContext) {
        audioContext = new (window.AudioContext || window.webkitAudioContext)();
        console.log('AudioContext initialized');
    }
    if (audioContext.state === 'suspended') {
        audioContext.resume().then(() => {
            console.log('AudioContext resumed');
        }).catch(error => {
            console.error('Error resuming AudioContext:', error);
        });
    }
}

function playAlertSound() {
    if (!audioContext || audioContext.state === 'suspended') {
        console.log('AudioContext not ready. Waiting for user interaction.');
        return;
    }
    try {
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

function triggerAlertBorder() {
    const alertBorder = document.getElementById('alertBorder');
    if (alertBorder) {
        alertBorder.classList.add('blinking');
        setTimeout(() => {
            alertBorder.classList.remove('blinking');
        }, 3000);
    }
}

// Blink the tab title 3 times for new calls
function blinkTabTitle() {
    let blinks = 0;
    const interval = setInterval(() => {
        document.title = blinks % 2 === 0 ? blinkTitle : normalTitle;
        blinks++;
        if (blinks >= 6) { // 3 blinks = 6 toggles (on/off)
            clearInterval(interval);
            setTabTitle(); // Settle to active or normal after blink
        }
    }, 500); // Every half-second
}

// Set tab title based on unacknowledged calls (blink active if any)
function setTabTitle(unackCount = 0) {
    if (unackCount > 0) {
        document.title = activeTitle;
        // Start blinking active title until acknowledged
        if (!activeBlinkInterval) {
            let activeBlink = 0;
            activeBlinkInterval = setInterval(() => {
                document.title = activeBlink % 2 === 0 ? activeTitle : normalTitle;
                activeBlink++;
            }, 1000); // Blink every second
        }
    } else {
        document.title = normalTitle;
        // Stop blinking if no unack calls
        if (activeBlinkInterval) {
            clearInterval(activeBlinkInterval);
            activeBlinkInterval = null;
        }
    }
}

document.addEventListener('click', initAudioContext, { once: true });

function populateStateGrid() {
    const stateGrid = document.getElementById('stateGrid');
    stateGrid.innerHTML = '';
    states.forEach(state => {
        const label = document.createElement('label');
        label.className = 'state-checkbox';
        const checkbox = document.createElement('input');
        checkbox.type = 'checkbox';
        checkbox.name = 'state';
        checkbox.value = state;
        if (selectedStates.has(state)) {
            checkbox.checked = true;
        }
        checkbox.addEventListener('change', handleStateChange);
        label.appendChild(checkbox);
        label.appendChild(document.createTextNode(` ${state}`));
        stateGrid.appendChild(label);
    });
}

function handleStateChange() {
    const checkboxes = document.querySelectorAll('input[name="state"]');
    const newSelectedStates = new Set();
    checkboxes.forEach(checkbox => {
        if (checkbox.checked) {
            if (newSelectedStates.size < 4) {
                newSelectedStates.add(checkbox.value);
            } else {
                checkbox.checked = false;
                alert('You can select up to 4 states only.');
            }
        }
    });
    selectedStates = newSelectedStates;
    console.log(`State filter updated: ${selectedStates.size} states`);
    fetch('/api/state-filter', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ states: Array.from(selectedStates) })
    }).then(() => fetchFireCalls()).catch(error => console.error('Error updating state filter:', error));
}

function updateCallList(calls) {
    const callsList = document.getElementById('callsList');
    const callCount = document.getElementById('callCount');
    if (!callsList || !callCount) {
        console.error('Calls list or call count element not found');
        return;
    }
    callCount.textContent = `(${calls.length})`;
    console.log('Updating call list with:', calls); // Debug calls

    // Track existing cards by ID
    const existingCards = new Map();
    callsList.querySelectorAll('.call-card').forEach(card => {
        const id = card.getAttribute('data-id');
        if (id) existingCards.set(id, card);
    });

    // Update or add cards
    calls.forEach(call => {
        if (!selectedStates.has(call.state)) {
            console.log('Call skipped due to state filter:', call.state);
            return;
        }
        console.log('Checking call:', call);
        const cardId = call.id;
        let card = existingCards.get(cardId);

        if (card) {
            // Check if audio is playing before updating
            const audio = card.querySelector('audio');
            let wasPlaying = false;
            let currentTime = 0;
            if (audio && !audio.paused && !audio.ended) {
                wasPlaying = true;
                currentTime = audio.currentTime;
                audio.pause(); // Pause to safely update
                playingAudios.delete(cardId); // Remove from playing tracker
            }

            // Update existing card (without recreating audio if it existed)
            card.className = `call-card ${call.acknowledged ? '' : 'unacknowledged'}`;
            const date = formatTimestamp(call.timestamp);
            const audioHtml = audio ? `<audio controls src="${call.audio_url}"></audio>` : `<div class="audio-player"><audio controls src="${call.audio_url}"></audio></div>`;
            card.innerHTML = `
                <div class="call-header">
                    <span class="incident-type">${call.agency}</span>
                    <span class="state-badge">${call.state}</span>
                </div>
                <div class="call-details">
                    <p class="location">Location: ${call.location}</p>
                    <div class="transcript">Transcript: ${call.transcript || 'No transcript'}</div>
                    <p class="timestamp">Timestamp: ${date}</p>
                    ${audioHtml}
                    <button class="dismiss-btn" onclick="dismissCall('${call.id}')">×</button>
                </div>
            `;

            // Resume audio if it was playing
            if (wasPlaying) {
                const newAudio = card.querySelector('audio');
                newAudio.currentTime = currentTime;
                newAudio.play().then(() => {
                    playingAudios.set(cardId, newAudio);
                }).catch(e => console.error('Error resuming audio:', e));
            }

            existingCards.delete(cardId); // Mark as updated
        } else {
            // Create new card
            card = document.createElement('div');
            card.setAttribute('data-id', cardId);
            card.className = `call-card ${call.acknowledged ? '' : 'unacknowledged'}`;
            const date = formatTimestamp(call.timestamp);
            card.innerHTML = `
                <div class="call-header">
                    <span class="incident-type">${call.agency}</span>
                    <span class="state-badge">${call.state}</span>
                </div>
                <div class="call-details">
                    <p class="location">Location: ${call.location}</p>
                    <div class="transcript">Transcript: ${call.transcript || 'No transcript'}</div>
                    <p class="timestamp">Timestamp: ${date}</p>
                    <div class="audio-player"><audio controls src="${call.audio_url}"></audio></div>
                    <button class="dismiss-btn" onclick="dismissCall('${call.id}')">×</button>
                </div>
            `;
            card.addEventListener('click', () => {
                if (!call.acknowledged) {
                    acknowledgeCall(call.id);
                }
            });
            callsList.appendChild(card);
        }
    });

    // Remove cards that no longer exist in the data
    existingCards.forEach(card => card.remove());

    if (calls.length === 0) {
        callsList.innerHTML = '<div class="no-calls">No active fire calls</div>';
    }
}

function acknowledgeCall(callId) {
    fetch(`/api/fire-calls/${encodeURIComponent(callId)}/acknowledge`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
    })
    .then(response => {
        if (!response.ok) throw new Error('Failed to acknowledge');
        return response.json();
    })
    .then(data => {
        console.log('Acknowledge response:', data);
        fetchFireCalls(); // Refresh the list
    })
    .catch(error => console.error('Error acknowledging call:', error));
}

function dismissCall(callId) {
    // Stop audio if playing before dismissing
    const audio = playingAudios.get(callId);
    if (audio) {
        audio.pause();
        playingAudios.delete(callId);
    }
    fetch(`/api/fire-calls/${encodeURIComponent(callId)}`, {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json' }
    })
    .then(response => {
        if (!response.ok) throw new Error('Failed to dismiss');
        return response.json();
    })
    .then(data => {
        console.log('Dismiss response:', data);
        fetchFireCalls(); // Refresh the list
    })
    .catch(error => console.error('Error dismissing call:', error));
}

function updateHealthStatus(data) {
    const statusEl = document.getElementById('status');
    const queueEl = document.getElementById('queueStatus');
    const startEl = document.getElementById('checkStart');
    const finishEl = document.getElementById('checkFinish');
    if (statusEl) {
        statusEl.textContent = data.status || 'Unknown';
        statusEl.classList.toggle('active', data.status === 'running');
    }
    if (queueEl) {
        const count = data.queue_size || 0; // Changed to queue_size to reflect all calls
        queueEl.textContent = `Queue: ${count}`;
        queueEl.classList.toggle('queue-active', count > 0);
        console.log('Health status data:', data); // Debug queue count
    }
    if (startEl) startEl.textContent = `Check Start: ${formatTimestamp(data.check_start)}`;
    if (finishEl) finishEl.textContent = `Check Finish: ${formatTimestamp(data.check_finish)}`;
}

function fetchFireCalls() {
    fetch('/api/fire-calls')
        .then(response => {
            if (!response.ok) throw new Error('Network response was not ok');
            return response.json();
        })
        .then(data => {
            console.log('Fire calls received:', data);
            const calls = data.calls || [];
            updateCallList(calls);
            // Count unacknowledged calls (filtered by state)
            const unackCalls = calls.filter(call => !call.acknowledged && selectedStates.has(call.state));
            const currentUnackCount = unackCalls.length;
            // Blink if new unacknowledged calls arrived (reliable for batches)
            if (currentUnackCount > previousUnackCount) {
                playAlertSound(); // Always play on increase
                triggerAlertBorder();
                blinkTabTitle();
            }
            previousUnackCount = currentUnackCount;
            // Set title based on current unack count
            setTabTitle(currentUnackCount);
        })
        .catch(error => console.error('Error fetching fire calls:', error));
}

function fetchHealthStatus() {
    fetch('/api/health')
        .then(response => {
            if (!response.ok) throw new Error('Network response was not ok');
            return response.json();
        })
        .then(data => {
            console.log('Health status received:', data);
            updateHealthStatus(data);
        })
        .catch(error => console.error('Error fetching health status:', error));
}

function toggleStateFilter() {
    const filterContent = document.getElementById('filterContent');
    const collapseIcon = document.getElementById('collapseIcon');
    if (filterContent.classList.contains('collapsed')) {
        filterContent.classList.remove('collapsed');
        collapseIcon.textContent = '▼';
    } else {
        filterContent.classList.add('collapsed');
        collapseIcon.textContent = '▲';
    }
}

document.addEventListener('DOMContentLoaded', () => {
    console.log('DOM loaded');
    // Set initial title
    setTabTitle();
    populateStateGrid();
    const collapseBtn = document.getElementById('collapseBtn');
    if (collapseBtn) {
        collapseBtn.addEventListener('click', toggleStateFilter);
    }
    fetchFireCalls();
    fetchHealthStatus();
    setInterval(fetchFireCalls, 30000); // Slower polling: every 30 seconds to reduce interruptions
    setInterval(fetchHealthStatus, 20000); // Health check every 20 seconds
    navigator.serviceWorker.register('/static/sw.js')
        .then(reg => console.log('Service Worker registered!', reg))
        .catch(err => console.error('Service Worker registration failed:', err));

    // Track audio playback to avoid interruptions
    document.addEventListener('play', (e) => {
        const audio = e.target;
        const card = audio.closest('.call-card');
        if (card) {
            const callId = card.getAttribute('data-id');
            playingAudios.set(callId, audio);
            // New: Acknowledge on play if unacknowledged
            if (card.classList.contains('unacknowledged')) {
                acknowledgeCall(callId);
            }
        }
    }, true);

    document.addEventListener('pause', (e) => {
        const audio = e.target;
        const card = audio.closest('.call-card');
        if (card) {
            const callId = card.getAttribute('data-id');
            playingAudios.delete(callId);
        }
    }, true);
});