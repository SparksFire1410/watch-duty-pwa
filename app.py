import re
from flask import Flask, jsonify, request
from flask_cors import CORS
from bs4 import BeautifulSoup
import requests
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime
import json

app = Flask(__name__)
CORS(app)

fire_calls = []
last_check_time = None
all_calls_cache = []

FIRE_KEYWORDS = [
    r'grass[\s_-]?fire',
    r'brush[\s_-]?fire', 
    r'wildland[\s_-]?fire',
    r'wild[\s_-]?fire'
]

US_STATES = [
    "Alabama", "Alaska", "Arizona", "Arkansas", "California", "Colorado",
    "Connecticut", "Delaware", "Florida", "Georgia", "Hawaii", "Idaho",
    "Illinois", "Indiana", "Iowa", "Kansas", "Kentucky", "Louisiana",
    "Maine", "Maryland", "Massachusetts", "Michigan", "Minnesota",
    "Mississippi", "Missouri", "Montana", "Nebraska", "Nevada",
    "New Hampshire", "New Jersey", "New Mexico", "New York",
    "North Carolina", "North Dakota", "Ohio", "Oklahoma", "Oregon",
    "Pennsylvania", "Rhode Island", "South Carolina", "South Dakota",
    "Tennessee", "Texas", "Utah", "Vermont", "Virginia", "Washington",
    "West Virginia", "Wisconsin", "Wyoming"
]

def is_fire_call(incident_type):
    if not incident_type:
        return False
    
    incident_lower = incident_type.lower()
    for pattern in FIRE_KEYWORDS:
        if re.search(pattern, incident_lower):
            return True
    return False

def scrape_dispatch_calls():
    global fire_calls, last_check_time, all_calls_cache
    
    try:
        url = "https://www.edispatches.com/call-log/"
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        new_calls = []
        table = soup.find('table')
        
        if table:
            rows = table.find_all('tr')[1:]
            
            for row in rows:
                cols = row.find_all('td')
                if len(cols) >= 4:
                    timestamp = cols[0].text.strip()
                    location = cols[1].text.strip()
                    incident_type = cols[2].text.strip()
                    state = cols[3].text.strip() if len(cols) > 3 else "Unknown"
                    
                    call_data = {
                        'timestamp': timestamp,
                        'location': location,
                        'incident_type': incident_type,
                        'state': state,
                        'id': f"{timestamp}_{location}_{incident_type}"
                    }
                    
                    new_calls.append(call_data)
                    
                    if is_fire_call(incident_type):
                        if call_data['id'] not in [c['id'] for c in fire_calls]:
                            fire_calls.insert(0, call_data)
        
        all_calls_cache = new_calls
        last_check_time = datetime.now().isoformat()
        
        print(f"Scraped {len(new_calls)} calls, {len([c for c in new_calls if is_fire_call(c['incident_type'])])} fire calls")
        
    except Exception as e:
        print(f"Error scraping dispatch calls: {e}")

@app.route('/api/fire-calls')
def get_fire_calls():
    return jsonify({
        'calls': fire_calls,
        'last_check': last_check_time
    })

@app.route('/api/states')
def get_states():
    return jsonify({'states': US_STATES})

@app.route('/api/mark-seen', methods=['POST'])
def mark_seen():
    data = request.json
    call_id = data.get('call_id')
    
    for call in fire_calls:
        if call['id'] == call_id:
            call['seen'] = True
    
    return jsonify({'success': True})

@app.route('/api/clear-old-calls', methods=['POST'])
def clear_old_calls():
    global fire_calls
    fire_calls = [c for c in fire_calls if not c.get('seen', False)]
    return jsonify({'success': True})

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

scrape_dispatch_calls()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
