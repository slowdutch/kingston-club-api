"""
Kingston Schools FA — Spond API Backend
Flask REST API that connects admin dashboard to Spond
"""

from flask import Flask, jsonify, request
from flask_cors import CORS
import asyncio
import copy
import os
import requests
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from spond import spond
from spond._event_template import _EVENT_TEMPLATE

app = Flask(__name__)
CORS(app)

# Load from environment
SPOND_USERNAME = os.getenv('SPOND_USERNAME')
SPOND_PASSWORD = os.getenv('SPOND_PASSWORD')
SPOND_GROUP_ID = os.getenv('SPOND_GROUP_ID')


LONDON = ZoneInfo('Europe/London')


def _utc_stamp(dt):
    """Spond expects UTC ISO timestamps with milliseconds."""
    return dt.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.000Z')


async def create_event(s, heading, start, end, location_name, location_address, description):
    """Create an event with a raw POST to Spond's sponds/ endpoint.

    The spond library (0.x) has no create method; this mirrors its update_event
    payload (_EVENT_TEMPLATE) and adds the owner from the logged-in profile.
    Not in the library, so verify the response on first real use.
    """
    profile = await s.get_profile()
    payload = copy.deepcopy(_EVENT_TEMPLATE)
    payload.update({
        'heading': heading,
        'description': description,
        'startTimestamp': _utc_stamp(start),
        'endTimestamp': _utc_stamp(end),
        'groupId': SPOND_GROUP_ID,
        'visibility': 'INVITEES',
        'location': {'name': location_name, 'address': location_address, 'feature': None,
                     'id': None, 'latitude': None, 'longitude': None},
        'owners': [{'id': profile['id']}],
        'recipients': {'group': {'id': SPOND_GROUP_ID}},
        'name': heading,
        'tasks': {'openTasks': [], 'assignedTasks': []},
    })
    async with s.clientsession.post(f"{s.api_url}sponds/", json=payload, headers=s.auth_headers) as r:
        body = await r.json(content_type=None)
        if not r.ok:
            raise ValueError(f"Spond create failed {r.status}: {body}")
        return body


def run_async(coro):
    """Helper to run async Spond calls in Flask sync context"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@app.route('/api/spond/events', methods=['GET'])
def get_events():
    """Get upcoming events from Spond"""
    async def fetch():
        s = spond.Spond(username=SPOND_USERNAME, password=SPOND_PASSWORD)
        try:
            events = await s.get_events(
                group_id=SPOND_GROUP_ID,
                min_start=datetime.now(timezone.utc) - timedelta(days=1),
                max_events=50
            )
            return events
        finally:
            await s.clientsession.close()

    try:
        events = run_async(fetch())
        return jsonify(events), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/spond/create-training', methods=['POST'])
def create_training():
    """Create training session in Spond"""
    data = request.json
    date_str = data.get('date')
    time_str = data.get('time', '15:00')

    async def create():
        s = spond.Spond(username=SPOND_USERNAME, password=SPOND_PASSWORD)
        try:
            start = datetime.fromisoformat(f"{date_str}T{time_str}:00").replace(tzinfo=LONDON)
            result = await create_event(
                s, heading="U11 Training Session",
                start=start, end=start + timedelta(hours=1),
                location_name="The Tiffin Girls' School",
                location_address="Richmond Road, Kingston upon Thames, KT2 5PL",
                description="Bring: Kit, shin pads, water bottle, any medication.\nArrive 2:50pm for 3:00pm start.",
            )
            return result
        finally:
            await s.clientsession.close()

    try:
        result = run_async(create())
        return jsonify(result), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/spond/create-match', methods=['POST'])
def create_match():
    """Create match event in Spond"""
    data = request.json
    date_str = data.get('date')
    time_str = data.get('time')
    opponent = data.get('opponent')
    home = data.get('home', True)

    async def create():
        s = spond.Spond(username=SPOND_USERNAME, password=SPOND_PASSWORD)
        try:
            start = datetime.fromisoformat(f"{date_str}T{time_str}:00").replace(tzinfo=LONDON)
            result = await create_event(
                s, heading=f"U11 Match vs {opponent}",
                start=start, end=start + timedelta(hours=1, minutes=30),
                location_name="Weir Archer Athletics & Fitness Centre" if home else "Away Venue (TBC)",
                location_address="Kingston Road, Tolworth, Surbiton, KT5 9QB" if home else "",
                description=f"{'HOME' if home else 'AWAY'} match. Full match kit required. Arrive 30 minutes before kick-off.",
            )
            return result
        finally:
            await s.clientsession.close()

    try:
        result = run_async(create())
        return jsonify(result), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/spond/event/<event_id>/attendance', methods=['GET'])
def get_event_attendance(event_id):
    """Get detailed attendance for a specific event"""
    async def fetch():
        s = spond.Spond(username=SPOND_USERNAME, password=SPOND_PASSWORD)
        try:
            event = await s.get_event(event_id)
            return event
        finally:
            await s.clientsession.close()

    try:
        event = run_async(fetch())
        return jsonify(event), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/spond/event/<event_id>/attendance/excel', methods=['GET'])
def export_event_attendance(event_id):
    """Export attendance to Excel"""
    async def fetch():
        s = spond.Spond(username=SPOND_USERNAME, password=SPOND_PASSWORD)
        try:
            xlsx_data = await s.get_event_attendance_xlsx(event_id)
            return xlsx_data
        finally:
            await s.clientsession.close()

    try:
        xlsx_data = run_async(fetch())
        return xlsx_data, 200, {
            'Content-Type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            'Content-Disposition': f'attachment; filename=attendance_{event_id}.xlsx'
        }
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/spond/send-message', methods=['POST'])
def send_message():
    """Send message to Spond group"""
    data = request.json
    message = data.get('message')

    async def send():
        s = spond.Spond(username=SPOND_USERNAME, password=SPOND_PASSWORD)
        try:
            await s.send_message(text=message, group_uid=SPOND_GROUP_ID)
            return {'success': True}
        finally:
            await s.clientsession.close()

    try:
        run_async(send())
        return jsonify({'success': True}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ─── STRIPE PAYMENTS (admin tab: live read from Stripe) ───
STRIPE_API_KEY = os.getenv('STRIPE_API_KEY')
STRIPE_PAYMENT_LINK_ID = os.getenv('STRIPE_PAYMENT_LINK_ID', 'plink_1UXVYtR4Glk7COcQN0kzCcC5')
ADMIN_KEY = os.getenv('ADMIN_KEY')


@app.route('/api/stripe/payments', methods=['GET'])
def stripe_payments():
    """List recent checkout sessions for the kit payment link."""
    if ADMIN_KEY and request.headers.get('X-Admin-Key') != ADMIN_KEY:
        return jsonify({'error': 'unauthorized'}), 401
    if not STRIPE_API_KEY:
        return jsonify({'error': 'STRIPE_API_KEY not configured on server'}), 500
    try:
        r = requests.get(
            'https://api.stripe.com/v1/checkout/sessions',
            params={'payment_link': STRIPE_PAYMENT_LINK_ID, 'limit': 100},
            headers={'Authorization': f'Bearer {STRIPE_API_KEY}'},
            timeout=15)
        r.raise_for_status()
    except requests.RequestException as e:
        return jsonify({'error': f'Stripe request failed: {e}'}), 502
    payments = [{
        'created': s.get('created'),
        'status': s.get('payment_status'),
        'amount': s.get('amount_total'),
        'currency': s.get('currency'),
        'email': (s.get('customer_details') or {}).get('email'),
        'player': s.get('client_reference_id'),
    } for s in r.json().get('data', [])]
    return jsonify({'payments': payments})


if __name__ == '__main__':
    if not all([SPOND_USERNAME, SPOND_PASSWORD, SPOND_GROUP_ID]):
        print("⚠️  Missing environment variables. Set SPOND_USERNAME, SPOND_PASSWORD, and SPOND_GROUP_ID")
        exit(1)

    print("✅ Kingston Schools FA Spond API Server")
    print(f"   Group ID: {SPOND_GROUP_ID}")
    print("   Starting on http://localhost:5000")
    app.run(debug=True, port=5000)
