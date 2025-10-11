# Edispatches monitor for Watch Duty

## Overview
A web-based alert application that monitors fire department dispatch calls from edispatches.com. Built for watch duty purposes to track fire department calls across all US states.

## Project Purpose
This application helps monitor emergency fire dispatch calls in real-time, with customizable state filtering and multiple alert mechanisms including visual, audio, and desktop notifications.

## Current State
- Fully functional fire call monitoring system
- Web-based application accessible via browser
- Running on Flask backend with automated scraping every 60 seconds
- Frontend with real-time updates every 5 seconds

## Features
- **Automated Web Scraping**: Checks call-log-api.edispatches.com/calls/ every 60 seconds for new dispatch calls
- **Speech-to-Text Transcription**: Uses faster-whisper AI to transcribe dispatch audio and detect fire keywords
  - Detects: grass fire, brush fire, wildland fire, wildfire (all variations)
  - Filters out non-fire calls (EMS, medical, etc.) based on actual audio content
- **Audio Re-checking**: Automatically re-checks recent calls (last 10 minutes) every minute to detect if full audio becomes available on edispatches.com
- **Smart Call Retention**: Calls stay visible for minimum 1 hour, last 5 calls kept indefinitely
- **Manual Dismissal**: X button in upper right corner of each call for manual removal
- **State Filtering**: Checkbox filter for all 50 US states with Select All/Deselect All options
- **Collapsible State Filter**: Minimize/expand state filter to maximize fire calls display area (preference saved)
- **Scrollable Call List**: View multiple active fire calls with smooth scrolling (600px max-height)
- **Visual Alerts**: Red blinking border animation when new fire calls are detected (5 second duration)
- **Audio Alerts**: Web Audio API-generated beep sound (800Hz, 0.5 second duration)
- **Desktop Notifications**: Browser-based notifications with call details
- **Audio Playback**: Embedded audio player for each call to listen to dispatch audio
- **Transcript Display**: Shows full AI-transcribed text from each dispatch call
- **Favicon Blinking**: Red blinking favicon when window is minimized and alerts are active
- **Persistent Preferences**: State filter selections and collapse state saved to browser localStorage

## Technology Stack

### Backend
- Python 3.11
- Flask (web framework)
- Flask-CORS (cross-origin support)
- Beautiful Soup 4 (HTML parsing for edispatches API)
- Requests (HTTP requests)
- APScheduler (background scheduling - runs scraper every 60 seconds)

### Frontend
- HTML5
- CSS3 (with modern animations and gradients)
- Vanilla JavaScript
- Web Audio API (alert sounds)
- Notification API (desktop alerts)
- LocalStorage API (persistent settings)

## Project Structure
```
.
├── app.py                      # Flask backend server
├── templates/
│   └── index.html             # Main HTML template
├── static/
│   ├── style.css              # Styles and animations
│   └── app.js                 # Frontend JavaScript logic
├── generate_alert_sound.py    # Sound generation script (unused - using Web Audio API)
└── replit.md                  # Project documentation
```

## How to Use

1. **Start the Application**: The app runs automatically via the configured workflow on port 5000

2. **Configure State Filter**: 
   - Use "Select All" or "Deselect All" buttons for quick selection
   - Or manually check/uncheck individual states
   - Selections are automatically saved

3. **Monitor Fire Calls**:
   - The app checks for new calls every 60 seconds
   - Frontend updates every 5 seconds
   - New fire calls trigger all alert mechanisms

4. **Alert System**:
   - Screen border blinks red for 5 seconds when new calls appear
   - Audio beep plays for new calls
   - Desktop notifications show call details
   - When minimized, favicon blinks red until window is restored

## Recent Changes (October 11, 2025)
- Initial project setup with Python environment and dependencies
- Created Flask backend with web scraping functionality from call-log-api.edispatches.com
- **Updated to Whisper transcription**: Uses faster-whisper (self-hosted) for accurate speech-to-text
- Implemented fire keyword detection from audio transcripts (grass fire, brush fire, wildland fire, wildfire)
- Built responsive frontend UI with state filtering for all 50 US states
- Added visual alert system with red blinking border (CSS animations)
- Implemented audio alerts using Web Audio API (800Hz beep sound)
- Added desktop notifications and favicon blinking for minimized state
- **Added audio player**: Users can listen to dispatch audio directly in the app
- **Added transcript display**: Shows detected speech-to-text transcription for each call
- Optimized processing: Background threading, processes max 5 calls at a time
- Uses faster-whisper library (4x faster than original Whisper, runs on CPU)
- **Call retention system**: Calls stay for minimum 1 hour, last 5 calls kept indefinitely
- **Manual dismissal**: X button in upper right corner of each call to dismiss manually
- **Scrollable calls list**: Can scroll through multiple active fire calls (600px max-height)
- Configured workflow to run on port 5000

## API Endpoints

### `GET /`
Returns the main application HTML page

### `GET /api/fire-calls`
Returns active fire department calls and last check timestamp
```json
{
  "calls": [
    {
      "audio_url": "https://audio.edispatches.com/play/...",
      "agency": "Richmond_Fire",
      "location": "Madison, KY",
      "state": "Kentucky",
      "timestamp": "2025-10-10 16:27:46",
      "id": "https://audio.edispatches.com/play/..."
    }
  ],
  "last_check": "2025-10-10T19:31:52.123456Z"
}
```

### `GET /api/states`
Returns list of all 50 US states

### `GET /api/health`
Returns application health status
```json
{
  "status": "running",
  "last_check": "2025-10-10T19:31:52.123456Z",
  "fire_calls_count": 7
}
```

## Configuration

### Scraping Interval
Currently set to 60 seconds (configurable in `app.py` scheduler section)

### Frontend Update Interval
Currently set to 5 seconds (configurable in `static/app.js` line 262)

### Fire Agency Detection Patterns
Defined in `app.py` as FIRE_AGENCY_KEYWORDS, using regex patterns for flexible matching:
- `\bfire\b` - Matches "fire" as a whole word
- `\bfd\b` - Matches "FD" (Fire Department)
- `\bvfd\b` - Matches "VFD" (Volunteer Fire Department)
- `fire[-_\s]?dept` - Matches fire department variations
- `fire[-_\s]?department` - Matches full "fire department"
- `fire[-_\s]?rescue` - Matches fire rescue units

## User Preferences
- State filter preferences saved in browser localStorage
- Automatically restored on page reload
- No server-side storage required

## Future Enhancement Ideas
- Call history log with searchable archive
- Custom alert sounds with volume control
- Snooze functionality for breaks
- Export feature for daily/weekly reports
- Map visualization showing fire locations
- Email/SMS alert integration
- Historical data analysis and trends

## Notes for Development
- Application uses Flask development server (suitable for local/personal use)
- Web scraping depends on call-log-api.edispatches.com maintaining current HTML structure
- **Detection method**: Filters by agency/department names instead of audio transcription (instant and reliable)
- Audio alerts require user interaction first (browser autoplay policy)
- Desktop notifications require user permission grant
- Favicon blinking stops when window is restored to foreground
- No external API costs - completely self-contained solution
