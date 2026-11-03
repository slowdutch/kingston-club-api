#!/usr/bin/env python3
"""
Kingston District Schools FA — Spond Event Management
Automates match/training event creation and attendance tracking via Spond API
"""

import asyncio
import os
from datetime import datetime, timedelta
from spond import spond

# Config
SPOND_USERNAME = os.getenv('SPOND_USERNAME')
SPOND_PASSWORD = os.getenv('SPOND_PASSWORD')
SPOND_GROUP_ID = os.getenv('SPOND_GROUP_ID')  # Kingston Schools FA U11 group

# Event templates
TRAINING_TEMPLATE = {
    "heading": "U11 Training Session",
    "location": {
        "name": "The Tiffin Girls' School",
        "address": "Richmond Road, Kingston upon Thames, KT2 5PL"
    },
    "duration": 60,  # minutes
    "description": "Bring: Kit, shin pads, water bottle, any medication.\nArrive 2:50pm for 3:00pm start."
}

MATCH_TEMPLATE = {
    "heading": "U11 Match",
    "location": {
        "name": "Weir Archer Athletics & Fitness Centre",
        "address": "Kingston Road, Tolworth, Surbiton, KT5 9QB"
    },
    "duration": 90,  # minutes (including warm-up)
    "description": "Full match kit required. Arrive 30 minutes before kick-off."
}


async def create_training_session(date_str: str, time_str: str = "15:00"):
    """
    Create training event in Spond.

    Args:
        date_str: Date in YYYY-MM-DD format (e.g. "2026-11-15")
        time_str: Time in HH:MM format (default "15:00" for 3pm)
    """
    s = spond.Spond(username=SPOND_USERNAME, password=SPOND_PASSWORD)

    # Parse datetime
    dt = datetime.fromisoformat(f"{date_str}T{time_str}:00")

    event_data = {
        **TRAINING_TEMPLATE,
        "startTimestamp": dt.isoformat(),
        "endTimestamp": (dt + timedelta(minutes=60)).isoformat(),
    }

    try:
        # Create event (method depends on Spond API - check docs)
        result = await s.create_event(
            group_uid=SPOND_GROUP_ID,
            **event_data
        )
        print(f"✅ Training created: {date_str} at {time_str}")
        print(f"   Event ID: {result.get('uid')}")
        return result
    except Exception as e:
        print(f"❌ Failed to create training: {e}")
        raise
    finally:
        await s.clientsession.close()


async def create_match(date_str: str, time_str: str, opponent: str, home: bool = True):
    """
    Create match event in Spond.

    Args:
        date_str: Date in YYYY-MM-DD format
        time_str: Kick-off time in HH:MM format
        opponent: Opponent team name
        home: True for home match, False for away
    """
    s = spond.Spond(username=SPOND_USERNAME, password=SPOND_PASSWORD)

    dt = datetime.fromisoformat(f"{date_str}T{time_str}:00")

    event_data = {
        **MATCH_TEMPLATE,
        "heading": f"U11 Match vs {opponent}",
        "startTimestamp": dt.isoformat(),
        "endTimestamp": (dt + timedelta(minutes=90)).isoformat(),
    }

    if not home:
        event_data["description"] = f"AWAY match. {event_data['description']}\n\nTravel details will be confirmed via Spond chat."
        # Away venue details would be updated here

    try:
        result = await s.create_event(
            group_uid=SPOND_GROUP_ID,
            **event_data
        )
        print(f"✅ Match created: {opponent} on {date_str}")
        print(f"   Event ID: {result.get('uid')}")
        return result
    except Exception as e:
        print(f"❌ Failed to create match: {e}")
        raise
    finally:
        await s.clientsession.close()


async def get_attendance_report(event_id: str):
    """Export attendance report for an event to Excel"""
    s = spond.Spond(username=SPOND_USERNAME, password=SPOND_PASSWORD)

    try:
        xlsx_data = await s.get_event_attendance_xlsx(event_id)
        filename = f"attendance_{event_id}_{datetime.now().strftime('%Y%m%d')}.xlsx"

        with open(filename, 'wb') as f:
            f.write(xlsx_data)

        print(f"✅ Attendance exported: {filename}")
        return filename
    except Exception as e:
        print(f"❌ Failed to export attendance: {e}")
        raise
    finally:
        await s.clientsession.close()


async def send_group_message(message: str):
    """Send message to U11 group chat"""
    s = spond.Spond(username=SPOND_USERNAME, password=SPOND_PASSWORD)

    try:
        await s.send_message(text=message, group_uid=SPOND_GROUP_ID)
        print(f"✅ Message sent to group")
    except Exception as e:
        print(f"❌ Failed to send message: {e}")
        raise
    finally:
        await s.clientsession.close()


async def list_upcoming_events():
    """List all upcoming events for the group"""
    s = spond.Spond(username=SPOND_USERNAME, password=SPOND_PASSWORD)

    try:
        events = await s.get_events(
            group_id=SPOND_GROUP_ID,
            min_start=datetime.now().isoformat(),
            max_events=20
        )

        print(f"\n📅 Upcoming Events ({len(events)}):\n")
        for event in events:
            start = datetime.fromisoformat(event['startTimestamp'])
            print(f"  • {start.strftime('%a %d %b, %H:%M')} — {event['heading']}")
            print(f"    {event['responses']['acceptedCount']} accepted, {event['responses']['declinedCount']} declined")

        return events
    except Exception as e:
        print(f"❌ Failed to fetch events: {e}")
        raise
    finally:
        await s.clientsession.close()


# ─── CLI Entry Points ───

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("""
Usage:
  python spond_manager.py create-training <YYYY-MM-DD> [HH:MM]
  python spond_manager.py create-match <YYYY-MM-DD> <HH:MM> <opponent> [away]
  python spond_manager.py list-events
  python spond_manager.py send-message "<message text>"
  python spond_manager.py attendance <event_id>

Examples:
  python spond_manager.py create-training 2026-11-15
  python spond_manager.py create-match 2026-11-16 10:00 "Sutton Schools" away
  python spond_manager.py list-events
  python spond_manager.py send-message "Training confirmed for Sunday 3pm"
        """)
        sys.exit(1)

    command = sys.argv[1]

    if command == "create-training":
        date = sys.argv[2]
        time = sys.argv[3] if len(sys.argv) > 3 else "15:00"
        asyncio.run(create_training_session(date, time))

    elif command == "create-match":
        date = sys.argv[2]
        time = sys.argv[3]
        opponent = sys.argv[4]
        home = "away" not in sys.argv
        asyncio.run(create_match(date, time, opponent, home))

    elif command == "list-events":
        asyncio.run(list_upcoming_events())

    elif command == "send-message":
        message = sys.argv[2]
        asyncio.run(send_group_message(message))

    elif command == "attendance":
        event_id = sys.argv[2]
        asyncio.run(get_attendance_report(event_id))

    else:
        print(f"❌ Unknown command: {command}")
        sys.exit(1)
