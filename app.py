import re
import os
import tempfile
import threading
from flask import Flask, jsonify, render_template
from flask_cors import CORS
from bs4 import BeautifulSoup
import requests
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timedelta
from faster_whisper import WhisperModel

app = Flask(__name__)
CORS(app)

# Initialize Whisper model (small model for faster processing)
# Using int8 quantization for CPU efficiency
print("Loading Whisper model...")
whisper_model = WhisperModel("small", device="cpu", compute_type="int8")
print("Whisper model loaded successfully")

fire_calls = []
last_check_time = None
processed_audio_urls = set()
processing_lock = threading.Lock()

FIRE_KEYWORDS = [
    r'grass[\s_-]?fire',
    r'brush[\s_-]?fire', 
    r'wildland[\s_-]?fire',
    r'wild[\s_-]?fire'
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
    return False

def transcribe_audio_with_whisper(audio_url):
    tmp_path = None
    
    try:
        response = requests.get(audio_url, timeout=30)
        response.raise_for_status()
        
        with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as tmp_file:
            tmp_file.write(response.content)
            tmp_path = tmp_file.name
        
        segments, info = whisper_model.transcribe(tmp_path, beam_size=5, language="en")
        
        transcript_parts = []
        for segment in segments:
            transcript_parts.append(segment.text)
        
        transcript = " ".join(transcript_parts).strip()
        
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)
            
        return transcript
        
    except Exception as e:
        print(f"Transcription error for {audio_url}: {e}")
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)
        return None

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
            
    except Exception as e:
        print(f"Error during re-check: {e}")
    finally:
        processing_lock.release()

def scrape_dispatch_calls():
    global fire_calls, last_check_time, processed_audio_urls
    
    # Use lock to prevent concurrent execution
    if not processing_lock.acquire(blocking=False):
        print("Scan already in progress, skipping...")
        return
    
    try:
        new_fire_calls_count = 0
        
        url = "https://call-log-api.edispatches.com/calls/"
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        table = soup.find('table')
        
        if table:
            rows = table.find_all('tr')
            new_calls_to_process = []
            
            # First pass: collect new calls
            for row in rows[:20]:  # Limit to first 20 rows to avoid overload
                cols = row.find_all('td')
                if len(cols) >= 4:
                    audio_tag = cols[0].find('audio')
                    if audio_tag and audio_tag.get('src'):
                        audio_url = audio_tag.get('src')
                        agency = cols[1].text.strip()
                        location = cols[2].text.strip()
                        timestamp = cols[3].text.strip()
                        state = extract_state_from_location(location)
                        
                        if audio_url not in processed_audio_urls:
                            new_calls_to_process.append({
                                'audio_url': audio_url,
                                'agency': agency,
                                'location': location,
                                'state': state,
                                'timestamp': timestamp
                            })
            
            # Second pass: transcribe and filter (limit to 5 at a time)
            for call_info in new_calls_to_process[:5]:
                print(f"Processing new call from {call_info['agency']} at {call_info['location']}")
                
                transcript = transcribe_audio_with_whisper(call_info['audio_url'])
                
                if transcript and is_fire_call_in_transcript(transcript):
                    call_data = {
                        'audio_url': call_info['audio_url'],
                        'agency': call_info['agency'],
                        'location': call_info['location'],
                        'state': call_info['state'],
                        'timestamp': call_info['timestamp'],
                        'transcript': transcript,
                        'first_detected': datetime.utcnow().isoformat() + 'Z',
                        'id': call_info['audio_url']
                    }
                    
                    fire_calls.insert(0, call_data)
                    new_fire_calls_count += 1
                    print(f"🔥 FIRE CALL DETECTED: {call_info['agency']} - {call_info['location']}")
                    print(f"   Transcript: {transcript[:100]}...")
                
                processed_audio_urls.add(call_info['audio_url'])
        
        last_check_time = datetime.utcnow().isoformat() + 'Z'
        print(f"Scan complete. Found {new_fire_calls_count} new fire calls (Total: {len(fire_calls)})")
        
    except Exception as e:
        print(f"Error scraping dispatch calls: {e}")
    finally:
        processing_lock.release()

@app.route('/')
def index():
    response = app.make_response(render_template('index.html'))
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

@app.route('/api/fire-calls')
def get_fire_calls():
    return jsonify({
        'calls': fire_calls,
        'last_check': last_check_time
    })

@app.route('/api/states')
def get_states():
    return jsonify({'states': list(US_STATES.values())})

@app.route('/api/health')
def health():
    return jsonify({
        'status': 'running',
        'last_check': last_check_time,
        'fire_calls_count': len(fire_calls)
    })

scheduler = BackgroundScheduler()
scheduler.add_job(func=scrape_dispatch_calls, trigger="interval", seconds=60)
scheduler.add_job(func=recheck_recent_calls, trigger="interval", seconds=60)
scheduler.start()

# Run initial scan in background thread so app can start
print("Starting initial scan in background...")
threading.Thread(target=scrape_dispatch_calls, daemon=True).start()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
