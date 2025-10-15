import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

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
import pytz
import time
from faster_whisper import WhisperModel
from pydub import AudioSegment

app = Flask(__name__)
CORS(app)

whisper_model = None
fire_calls = []
check_start_time = None
check_finish_time = None
processed_audio_urls = set()
processing_lock = threading.Lock()
call_queue = deque()
queue_lock = threading.Lock()
selected_states = set(["New Jersey", "New York", "Texas", "Illinois"])
states_lock = threading.Lock()
state_call_tracking = {}
MAX_CALLS_PER_STATE = 20

FIRE_KEYWORDS = [
    r'grass[\s_-]?fire', r'grass[\s_-]?on[\s_-]?fire',
    r'brush[\s_-]?fire', r'brush[\s_-]?on[\s_-]?fire',
    r'wildland[\s_-]?fire', r'wild[\s_-]?fire',
    r'natural[\s_-]?cover[\s_-]?fire',
    r'vegetation[\s_-]?fire', r'vegetation[\s_-]?on[\s_-]?fire',
    r'pasture[\s_-]?fire', r'pasture[\s_-]?on[\s_-]?fire',
    r'hay[\s_-]?field[\s_-]?fire', r'hay[\s_-]?fire', r'hay[\s_-]?on[\s_-]?fire',
    r'ditch[\s_-]?fire', r'ditch[\s_-]?on[\s_-]?fire',
    r'trees?[\s_-]?on[\s_-]?fire', r'tree[\s_-]?fire',
    r'bushes?[\s_-]?on[\s_-]?fire', r'bush[\s_-]?on[\s_-]?fire', r'bush[\s_-]?fire',
    r'controlled[\s_-]?burn',
    r'\bsmoke\b', r'\bsmoking\b',
    r'structures?[\s_-]?in[\s_-]?danger', r'structures?[\s_-]?threatened',
    r'outside[\s_-]?fire',
    r'out[\s_-]?side[\s_-]?fire',
    r'fire[\s_-]?outside',
    r'fire[\s_-]?out[\s_-]?side',
    r'\bufo\b',
    r'unidentified[\s_-]?flying[\s_-]?objects'
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
    for pattern in FIRE_KEYWORDS:
        if re.search(pattern, transcript_lower):
            return True
    if re.search(r'out[\s_-]?of[\s_-]?control[\s_-]?burn', transcript_lower):
        return True
    return False

def transcribe_audio_with_whisper(audio_url, max_seconds=25):
    global whisper_model
    if whisper_model is None:
        logging.info("Loading Whisper model...")
        whisper_model = WhisperModel("small", device="cpu", compute_type="int8")
        logging.info("Whisper model loaded successfully")
    tmp_path = None
    trimmed_path = None
    try:
        response = requests.get(audio_url, timeout=30)
        response.raise_for_status()
        with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as tmp_file:
            tmp_file.write(response.content)
            tmp_path = tmp_file.name
        audio = AudioSegment.from_mp3(tmp_path)
        max_ms = max_seconds * 1000
        if len(audio) > max_ms:
            trimmed_audio = audio[:max_ms]
            with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as trimmed_file:
                trimmed_audio.export(trimmed_file.name, format="mp3")
                trimmed_path = trimmed_file.name
            transcribe_file = trimmed_path
        else:
            transcribe_file = tmp_path
        segments, info = whisper_model.transcribe(transcribe_file, beam_size=5, language="en")
        transcript_parts = [segment.text for segment in segments]
        transcript = " ".join(transcript_parts).strip()
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)
        if trimmed_path and os.path.exists(trimmed_path):
            os.unlink(trimmed_path)
        return transcript
    except Exception as e:
        logging.error(f"Transcription error for {audio_url}: {str(e)}")
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)
        if trimmed_path and os.path.exists(trimmed_path):
            os.unlink(trimmed_path)
        return None

def is_ems_only_agency(agency_name):
    agency_lower = agency_name.lower()
    fire_keywords = [
        r'\bfire\b', r'\bfd\b', r'\bvfd\b',
        r'fire[-_\s]?dept', r'fire[-_\s]?department',
        r'fire[-_\s]?rescue', r'fire[-_\s]?ems',
        r'fire[-_\s]?district'
    ]
    has_fire = any(re.search(pattern, agency_lower) for pattern in fire_keywords)
    if has_fire:
        return False
    obvious_ems_patterns = [
        r'(^|[-_\s])ems([-_\s]|$)', r'(^|[-_\s])ambulance([-_\s]|$)',
        r'(^|[-_\s])medic([-_\s]|$)', r'(^|[-_\s])paramedic',
        r'(^|[-_\s])emt([-_\s]|$)', r'medical[-_\s]service',
        r'emergency[-_\s]medical[-_\s]service'
    ]
    has_obvious_ems = any(re.search(pattern, agency_lower) for pattern in obvious_ems_patterns)
    return has_obvious_ems

def cleanup_old_calls():
    global fire_calls
    if len(fire_calls) <= 5:
        return
    try:
        now = datetime.now(pytz.UTC)
        one_hour_ago = now - timedelta(hours=1)
        old_calls = []
        recent_calls = []
        for call in fire_calls:
            if 'first_detected' in call:
                first_detected = datetime.fromisoformat(call['first_detected'].replace('Z', '+00:00')).replace(tzinfo=pytz.UTC)
                if first_detected < one_hour_ago:
                    old_calls.append(call)
                else:
                    recent_calls.append(call)
        calls_to_keep = recent_calls + fire_calls[-5:]
        seen_ids = set()
        unique_calls = []
        for call in calls_to_keep:
            if call['id'] not in seen_ids:
                seen_ids.add(call['id'])
                unique_calls.append(call)
        removed_count = len(fire_calls) - len(unique_calls)
        if removed_count > 0:
            fire_calls = unique_calls
            logging.info(f"Cleaned up {removed_count} old calls (keeping {len(fire_calls)} calls)")
    except Exception as e:
        logging.error(f"Error during cleanup: {str(e)}")

def process_call_queue():
    global fire_calls
    if not processing_lock.acquire(blocking=False):
        return
    try:
        processed_count = 0
        max_per_cycle = 5
        while processed_count < max_per_cycle:
            with queue_lock:
                if not call_queue:
                    break
                call_info = call_queue.popleft()
            logging.info(f"Processing queued call from {call_info['agency']} at {call_info['location']}")
            transcript = transcribe_audio_with_whisper(call_info['audio_url'], max_seconds=25)
            processed_audio_urls.add(call_info['audio_url'])
            if transcript and is_fire_call_in_transcript(transcript):
                call_id = call_info['audio_url']
                existing_call = next((c for c in fire_calls if c['id'] == call_id), None)
                if existing_call:
                    if existing_call.get('transcript') != transcript:
                        existing_call['transcript'] = transcript
                        logging.info(f"🔄 UPDATED: {call_info['agency']} - {call_info['location']}")
                        logging.info(f"   New transcript (25s): {transcript[:100]}...")
                else:
                    call_data = {
                        'audio_url': call_info['audio_url'],
                        'agency': call_info['agency'],
                        'location': call_info['location'],
                        'state': call_info['state'],
                        'timestamp': call_info['timestamp'],
                        'transcript': transcript,
                        'first_detected': datetime.now(pytz.UTC).isoformat() + 'Z',
                        'id': call_info['audio_url'],
                        'acknowledged': False
                    }
                    fire_calls.insert(0, call_data)
                    logging.info(f"🔥 FIRE CALL DETECTED: {call_info['agency']} - {call_info['location']}")
                    logging.info(f"   Transcript (25s): {transcript[:100]}...")
            else:
                logging.info(f"❌ No fire keywords detected in {call_info['agency']}")
                logging.info(f"   Transcript: {transcript[:150]}...")
            processed_count += 1
            time.sleep(1)
        if processed_count > 0:
            with queue_lock:
                queue_size = len(call_queue)
            logging.info(f"Queue processing: {processed_count} calls processed, {queue_size} remaining in queue")
    except Exception as e:
        logging.error(f"Error processing queue: {str(e)}")
    finally:
        processing_lock.release()

def recheck_recent_calls():
    global fire_calls
    if not processing_lock.acquire(blocking=False):
        logging.info("Re-check skipped - scan in progress")
        return
    try:
        now = datetime.now(pytz.UTC)
        cutoff_time = now - timedelta(minutes=10)
        updated_count = 0
        for call in fire_calls:
            if 'first_detected' in call:
                first_detected = datetime.fromisoformat(call['first_detected'].replace('Z', '+00:00')).replace(tzinfo=pytz.UTC)
                if first_detected > cutoff_time:
                    logging.info(f"Re-checking audio for {call['agency']} at {call['location']}")
                    new_transcript = transcribe_audio_with_whisper(call['audio_url'])
                    if new_transcript and new_transcript != call.get('transcript', ''):
                        old_length = len(call.get('transcript', ''))
                        new_length = len(new_transcript)
                        if new_length > old_length:
                            call['transcript'] = new_transcript
                            updated_count += 1
                            logging.info(f"✓ Updated transcript for {call['agency']} ({old_length} -> {new_length} chars)")
        if updated_count > 0:
            logging.info(f"Re-check complete. Updated {updated_count} calls with better audio")
        else:
            logging.info("Re-check complete. No updates needed")
        cleanup_old_calls()
    except Exception as e:
        logging.error(f"Error during re-check: {str(e)}")
    finally:
        processing_lock.release()

def scrape_dispatch_calls(max_rows=10, is_initial_scan=False):
    global check_start_time, check_finish_time, processed_audio_urls, state_call_tracking
    logging.info("Fetching dispatch data...")
    try:
        check_start_time = datetime.now(pytz.UTC).isoformat() + 'Z'
        url = "https://call-log-api.edispatches.com/calls/"
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        table = soup.find('table')
        if table:
            rows = table.find_all('tr')
            scan_limit = max_rows if not is_initial_scan else 20
            if is_initial_scan:
                logging.info(f"Initial scan: checking last {scan_limit} calls (max 20 per selected state)...")
            scan_calls_by_state = {}
            for row in rows[:scan_limit]:
                cols = row.find_all('td')
                if len(cols) >= 4:
                    audio_tag = cols[0].find('audio')
                    if audio_tag and audio_tag.get('src'):
                        audio_url = audio_tag.get('src')
                        agency = cols[1].text.strip()
                        location = cols[2].text.strip()
                        timestamp_str = cols[3].text.strip()
                        state = extract_state_from_location(location)
                        with states_lock:
                            state_is_selected = state in selected_states
                        if not state_is_selected:
                            processed_audio_urls.add(audio_url)  # Skip and mark as processed
                            logging.info(f"Skipped call from {agency} in {state} - not in selected states")
                            continue
                        if is_ems_only_agency(agency):
                            processed_audio_urls.add(audio_url)
                            continue
                        try:
                            call_time = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S').replace(tzinfo=pytz.UTC)
                        except:
                            call_time = datetime.now(pytz.UTC)
                        call_info = {
                            'audio_url': audio_url,
                            'agency': agency,
                            'location': location,
                            'state': state,
                            'timestamp': timestamp_str,
                            'call_time': call_time
                        }
                        if state not in scan_calls_by_state:
                            scan_calls_by_state[state] = []
                        scan_calls_by_state[state].append(call_info)
            with queue_lock:
                call_queue.clear()
                for state, calls in scan_calls_by_state.items():
                    calls.sort(key=lambda x: x['call_time'], reverse=True)
                    recent_calls = calls[:MAX_CALLS_PER_STATE]
                    for call_info in recent_calls:
                        if call_info['audio_url'] not in processed_audio_urls:
                            queue_call = {k: v for k, v in call_info.items() if k != 'call_time'}
                            call_queue.append(queue_call)
                queue_size = len(call_queue)
                state_call_tracking = scan_calls_by_state
            if queue_size > 0:
                logging.info(f"Scan complete. Queue rebuilt: {queue_size} calls (max 20 per state)")
            else:
                logging.info(f"Scan complete. No new calls found")
        check_finish_time = datetime.now(pytz.UTC).isoformat() + 'Z'
    except Exception as e:
        logging.error(f"Error scraping dispatch calls: {str(e)}")
    finally:
        check_finish_time = datetime.now(pytz.UTC).isoformat() + 'Z'

@app.route('/')
def index():
    response = app.make_response(render_template('index.html'))
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

@app.route('/api/health', methods=['GET'])
def health_check():
    global fire_calls, check_start_time, check_finish_time
    with queue_lock:
        queue_size = len(call_queue)
    return jsonify({
        'status': 'running',
        'check_start': check_start_time or datetime.now(pytz.UTC).isoformat() + 'Z',
        'check_finish': check_finish_time or datetime.now(pytz.UTC).isoformat() + 'Z',
        'queue_size': queue_size
    })

@app.route('/api/fire-calls')
def get_fire_calls():
    with queue_lock:
        queue_size = len(call_queue)
    return jsonify({
        'calls': fire_calls,
        'check_start': check_start_time or datetime.now(pytz.UTC).isoformat() + 'Z',
        'check_finish': check_finish_time or datetime.now(pytz.UTC).isoformat() + 'Z',
        'queue_size': queue_size
    })

@app.route('/api/states')
def get_states():
    return jsonify({'states': list(US_STATES.values())})

@app.route('/api/fire-calls/<path:call_id>', methods=['DELETE'])
def delete_fire_call(call_id):
    global fire_calls
    original_count = len(fire_calls)
    fire_calls = [call for call in fire_calls if call['id'] != call_id]
    if len(fire_calls) < original_count:
        return jsonify({'success': True, 'message': 'Call dismissed'})
    else:
        return jsonify({'success': False, 'message': 'Call not found'}), 404

@app.route('/api/state-filter', methods=['POST'])
def update_state_filter():
    global selected_states
    try:
        data = request.get_json()
        states = data.get('states', [])[:4]
        with states_lock:
            selected_states = set(states)
            if len(selected_states) > 4:
                selected_states = set(list(selected_states)[:4])
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

@app.route('/api/fire-calls/<path:call_id>/acknowledge', methods=['POST'])
def acknowledge_fire_call(call_id):
    global fire_calls
    for call in fire_calls:
        if call['id'] == call_id:
            call['acknowledged'] = True
            return jsonify({'success': True, 'message': 'Call acknowledged'})
    return jsonify({'success': False, 'message': 'Call not found'}), 404
    
scheduler = BackgroundScheduler({'apscheduler.job_defaults.max_instances': 3})
# ... (all your existing code up to the scheduler definition)

scheduler = BackgroundScheduler({'apscheduler.job_defaults.max_instances': 3})

# Define the utility function inside the main script scope, 
# or keep it as you had it, but ensure it's defined before it's added.
def initial_scan_job(scheduler_ref):
    # This runs the initial scan logic once
    logging.info("Starting initial scan (one-time job)...")
    scrape_dispatch_calls(max_rows=20, is_initial_scan=True)
    # Remove this job after it runs
    try:
        scheduler_ref.remove_job('initial_scan')
        logging.info("Initial scan complete and job removed.")
    except Exception as e:
        logging.warning(f"Failed to remove initial_scan job: {e}")

# 1. Add recurring jobs
scheduler.add_job(func=scrape_dispatch_calls, trigger="interval", seconds=60, max_instances=3)
scheduler.add_job(func=process_call_queue, trigger="interval", seconds=30, max_instances=3)
scheduler.add_job(func=recheck_recent_calls, trigger="interval", seconds=120, max_instances=3)

# 2. Add the one-time initial scan job
from datetime import datetime
scheduler.add_job(
    func=initial_scan_job, 
    id='initial_scan', 
    name='initial_scan', 
    args=[scheduler], 
    trigger='date', 
    run_date=datetime.now()
)

# 3. Start the scheduler once
logging.info("Starting BackgroundScheduler...")
scheduler.start()

# Everything is now configured correctly for Gunicorn to run 'app:app'
# and the background tasks will execute robustly.
