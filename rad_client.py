from flask import Flask, request, jsonify
import uuid
import os
from dotenv import load_dotenv
import MySQLdb
from mpesa_connect import App, STKPush

# Load environment variables from .env
load_dotenv()

# Flask App
app = Flask(__name__)

# DB Connection (update credentials as needed)
db = MySQLdb.connect(
    host='localhost',
    user='radius',
    passwd='radiuspass',
    db='radius',
    port=3306
)

# M-PESA Configuration
mpesa_app = App(
    consumer_key=os.getenv("MPESA_CONSUMER_KEY"),
    consumer_secret=os.getenv("MPESA_CONSUMER_SECRET"),
    short_code='174379',
    passkey=os.getenv("MPESA_PASSKEY"),
    callback_url='https://paywifi.com/callback'  # MUST be HTTPS and reachable by Safaricom
)

access_token = mpesa_app.get_token()
stkpush = STKPush(mpesa_app, access_token=access_token)

@app.route('/pay', methods=['POST'])
def pay():
    data = request.get_json()
    phone = data.get('phone')
    amount = int(data.get('amount'))

    res = stkpush.process_request(
        phone_number=phone,
        amount=amount,
        account_reference=str(uuid.uuid4())[:8],
        transaction_desc='WiFi Access Payment'
    )

    return jsonify({
        'CheckoutRequestID': res.get('CheckoutRequestID'),
        'MerchantRequestID': res.get('MerchantRequestID')
    })

@app.route('/status/<checkout_id>', methods=['GET'])
def status(checkout_id):
    seconds = request.args.get('seconds', default='3600')

    result = stkpush.query(
        business_short_code='174379',
        checkout_request_id=checkout_id
    )

    if result.get('ResultCode') == '0':
        voucher = uuid.uuid4().hex[:8].upper()
        password = uuid.uuid4().hex[:6]

        cur = db.cursor()

        # Insert into radcheck (FreeRADIUS auth)
        cur.execute("""
            INSERT INTO radcheck (username, attribute, op, value)
            VALUES (%s, 'Cleartext-Password', ':=', %s),
                   (%s, 'Session-Timeout', ':=', %s),
                   (%s, 'Simultaneous-Use', ':=', '1')
        """, (voucher, password, voucher, seconds, voucher))

        # Save to mpesa_payments
        cur.execute("""
            INSERT INTO mpesa_payments (checkout_id, voucher, password)
            VALUES (%s, %s, %s)
        """, (checkout_id, voucher, password))

        db.commit()
        return jsonify(status='SUCCESS', voucher=voucher, password=password)

    elif result.get('ResultCode') == '1032':
        return jsonify(status='CANCELLED')
    else:
        return jsonify(status='PENDING')

@app.route('/verify-code', methods=['POST'])
def verify_code():
    data = request.get_json()
    code = data.get('code', '').strip().upper()

    if not code or len(code) < 8 or not code.isalnum():
        return jsonify({'status': 'INVALID', 'message': 'Invalid M-PESA code format'})

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

@app.route('/callback', methods=['POST'])
def callback():
    # Log M-PESA transaction (optional)
    data = request.get_json()
    with open('mpesa_callback.log', 'a') as f:
        f.write(str(data) + '\n')
    return '', 200

@app.route('/register_device', methods=['POST'])
def register_device():
    data = request.json
    voucher = data.get('voucher')
    mac = data.get('mac')
    ip = data.get('ip')

    cur = db.cursor()
    cur.execute("""
        INSERT INTO device_map (voucher, mac, ip)
        VALUES (%s, %s, %s)
    """, (voucher, mac, ip))
    db.commit()
    return '', 204

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)

