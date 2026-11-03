# Spond Backend API — Quick Start

## Install

```bash
cd Admin/Spond
pip install flask flask-cors spond
```

## Configure

Create `.env`:
```bash
SPOND_USERNAME=your@email.com
SPOND_PASSWORD=yourpassword
SPOND_GROUP_ID=your_group_id_from_spond
```

## Run

```bash
python api_server.py
```

Server runs on `http://localhost:5000`

## Deploy Website

Update website API base URL in `Website/kingston-schools-fa/src/main.js`:

```javascript
const SPOND_API_BASE = 'http://localhost:5000'  // Local dev
// const SPOND_API_BASE = 'https://your-domain.com'  // Production
```

Then in `loadEventsData()`, `createTrainingEvent()`, etc., replace `/api/spond/` with `${SPOND_API_BASE}/api/spond/`

## Production Deployment

Deploy Flask API to:
- **Heroku**: `heroku create kingston-spond-api && git push heroku main`
- **Railway**: Connect GitHub repo, set env vars
- **DigitalOcean App Platform**: Python app, set env vars

Set environment variables in hosting platform dashboard.

Enable CORS for your domain in `api_server.py`:
```python
CORS(app, origins=['https://kingstonschoolsfa.co.uk'])
```

## Admin Dashboard Features

**4 Tabs:**

1. **Trial Nominations** — Original nominations table (unchanged)

2. **Events & Attendance** — NEW
   - Lists all upcoming Spond events
   - Shows accepted/declined/unanswered counts per event
   - Create training: `+ Create Training` button
   - Create match: `+ Create Match` button
   - View attendance details per event
   - Export Excel attendance report per event

3. **Kit Orders** — NEW
   - All kit orders from `#kit-order` page
   - Shows sizes (shirt/shorts/socks/tracksuit), GK flag, payment status
   - Total revenue calculation
   - Export to CSV

4. **Consent Forms** — NEW
   - All parent consent forms
   - Medical conditions, emergency contacts, photo consent
   - Export to CSV

## API Endpoints

```
GET    /api/spond/events                        # List upcoming events
POST   /api/spond/create-training               # Create training session
POST   /api/spond/create-match                  # Create match event
GET    /api/spond/event/:id/attendance          # Get event details
GET    /api/spond/event/:id/attendance/excel    # Download Excel
POST   /api/spond/send-message                  # Send group message
```

## Testing

```bash
# List events
curl http://localhost:5000/api/spond/events

# Create training
curl -X POST http://localhost:5000/api/spond/create-training \
  -H "Content-Type: application/json" \
  -d '{"date":"2026-11-15","time":"15:00"}'

# Create match
curl -X POST http://localhost:5000/api/spond/create-match \
  -H "Content-Type: application/json" \
  -d '{"date":"2026-11-16","time":"10:00","opponent":"Sutton Schools","home":true}'
```

## Security

- Never commit `.env` to git
- Use HTTPS in production
- Restrict CORS to your domain only
- Consider adding API key authentication for production
