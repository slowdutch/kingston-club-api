"""
Kingston Schools FA — Spond API Backend
Flask REST API that connects admin dashboard to Spond
"""

from flask import Flask, jsonify, request
from flask_cors import CORS
import asyncio
import copy
import hashlib
import hmac
import json
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


def _member_names(group):
    """Map member id -> display name (Spond API events only carry member IDs)."""
    out = {}
    for m in (group or {}).get('members', []):
        name = ' '.join(filter(None, [m.get('firstName'), m.get('lastName')])).strip()
        out[m.get('id')] = name or 'Unknown'
    return out


def _reshape_event(e, members):
    """Frontend-friendly event: counts + participant names resolved from the group."""
    r = e.get('responses') or {}

    def plist(key):
        return [{'id': i, 'name': members.get(i, 'Unknown')} for i in (r.get(key) or [])]

    acc, dec, un = plist('acceptedIds'), plist('declinedIds'), plist('unansweredIds')
    loc = e.get('location')
    return {
        'uid': e.get('id'),
        'heading': e.get('heading'),
        'startTimestamp': e.get('startTimestamp'),
        'location': {'name': loc.get('name') if isinstance(loc, dict) else loc},
        'responses': {
            'acceptedCount': len(acc), 'declinedCount': len(dec), 'unansweredCount': len(un),
            'acceptedParticipants': acc, 'declinedParticipants': dec, 'unansweredParticipants': un,
        },
    }


@app.route('/api/spond/events', methods=['GET'])
def get_events():
    """Get upcoming events from Spond, enriched with response counts and names"""
    async def fetch():
        s = spond.Spond(username=SPOND_USERNAME, password=SPOND_PASSWORD)
        try:
            events = await s.get_events(
                group_id=SPOND_GROUP_ID,
                min_start=datetime.now(timezone.utc) - timedelta(days=1),
                max_events=50
            )
            group = await s.get_group(SPOND_GROUP_ID)
            return events, group
        finally:
            await s.clientsession.close()

    try:
        events, group = run_async(fetch())
        members = _member_names(group)
        reshaped = [_reshape_event(e, members) for e in events]
        reshaped.sort(key=lambda e: e.get('startTimestamp') or '')
        return jsonify(reshaped), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/spond/members', methods=['GET'])
def get_members():
    """Group members with display names — lets the console reconcile the
    Spond group against the squad roster (who has joined, who hasn't)."""
    async def fetch():
        s = spond.Spond(username=SPOND_USERNAME, password=SPOND_PASSWORD)
        try:
            return await s.get_group(SPOND_GROUP_ID)
        finally:
            await s.clientsession.close()

    try:
        group = run_async(fetch())
        out = []
        for m in (group or {}).get('members', []):
            name = ' '.join(filter(None, [m.get('firstName'), m.get('lastName')])).strip() or 'Unknown'
            out.append({'id': m.get('id'), 'name': name})
        out.sort(key=lambda m: m['name'])
        return jsonify(out), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/spond/create-training', methods=['POST'])
def create_training():
    """Create training session in Spond"""
    data = request.json
    date_str = data.get('date')
    time_str = data.get('time', '15:30')

    async def create():
        s = spond.Spond(username=SPOND_USERNAME, password=SPOND_PASSWORD)
        try:
            start = datetime.fromisoformat(f"{date_str}T{time_str}:00").replace(tzinfo=LONDON)
            result = await create_event(
                s, heading="U11 Training Session",
                start=start, end=start + timedelta(hours=1),
                location_name="The Tiffin Girls' School",
                location_address="Richmond Road, Kingston upon Thames, KT2 5PL",
                description="Bring: Training kit, water bottle, any medication.\nArrive 3:20pm for 3:30pm start.\nShin pads are only needed for matches.",
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
    tbd_time = not time_str

    async def create():
        s = spond.Spond(username=SPOND_USERNAME, password=SPOND_PASSWORD)
        try:
            # Spond requires a start time; without one we park matches at
            # noon and label them clearly until the league confirms.
            start = datetime.fromisoformat(f"{date_str}T{time_str or '12:00'}:00").replace(tzinfo=LONDON)
            result = await create_event(
                s, heading=f"U11 Match vs {opponent}{' (KO TBC)' if tbd_time else ''}",
                start=start, end=start + timedelta(hours=1, minutes=30),
                location_name="Weir Archer Athletics & Fitness Centre" if home else "Away Venue (TBC)",
                location_address="Kingston Road, Tolworth, Surbiton, KT5 9QB" if home else "",
                description=f"{'HOME' if home else 'AWAY'} match. Kick-off time to be confirmed by the league. Full match kit and shin pads required. Meet 30 minutes before kick-off.",
            )
            return result
        finally:
            await s.clientsession.close()

    try:
        result = run_async(create())
        return jsonify(result), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/spond/update-event', methods=['POST'])
@app.route('/api/spond/update-match', methods=['POST'])
def update_event_route():
    """Update an existing event (date, time, home/away, opponent, kind).

    The league keeps moving dates, so provisional events need to be editable
    without deleting and recreating them (which would drop replies)."""
    data = request.json
    uid = data.get('uid')
    if not uid:
        return jsonify({'error': 'uid is required'}), 400
    kind = data.get('kind', 'match')
    tbd_time = kind == 'match' and not data.get('time')

    async def update():
        s = spond.Spond(username=SPOND_USERNAME, password=SPOND_PASSWORD)
        try:
            event = await s.get_event(uid)
            if not event:
                raise ValueError('Event not found')
            if kind == 'training':
                start = datetime.fromisoformat(f"{data['date']}T{data.get('time', '15:30')}:00").replace(tzinfo=LONDON)
            else:
                # Spond requires a start time; without one we park matches at
                # noon and label them clearly until the league confirms.
                start = datetime.fromisoformat(f"{data['date']}T{data.get('time', '12:00')}:00").replace(tzinfo=LONDON)
            if kind == 'training':
                end = start + timedelta(hours=1)
                heading = 'U11 Training Session'
                location_name, location_address = "The Tiffin Girls' School", "Richmond Road, Kingston upon Thames, KT2 5PL"
                description = "Bring: Training kit, water bottle, any medication.\nArrive 3:20pm for 3:30pm start.\nShin pads are only needed for matches."
            else:
                end = start + timedelta(hours=1, minutes=30)
                opponent = data.get('opponent') or (event.get('heading', '').replace('U11 Match vs ', '').replace(' (KO TBC)', '') or 'Opponent')
                home = data.get('home', True)
                heading = f"U11 Match vs {opponent}{' (KO TBC)' if tbd_time else ''}"
                location_name = "Weir Archer Athletics & Fitness Centre" if home else "Away Venue (TBC)"
                location_address = "Kingston Road, Tolworth, Surbiton, KT5 9QB" if home else ""
                description = f"{'HOME' if home else 'AWAY'} match. Kick-off time to be confirmed by the league. Full match kit and shin pads required. Meet 30 minutes before kick-off."
            updates = {
                'heading': heading,
                'name': heading,
                'startTimestamp': _utc_stamp(start),
                'endTimestamp': _utc_stamp(end),
                'location': {'name': location_name, 'address': location_address,
                             'feature': None, 'id': None, 'latitude': None, 'longitude': None},
                'description': description,
            }
            return await s.update_event(uid, updates)
        finally:
            await s.clientsession.close()

    try:
        result = run_async(update())
        return jsonify({'updated': uid, 'result': result}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/spond/event/<event_id>/attendance', methods=['GET'])
def get_event_attendance(event_id):
    """Get detailed attendance for a specific event, enriched with names"""
    async def fetch():
        s = spond.Spond(username=SPOND_USERNAME, password=SPOND_PASSWORD)
        try:
            event = await s.get_event(event_id)
            group = await s.get_group(SPOND_GROUP_ID)
            return event, group
        finally:
            await s.clientsession.close()

    try:
        event, group = run_async(fetch())
        return jsonify(_reshape_event(event, _member_names(group))), 200
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

# Supabase service access (webhook marks kit orders paid)
SUPABASE_URL = os.getenv('SUPABASE_URL', 'https://bprieehoiiwliiencitr.supabase.co')
SUPABASE_SERVICE_KEY = os.getenv('SUPABASE_SERVICE_KEY')


@app.route('/api/stripe/webhook', methods=['POST'])
def stripe_webhook():
    """checkout.session.completed → mark the latest pending kit order for that email as paid."""
    secret = os.getenv('STRIPE_WEBHOOK_SECRET')
    if not secret:
        return jsonify({'error': 'STRIPE_WEBHOOK_SECRET not set'}), 500
    sig = request.headers.get('Stripe-Signature', '')
    try:
        parts = dict(p.split('=', 1) for p in sig.split(',') if '=' in p)
        t, v1 = parts['t'], parts['v1']
    except (KeyError, ValueError):
        return jsonify({'error': 'bad signature header'}), 400
    payload = request.get_data()
    expected = hmac.new(secret.encode(), f'{t}.'.encode() + payload, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, v1):
        return jsonify({'error': 'signature mismatch'}), 400

    event = json.loads(payload)
    if event.get('type') != 'checkout.session.completed':
        return jsonify({'received': True})
    s = event.get('data', {}).get('object', {})
    if s.get('payment_link') != STRIPE_PAYMENT_LINK_ID or not SUPABASE_SERVICE_KEY:
        return jsonify({'received': True})

    email = ((s.get('customer_details') or {}).get('email')) or s.get('customer_email') or ''
    if not email:
        return jsonify({'received': True, 'note': 'no email on session'}), 200

    hdrs = {'apikey': SUPABASE_SERVICE_KEY, 'Authorization': f'Bearer {SUPABASE_SERVICE_KEY}'}
    q = requests.get(f'{SUPABASE_URL}/rest/v1/kit_orders',
                     params={'parent_email': f'eq.{email}', 'status': 'eq.pending_payment',
                             'select': 'id', 'order': 'created_at.desc', 'limit': 1},
                     headers=hdrs, timeout=15)
    rows = q.json() if q.status_code == 200 else []
    if not rows:
        return jsonify({'received': True, 'note': 'no pending order matched'}), 200
    requests.patch(f'{SUPABASE_URL}/rest/v1/kit_orders',
                   params={'id': f'eq.{rows[0]["id"]}'},
                   headers={**hdrs, 'Content-Type': 'application/json', 'Prefer': 'return=minimal'},
                   data=json.dumps({'status': 'paid'}), timeout=15)
    return jsonify({'received': True, 'paid_order': rows[0]['id']}), 200


@app.route('/api/stripe/payments', methods=['GET'])
def stripe_payments():
    """List kit checkout sessions and monthly-fee subscription invoices."""
    if ADMIN_KEY and request.headers.get('X-Admin-Key') != ADMIN_KEY:
        return jsonify({'error': 'unauthorized'}), 401
    if not STRIPE_API_KEY:
        return jsonify({'error': 'STRIPE_API_KEY not configured on server'}), 500
    auth = {'Authorization': f'Bearer {STRIPE_API_KEY}'}

    try:
        r = requests.get(
            'https://api.stripe.com/v1/checkout/sessions',
            params={'payment_link': STRIPE_PAYMENT_LINK_ID, 'limit': 100},
            headers=auth, timeout=15)
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

    fees = []
    try:
        r = requests.get(
            'https://api.stripe.com/v1/invoices',
            params={'limit': 100, 'status': 'paid', 'expand[]': ['data.customer']},
            headers=auth, timeout=15)
        r.raise_for_status()
        for inv in r.json().get('data', []):
            lines = inv.get('lines', {}).get('data', [])
            desc = (lines[0].get('description') if lines else '') or ''
            if 'training' not in desc.lower() and 'subscription' not in (inv.get('billing_reason') or ''):
                continue
            cust = inv.get('customer') or {}
            fees.append({
                'created': inv.get('created'),
                'status': inv.get('status'),
                'amount': inv.get('amount_paid'),
                'currency': inv.get('currency'),
                'email': cust.get('email') if isinstance(cust, dict) else None,
                'description': desc,
            })
    except requests.RequestException:
        pass  # fees list is best-effort; kit payments still render

    return jsonify({'payments': payments, 'fees': fees})


if __name__ == '__main__':
    if not all([SPOND_USERNAME, SPOND_PASSWORD, SPOND_GROUP_ID]):
        print("⚠️  Missing environment variables. Set SPOND_USERNAME, SPOND_PASSWORD, and SPOND_GROUP_ID")
        exit(1)

    print("✅ Kingston Schools FA Spond API Server")
    print(f"   Group ID: {SPOND_GROUP_ID}")
    print("   Starting on http://localhost:5000")
    app.run(debug=True, port=5000)
