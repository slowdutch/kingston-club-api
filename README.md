# Spond Integration Setup Guide
## Kingston District Schools FA — U11 Squad Management

Automates event creation (training/matches), attendance tracking, and group messaging via Spond API.

---

## 1. Install Dependencies

```bash
pip install spond
```

Requirements: Python 3.11+, aiohttp 3.13.0+

---

## 2. Set Environment Variables

Create `.env` file in `Admin/Spond/`:

```bash
SPOND_USERNAME=your_email@example.com
SPOND_PASSWORD=your_spond_password
SPOND_GROUP_ID=your_u11_group_id
```

**Finding your Group ID:**
1. Log into Spond web/app
2. Navigate to your U11 Kingston Schools FA group
3. Group ID is in the URL: `spond.com/groups/[GROUP_ID]`

---

## 3. Usage Examples

### Create Training Session

```bash
# Sunday 15 November 2026, 3pm (default)
python spond_manager.py create-training 2026-11-15

# Custom time
python spond_manager.py create-training 2026-11-22 15:00
```

**Auto-populates:**
- Venue: The Tiffin Girls' School, Richmond Road, KT2 5PL
- Duration: 60 minutes
- Instructions: "Bring kit, shin pads, water. Arrive 2:50pm."

---

### Create Match Event

```bash
# Home match
python spond_manager.py create-match 2026-11-16 10:00 "Sutton Schools"

# Away match (adds travel notice)
python spond_manager.py create-match 2026-11-23 14:00 "Croydon District" away
```

**Auto-populates:**
- Home venue: Weir Archer, Kingston Road, Tolworth KT5 9QB
- Duration: 90 minutes (inc. warm-up)
- Instructions: "Full match kit. Arrive 30 min before kick-off."

---

### List Upcoming Events

```bash
python spond_manager.py list-events
```

Shows next 20 events with acceptance/decline counts.

---

### Send Group Message

```bash
python spond_manager.py send-message "Training confirmed for Sunday 3pm. Please confirm attendance in Spond."
```

---

### Export Attendance Report

```bash
python spond_manager.py attendance <event_id>
```

Downloads Excel attendance sheet: `attendance_[event_id]_[date].xlsx`

---

## 4. Monthly Event Batch Creation

Create entire month schedule at once:

```python
import asyncio
from spond_manager import create_training_session, create_match

async def november_schedule():
    # Training: Sundays 15th, 29th
    await create_training_session("2026-11-15")
    await create_training_session("2026-11-29")
    
    # Matches: Saturdays 16th, 30th
    await create_match("2026-11-16", "10:00", "Sutton Schools", home=True)
    await create_match("2026-11-30", "14:00", "Croydon District", home=False)

asyncio.run(november_schedule())
```

---

## 5. Integration with Website

Sync Spond events → website calendar display:

```python
async def sync_to_website():
    from spond_manager import list_upcoming_events
    import json
    
    events = await list_upcoming_events()
    
    # Export to JSON for website
    calendar_data = [{
        "date": e["startTimestamp"],
        "title": e["heading"],
        "venue": e["location"]["name"],
        "accepted": e["responses"]["acceptedCount"]
    } for e in events]
    
    with open("../../Website/kingston-schools-fa/public/calendar.json", "w") as f:
        json.dump(calendar_data, f, indent=2)
```

---

## 6. Automated Reminders

Set up cron job for 48h before events:

```bash
# crontab entry (runs daily at 9am)
0 9 * * * cd /path/to/Admin/Spond && python reminder_bot.py
```

`reminder_bot.py`:
```python
import asyncio
from datetime import datetime, timedelta
from spond_manager import list_upcoming_events, send_group_message

async def send_reminders():
    events = await list_upcoming_events()
    now = datetime.now()
    
    for event in events:
        start = datetime.fromisoformat(event['startTimestamp'])
        hours_until = (start - now).total_seconds() / 3600
        
        # 48h reminder
        if 47 < hours_until < 49:
            await send_group_message(
                f"⚽ Reminder: {event['heading']} in 48 hours!\n"
                f"📅 {start.strftime('%A %d %B, %H:%M')}\n"
                f"📍 {event['location']['name']}\n\n"
                f"Please confirm your attendance in Spond."
            )

asyncio.run(send_reminders())
```

---

## 7. API Limitations & Notes

- **Rate limiting**: Spond may throttle rapid API calls. Add delays between bulk operations.
- **Event editing**: To update event, delete and recreate (or use `update_event` if available).
- **Authentication**: Credentials stored in `.env` — **never commit to git**.
- **Group permissions**: Account must be group admin/organizer to create events.

---

## 8. Security

Add to `.gitignore`:
```
.env
*.xlsx
attendance_*.xlsx
```

Store credentials in environment variables or secure vault (not in code).

---

## Next Steps

1. Install: `pip install spond`
2. Get group ID from Spond web
3. Set `.env` variables
4. Test: `python spond_manager.py list-events`
5. Create first training: `python spond_manager.py create-training 2026-11-15`
6. Invite parents to Spond group (via Spond app/web)
7. Set up monthly payment in Spond group settings (£28/month)

Official API docs: https://olen.github.io/Spond/
