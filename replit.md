# Edispatches monitor for Watch Duty

## Overview
A Windows desktop alert application that monitors fire dispatch calls from edispatches.com. Built for watch duty purposes to track grass fires, brush fires, wildland fires, and wildfires across all US states.

## Project Purpose
This application helps monitor emergency fire dispatch calls in real-time, with customizable state filtering and multiple alert mechanisms including visual, audio, and desktop notifications.

## Current State
- Fully functional fire call monitoring system
- Web-based application accessible via browser
- Running on Flask backend with automated scraping every 60 seconds
- Frontend with real-time updates every 5 seconds

## Features
- **Automated Web Scraping**: Checks edispatches.com/call-log/ every 60 seconds for new dispatch calls
- **Fire Type Detection**: Case-insensitive matching for:
  - Grass Fire (all variations: GrassFire, Grass_Fire, etc.)
  - Brush Fire (all variations: Brushfire, Brush_Fire, etc.)
  - Wildland Fire (all variations: WildlandFire, Wildland_Fire, etc.)
  - Wildfire/Wild Fire (all variations)
- **State Filtering**: Checkbox filter for all 50 US states with Select All/Deselect All options
- **Visual Alerts**: Red blinking border animation when new fire calls are detected (5 second duration)
- **Audio Alerts**: Web Audio API-generated beep sound (800Hz, 0.5 second duration)
- **Desktop Notifications**: Browser-based notifications with call details
- **Favicon Blinking**: Red blinking favicon when window is minimized and alerts are active
- **Persistent Preferences**: State filter selections saved to browser localStorage

## Technology Stack

### Backend
- Python 3.11
- Flask (web framework)
- Flask-CORS (cross-origin support)
- Beautiful Soup 4 (HTML parsing)
- Requests (HTTP requests)
- APScheduler (background scheduling)

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

## Recent Changes (October 10, 2025)
- Initial project setup with Python environment and dependencies
- Created Flask backend with web scraping functionality
- Implemented fire call detection with regex patterns
- Built responsive frontend UI with state filtering
- Added visual alert system with CSS animations
- Implemented audio alerts using Web Audio API
- Added desktop notifications and favicon blinking for minimized state
- Configured workflow to run on port 5000

## API Endpoints

### `GET /`
Returns the main application HTML page

### `GET /api/fire-calls`
Returns active fire calls and last check timestamp
```json
{
  "calls": [...],
  "last_check": "2025-10-10T19:31:52.123456"
}
```

### `GET /api/states`
Returns list of all 50 US states

### `POST /api/mark-seen`
Marks a call as seen (for future tracking features)

### `POST /api/clear-old-calls`
Removes calls marked as seen

### `GET /api/health`
Returns application health status

## Configuration

### Scraping Interval
Currently set to 60 seconds (configurable in `app.py` line 130)

### Frontend Update Interval
Currently set to 5 seconds (configurable in `static/app.js` line 259)

### Fire Type Patterns
Defined in `app.py` lines 17-22, using regex patterns for flexible matching

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
- Web scraping depends on edispatches.com maintaining current HTML structure
- Audio requires user interaction first (browser autoplay policy)
- Desktop notifications require user permission grant
- Favicon blinking stops when window is restored to foreground
