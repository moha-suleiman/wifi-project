from flask import Flask, request, jsonify
import uuid
import MySQLdb
from mpesa_connect import App, STKPush
from dotenv import load_dotenv
import os

# ✅ Load environment variables from .env
load_dotenv()

# 🔧 Initialize Flask app
app = Flask(__name__)

# ✅ MySQL DB connection - update as needed
db = MySQLdb.connect(
    host='localhost',
    user='radius',               # ✅ Change if different
    passwd='radiuspass',         # ✅ Change if different
    db='radius',
    port=3306
)

# ✅ M-PESA App Setup
app_mp = App(
    consumer_key=os.getenv("MPESA_CONSUMER_KEY"),  # ✅ From .env
    consumer_secret=os.getenv("MPESA_CONSUMER_SECRET"),
    short_code='174379',  # ✅ Replace with YOUR short code
    passkey=os.getenv("MPESA_PASSKEY"),  # ✅ Your passkey from Daraja portal
    callback_url='https://yourdomain.com/callback'  # ✅ Must be HTTPS and reachable
)

# 🔐 Get M-PESA token and init STKPush
token = app_mp.get_token()
stk = STKPush(app_mp, access_token=token)

# 🔁 Initiate STK Push
@app.route('/pay', methods=['POST'])
def pay():
    d = request.json
    checkout = stk.process_request(
        phone_number=d['phone'],
        amount=int(d['amount']),
        account_reference=str(uuid.uuid4())[:8],
        transaction_desc='WiFi access'
    )
    return jsonify({
        'CheckoutRequestID': checkout.get('CheckoutRequestID'),
        'MerchantRequestID': checkout.get('MerchantRequestID')
    })


# 🔄 Poll STK status & issue voucher if successful
@app.route('/status/<cid>', methods=['GET'])
def status(cid):
    res = stk.query(
        business_short_code='174379',
        checkout_request_id=cid
    )

    if res.get('ResultCode') == '0':
        voucher = uuid.uuid4().hex[:8].upper()
        password = uuid.uuid4().hex[:6]
        seconds = request.args.get('seconds', default='3600')

        cur = db.cursor()

        # Insert voucher into FreeRADIUS radcheck table
        cur.execute("""
            INSERT INTO radcheck (username, attribute, op, value)
            VALUES (%s, 'Cleartext-Password', ':=', %s),
                   (%s, 'Session-Timeout', ':=', %s),
                   (%s, 'Simultaneous-Use', ':=', '1')
        """, (voucher, password, voucher, seconds, voucher))

        # Save to mpesa_payments for manual fallback
        cur.execute("""
            INSERT INTO mpesa_payments (checkout_id, voucher, password)
            VALUES (%s, %s, %s)
        """, (cid, voucher, password))

        db.commit()
        return jsonify(status='SUCCESS', voucher=voucher, password=password)
    else:
        return jsonify(status='PENDING', details=res)


# ✅ Manual entry of M-PESA message code (fallback)
@app.route('/verify-code', methods=['POST'])
def verify_code():
    data = request.get_json()
    code = data.get("code", "").strip().upper()

    if not code or len(code) < 8 or not code.isalnum():
        return jsonify({'status': 'INVALID', 'message': 'Code format is invalid'})

    cur = db.cursor()
    cur.execute("""
        SELECT voucher, password FROM mpesa_payments
        WHERE mpesa_code = %s
    """, (code,))
    result = cur.fetchone()

    if result:
        voucher, password = result
        return jsonify({'status': 'SUCCESS', 'voucher': voucher, 'password': password})
    else:
        return jsonify({'status': 'INVALID', 'message': 'Code not found or already used'})


# 🛰️ Register user device
@app.route('/register_device', methods=['POST'])
def register_device():
    d = request.json
    mac, ip, voucher = d['mac'], d['ip'], d['voucher']
    cur = db.cursor()
    cur.execute("""
        INSERT INTO device_map (voucher, mac, ip)
        VALUES (%s, %s, %s)
    """, (voucher, mac, ip))
    db.commit()
    return '', 204


# 🔔 M-PESA callback handler (you can log this for auditing)
@app.route('/callback', methods=['POST'])
def callback():
    data = request.get_json()
    # Log or handle data['Body'] as needed (optional)
    return '', 200


# 🚀 Start server
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
