import re
from flask import Flask, jsonify, render_template
from flask_cors import CORS
from bs4 import BeautifulSoup
import requests
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime

app = Flask(__name__)
CORS(app)

fire_calls = []
last_check_time = None
processed_audio_urls = set()

FIRE_AGENCY_KEYWORDS = [
    r'\bfire\b',
    r'\bfd\b',
    r'\bvfd\b',
    r'fire[-_\s]?dept',
    r'fire[-_\s]?department',
    r'fire[-_\s]?rescue'
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

def is_fire_agency(agency_name):
    if not agency_name:
        return False
    
    agency_lower = agency_name.lower()
    for pattern in FIRE_AGENCY_KEYWORDS:
        if re.search(pattern, agency_lower):
            return True
    return False

def scrape_dispatch_calls():
    global fire_calls, last_check_time, processed_audio_urls
    
    new_fire_calls_count = 0
    
    try:
        url = "https://call-log-api.edispatches.com/calls/"
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        table = soup.find('table')
        
        if table:
            rows = table.find_all('tr')
            
            for row in rows:
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
                            if is_fire_agency(agency):
                                call_data = {
                                    'audio_url': audio_url,
                                    'agency': agency,
                                    'location': location,
                                    'state': state,
                                    'timestamp': timestamp,
                                    'id': audio_url
                                }
                                
                                fire_calls.insert(0, call_data)
                                new_fire_calls_count += 1
                                print(f"🔥 FIRE CALL: {agency} - {location}")
                            
                            processed_audio_urls.add(audio_url)
        
        last_check_time = datetime.utcnow().isoformat() + 'Z'
        print(f"Scan complete. Found {new_fire_calls_count} new fire calls (Total: {len(fire_calls)})")
        
    except Exception as e:
        print(f"Error scraping dispatch calls: {e}")

@app.route('/')
def index():
    return render_template('index.html')

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
scheduler.start()

print("Starting initial scan...")
scrape_dispatch_calls()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
