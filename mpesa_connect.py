import base64
import datetime
import requests
from dataclasses import dataclass

@dataclass
class App:
    consumer_key: str
    consumer_secret: str
    short_code: str
    passkey: str
    callback_url: str

    def get_token(self):
        res = requests.get(
            "https://sandbox.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials",
            auth=(self.consumer_key, self.consumer_secret)
        )
        return res.json().get("access_token")

@dataclass
class STKPush:
    app: App
    access_token: str

    def process_request(self, phone_number, amount, account_reference, transaction_desc):
        timestamp = datetime.datetime.now().strftime('%Y%m%d%H%M%S')
        password = base64.b64encode(
            (self.app.short_code + self.app.passkey + timestamp).encode()
        ).decode()

        headers = {
            'Authorization': f'Bearer {self.access_token}',
            'Content-Type': 'application/json'
        }

        payload = {
            "BusinessShortCode": self.app.short_code,
            "Password": password,
            "Timestamp": timestamp,
            "TransactionType": "CustomerPayBillOnline",
            "Amount": amount,
            "PartyA": phone_number,
            "PartyB": self.app.short_code,
            "PhoneNumber": phone_number,
            "CallBackURL": self.app.callback_url,
            "AccountReference": account_reference,
            "TransactionDesc": transaction_desc
        }

        res = requests.post(
            "https://sandbox.safaricom.co.ke/mpesa/stkpush/v1/processrequest",
            json=payload,
            headers=headers
        )
        return res.json()

    def query(self, business_short_code, checkout_request_id):
        timestamp = datetime.datetime.now().strftime('%Y%m%d%H%M%S')
        password = base64.b64encode(
            (business_short_code + self.app.passkey + timestamp).encode()
        ).decode()

        headers = {
            'Authorization': f'Bearer {self.access_token}',
            'Content-Type': 'application/json'
        }

        payload = {
            "BusinessShortCode": business_short_code,
            "Password": password,
            "Timestamp": timestamp,
            "CheckoutRequestID": checkout_request_id
        }

        res = requests.post(
            "https://sandbox.safaricom.co.ke/mpesa/stkpushquery/v1/query",
            json=payload,
            headers=headers
        )
        return res.json()
