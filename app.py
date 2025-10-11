import re
import os
import tempfile
import threading
from collections import deque
from flask import Flask, jsonify, render_template, request
from flask_cors import CORS
from bs4 import BeautifulSoup
import requests
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timedelta
from faster_whisper import WhisperModel
from pydub import AudioSegment

app = Flask(__name__)
CORS(app)

# Initialize Whisper model (small model for better accuracy)
# Using int8 quantization for CPU efficiency
print("Loading Whisper model...")
whisper_model = WhisperModel("small", device="cpu", compute_type="int8")
print("Whisper model loaded successfully")

fire_calls = []
check_start_time = None
check_finish_time = None
processed_audio_urls = set()
processing_lock = threading.Lock()
call_queue = deque()  # Queue for calls waiting to be processed
queue_lock = threading.Lock()
selected_states = set()  # Will be populated with all states by default
states_lock = threading.Lock()

FIRE_KEYWORDS = [
    r'grass[\s_-]?fire',
    r'brush[\s_-]?fire', 
    r'wildland[\s_-]?fire',
    r'wild[\s_-]?fire',
    r'natural[\s_-]?cover[\s_-]?fire',
    r'vegetation[\s_-]?fire',
    r'pasture[\s_-]?fire',
    r'hay[\s_-]?field[\s_-]?fire',
    r'hay[\s_-]?fire',
    r'ditch[\s_-]?fire',
    r'trees?[\s_-]?on[\s_-]?fire',
    r'tree[\s_-]?fire',
    r'bushes?[\s_-]?on[\s_-]?fire',
    r'bush[\s_-]?on[\s_-]?fire',
    r'bush[\s_-]?fire',
    r'controlled[\s_-]?burn',
    r'\bsmoke\b'
]

US_STATES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas",
    "CA": "California", "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware",
    "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho",
    "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas",
    "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
    "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi",
    "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
    "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York",
    "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma",
    "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina",
    "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah",
    "VT": "Vermont", "VA": "Virginia", "WA": "Washington", "WV": "West Virginia",
    "WI": "Wisconsin", "WY": "Wyoming"
}

# Initialize selected_states with all states
selected_states.update(US_STATES.values())

def extract_state_from_location(location):
    parts = location.split(',')
    if len(parts) >= 2:
        state_abbr = parts[-1].strip().upper()
        return US_STATES.get(state_abbr, state_abbr)
    return "Unknown"

def is_fire_call_in_transcript(transcript):
    if not transcript:
        return False
    
    transcript_lower = transcript.lower()
    
    # Check all fire keywords
    for pattern in FIRE_KEYWORDS:
        if re.search(pattern, transcript_lower):
            return True
    
    # Special case: "out of control burn" (any variation)
    if re.search(r'out[\s_-]?of[\s_-]?control[\s_-]?burn', transcript_lower):
        return True
    
    return False

def transcribe_audio_with_whisper(audio_url, max_seconds=25):
    """Transcribe audio, but only process first max_seconds (default 25) for speed"""
    tmp_path = None
    trimmed_path = None
    
    try:
        response = requests.get(audio_url, timeout=30)
        response.raise_for_status()
        
        with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as tmp_file:
            tmp_file.write(response.content)
            tmp_path = tmp_file.name
        
        # Load audio and trim to max_seconds for faster transcription
        audio = AudioSegment.from_mp3(tmp_path)
        max_ms = max_seconds * 1000  # Convert to milliseconds
        
        # Only process if audio is longer than max_seconds, otherwise use original
        if len(audio) > max_ms:
            trimmed_audio = audio[:max_ms]
            with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as trimmed_file:
                trimmed_audio.export(trimmed_file.name, format="mp3")
                trimmed_path = trimmed_file.name
            transcribe_file = trimmed_path
        else:
            transcribe_file = tmp_path
        
        # Transcribe the (possibly trimmed) audio
        segments, info = whisper_model.transcribe(transcribe_file, beam_size=5, language="en")
        
        transcript_parts = []
        for segment in segments:
            transcript_parts.append(segment.text)
        
        transcript = " ".join(transcript_parts).strip()
        
        # Cleanup temp files
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)
        if trimmed_path and os.path.exists(trimmed_path):
            os.unlink(trimmed_path)
            
        return transcript
        
    except Exception as e:
        print(f"Transcription error for {audio_url}: {e}")
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)
        if trimmed_path and os.path.exists(trimmed_path):
            os.unlink(trimmed_path)
        return None

def is_ems_only_agency(agency_name):
    """
    CONSERVATIVE filtering: Only skip agencies that are CLEARLY and OBVIOUSLY EMS-only.
    When in doubt, let it through to the queue for transcription.
    
    Returns True if agency should be skipped (clearly EMS-only).
    Returns False if agency might be fire-related or is ambiguous.
    """
    agency_lower = agency_name.lower()
    
    # Fire-related keywords that indicate fire department involvement
    fire_keywords = [
        r'\bfire\b',
        r'\bfd\b',
        r'\bvfd\b',
        r'fire[-_\s]?dept',
        r'fire[-_\s]?department',
        r'fire[-_\s]?rescue',
        r'fire[-_\s]?ems',
        r'fire[-_\s]?district'
    ]
    
    # Check if agency has fire-related keywords
    has_fire = any(re.search(pattern, agency_lower) for pattern in fire_keywords)
    
    if has_fire:
        return False  # Has fire department, don't skip
    
    # VERY STRICT EMS-only patterns - only filter the most obvious cases
    # Examples: "County_EMS", "Ambulance_Service", "MedicUnit", "Paramedic_Response"
    # Will NOT match: "Station_20", "Saltillo_9", "AntrimAmb" (ambiguous cases)
    obvious_ems_patterns = [
        r'(^|[-_\s])ems([-_\s]|$)',           # "EMS" as standalone word with separators
        r'(^|[-_\s])ambulance([-_\s]|$)',     # "Ambulance" as standalone word
        r'(^|[-_\s])medic([-_\s]|$)',         # "Medic" as standalone word (not "medical")
        r'(^|[-_\s])paramedic',               # "Paramedic" prefix
        r'(^|[-_\s])emt([-_\s]|$)',           # "EMT" as standalone word
        r'medical[-_\s]service',              # "Medical Service" or "Medical_Service"
        r'emergency[-_\s]medical[-_\s]service' # "Emergency Medical Service"
    ]
    
    # Only skip if agency has OBVIOUS EMS-only patterns
    has_obvious_ems = any(re.search(pattern, agency_lower) for pattern in obvious_ems_patterns)
    
    if has_obvious_ems:
        return True  # Clearly EMS-only, skip transcription
    
    # Default: When in doubt, let it through for transcription
    return False

def cleanup_old_calls():
    """Remove calls older than 1 hour, but always keep the last 5 calls"""
    global fire_calls
    
    if len(fire_calls) <= 5:
        return
    
    try:
        now = datetime.utcnow()
        one_hour_ago = now - timedelta(hours=1)
        
        # Separate calls into old and recent
        old_calls = []
        recent_calls = []
        
        for call in fire_calls:
            if 'first_detected' in call:
                first_detected = datetime.fromisoformat(call['first_detected'].replace('Z', '+00:00'))
                if first_detected < one_hour_ago:
                    old_calls.append(call)
                else:
                    recent_calls.append(call)
        
        # Keep recent calls + the last 5 total (even if old)
        calls_to_keep = recent_calls + fire_calls[-5:]
        
        # Remove duplicates while preserving order
        seen_ids = set()
        unique_calls = []
        for call in calls_to_keep:
            if call['id'] not in seen_ids:
                seen_ids.add(call['id'])
                unique_calls.append(call)
        
        removed_count = len(fire_calls) - len(unique_calls)
        if removed_count > 0:
            fire_calls = unique_calls
            print(f"Cleaned up {removed_count} old calls (keeping {len(fire_calls)} calls)")
    
    except Exception as e:
        print(f"Error during cleanup: {e}")

def process_call_queue():
    """Process calls from the queue"""
    global fire_calls
    
    if not processing_lock.acquire(blocking=False):
        return
    
    try:
        processed_count = 0
        max_per_cycle = 15  # Process up to 15 calls per cycle
        
        while processed_count < max_per_cycle:
            with queue_lock:
                if not call_queue:
                    break
                call_info = call_queue.popleft()
            
            print(f"Processing queued call from {call_info['agency']} at {call_info['location']}")
            
            # Transcribe only first 25 seconds for speed
            transcript = transcribe_audio_with_whisper(call_info['audio_url'], max_seconds=25)
            
            # Mark as processed
            processed_audio_urls.add(call_info['audio_url'])
            
            if transcript and is_fire_call_in_transcript(transcript):
                # Check if this call already exists
                call_id = call_info['audio_url']
                existing_call = next((c for c in fire_calls if c['id'] == call_id), None)
                
                if existing_call:
                    # Update existing call with new transcript if different
                    if existing_call.get('transcript') != transcript:
                        existing_call['transcript'] = transcript
                        print(f"🔄 UPDATED: {call_info['agency']} - {call_info['location']}")
                        print(f"   New transcript (25s): {transcript[:100]}...")
                else:
                    # Add new call
                    call_data = {
                        'audio_url': call_info['audio_url'],  # Keep full audio for playback
                        'agency': call_info['agency'],
                        'location': call_info['location'],
                        'state': call_info['state'],
                        'timestamp': call_info['timestamp'],
                        'transcript': transcript,
                        'first_detected': datetime.utcnow().isoformat() + 'Z',
                        'id': call_info['audio_url']
                    }
                    
                    fire_calls.insert(0, call_data)
                    print(f"🔥 FIRE CALL DETECTED: {call_info['agency']} - {call_info['location']}")
                    print(f"   Transcript (25s): {transcript[:100]}...")
            
            processed_count += 1
        
        if processed_count > 0:
            with queue_lock:
                queue_size = len(call_queue)
            print(f"Queue processing: {processed_count} calls processed, {queue_size} remaining in queue")
            
    except Exception as e:
        print(f"Error processing queue: {e}")
    finally:
        processing_lock.release()

def recheck_recent_calls():
    """Re-check audio for calls detected in the last 10 minutes to see if full audio is available"""
    global fire_calls
    
    if not processing_lock.acquire(blocking=False):
        print("Re-check skipped - scan in progress")
        return
    
    try:
        now = datetime.utcnow()
        cutoff_time = now - timedelta(minutes=10)
        
        updated_count = 0
        
        for call in fire_calls:
            # Check if this call is less than 10 minutes old
            if 'first_detected' in call:
                first_detected = datetime.fromisoformat(call['first_detected'].replace('Z', '+00:00'))
                if first_detected > cutoff_time:
                    # Re-transcribe to check for updated audio
                    print(f"Re-checking audio for {call['agency']} at {call['location']}")
                    new_transcript = transcribe_audio_with_whisper(call['audio_url'])
                    
                    # Update if we got a better/different transcript
                    if new_transcript and new_transcript != call.get('transcript', ''):
                        old_length = len(call.get('transcript', ''))
                        new_length = len(new_transcript)
                        
                        if new_length > old_length:
                            call['transcript'] = new_transcript
                            updated_count += 1
                            print(f"✓ Updated transcript for {call['agency']} ({old_length} -> {new_length} chars)")
        
        if updated_count > 0:
            print(f"Re-check complete. Updated {updated_count} calls with better audio")
        else:
            print("Re-check complete. No updates needed")
        
        # Clean up old calls after re-check
        cleanup_old_calls()
            
    except Exception as e:
        print(f"Error during re-check: {e}")
    finally:
        processing_lock.release()

def scrape_dispatch_calls(max_rows=60, is_initial_scan=False):
    """Scan for new calls and add them to the queue"""
    global check_start_time, check_finish_time, processed_audio_urls
    
    try:
        # Set check start time at the start of the scan
        check_start_time = datetime.utcnow().isoformat() + 'Z'
        
        url = "https://call-log-api.edispatches.com/calls/"
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        table = soup.find('table')
        
        if table:
            rows = table.find_all('tr')
            new_calls_found = 0
            
            # Scan last 60 calls by default
            scan_limit = max_rows
            if is_initial_scan:
                print(f"Initial scan: checking last {scan_limit} calls...")
            
            for row in rows[:scan_limit]:
                cols = row.find_all('td')
                if len(cols) >= 4:
                    audio_tag = cols[0].find('audio')
                    if audio_tag and audio_tag.get('src'):
                        audio_url = audio_tag.get('src')
                        agency = cols[1].text.strip()
                        location = cols[2].text.strip()
                        timestamp = cols[3].text.strip()
                        state = extract_state_from_location(location)
                        
                        # Add to queue if not already processed AND state is selected AND not EMS-only
                        if audio_url not in processed_audio_urls:
                            # Check if this state is selected
                            with states_lock:
                                state_is_selected = state in selected_states
                            
                            if state_is_selected:
                                # Skip EMS-only agencies before adding to queue (saves processing time)
                                if is_ems_only_agency(agency):
                                    processed_audio_urls.add(audio_url)  # Mark as processed
                                    continue
                                
                                call_info = {
                                    'audio_url': audio_url,
                                    'agency': agency,
                                    'location': location,
                                    'state': state,
                                    'timestamp': timestamp
                                }
                                
                                with queue_lock:
                                    call_queue.append(call_info)
                                new_calls_found += 1
            
            if new_calls_found > 0:
                with queue_lock:
                    queue_size = len(call_queue)
                print(f"Scan complete. Added {new_calls_found} new calls to queue (Queue size: {queue_size})")
            else:
                print(f"Scan complete. No new calls found")
        
        # Set check finish time at the end of the scan
        check_finish_time = datetime.utcnow().isoformat() + 'Z'
        
    except Exception as e:
        print(f"Error scraping dispatch calls: {e}")
        check_finish_time = datetime.utcnow().isoformat() + 'Z'

@app.route('/')
def index():
    response = app.make_response(render_template('index.html'))
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

@app.route('/api/fire-calls')
def get_fire_calls():
    with queue_lock:
        queue_size = len(call_queue)
    
    return jsonify({
        'calls': fire_calls,
        'check_start': check_start_time,
        'check_finish': check_finish_time,
        'queue_size': queue_size
    })

@app.route('/api/states')
def get_states():
    return jsonify({'states': list(US_STATES.values())})

@app.route('/api/health')
def health():
    return jsonify({
        'status': 'running',
        'check_start': check_start_time,
        'check_finish': check_finish_time,
        'fire_calls_count': len(fire_calls)
    })

@app.route('/api/fire-calls/<path:call_id>', methods=['DELETE'])
def delete_fire_call(call_id):
    global fire_calls
    
    # Find and remove the call with the matching ID
    original_count = len(fire_calls)
    fire_calls = [call for call in fire_calls if call['id'] != call_id]
    
    if len(fire_calls) < original_count:
        return jsonify({'success': True, 'message': 'Call dismissed'})
    else:
        return jsonify({'success': False, 'message': 'Call not found'}), 404

@app.route('/api/state-filter', methods=['POST'])
def update_state_filter():
    """Update which states to monitor"""
    global selected_states
    
    try:
        data = request.get_json()
        states = data.get('states', [])
        
        with states_lock:
            selected_states = set(states)
        
        # Remove calls from queue that are no longer in selected states
        with queue_lock:
            filtered_queue = deque()
            removed_count = 0
            
            for call_info in call_queue:
                if call_info['state'] in selected_states:
                    filtered_queue.append(call_info)
                else:
                    removed_count += 1
            
            call_queue.clear()
            call_queue.extend(filtered_queue)
            queue_size = len(call_queue)
        
        print(f"State filter updated: {len(selected_states)} states selected, removed {removed_count} calls from queue")
        
        return jsonify({
            'success': True, 
            'selected_count': len(selected_states),
            'queue_size': queue_size,
            'removed_from_queue': removed_count
        })
        
    except Exception as e:
        print(f"Error updating state filter: {e}")
        return jsonify({'success': False, 'error': str(e)}), 400

scheduler = BackgroundScheduler()
scheduler.add_job(func=scrape_dispatch_calls, trigger="interval", seconds=60)
scheduler.add_job(func=process_call_queue, trigger="interval", seconds=10)  # Process queue every 10 seconds
scheduler.add_job(func=recheck_recent_calls, trigger="interval", seconds=60)
scheduler.start()

# Run initial scan in background thread so app can start
print("Starting initial scan of last 60 calls...")
threading.Thread(target=lambda: scrape_dispatch_calls(max_rows=60, is_initial_scan=True), daemon=True).start()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
