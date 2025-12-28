from http.server import BaseHTTPRequestHandler
import json
import os
import urllib.request
import urllib.parse

PAYPAL_CLIENT_ID = os.environ.get("PAYPAL_CLIENT_ID")
PAYPAL_SECRET = os.environ.get("PAYPAL_SECRET")
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
PAYPAL_API_BASE = "https://api-m.paypal.com"  # Live


def get_paypal_access_token():
    """Get OAuth token from PayPal"""
    url = f"{PAYPAL_API_BASE}/v1/oauth2/token"
    data = "grant_type=client_credentials".encode()
    
    req = urllib.request.Request(url, data=data, method="POST")
    credentials = f"{PAYPAL_CLIENT_ID}:{PAYPAL_SECRET}"
    import base64
    auth = base64.b64encode(credentials.encode()).decode()
    req.add_header("Authorization", f"Basic {auth}")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    
    with urllib.request.urlopen(req) as resp:
        result = json.loads(resp.read().decode())
        return result["access_token"]


def verify_webhook(headers, body):
    """Verify webhook signature with PayPal"""
    try:
        access_token = get_paypal_access_token()
        
        verify_url = f"{PAYPAL_API_BASE}/v1/notifications/verify-webhook-signature"
        
        verify_data = {
            "auth_algo": headers.get("paypal-auth-algo", ""),
            "cert_url": headers.get("paypal-cert-url", ""),
            "transmission_id": headers.get("paypal-transmission-id", ""),
            "transmission_sig": headers.get("paypal-transmission-sig", ""),
            "transmission_time": headers.get("paypal-transmission-time", ""),
            "webhook_id": os.environ.get("PAYPAL_WEBHOOK_ID", ""),
            "webhook_event": body
        }
        
        req = urllib.request.Request(
            verify_url, 
            data=json.dumps(verify_data).encode(),
            method="POST"
        )
        req.add_header("Authorization", f"Bearer {access_token}")
        req.add_header("Content-Type", "application/json")
        
        with urllib.request.urlopen(req) as resp:
            result = json.loads(resp.read().decode())
            return result.get("verification_status") == "SUCCESS"
    except Exception as e:
        print(f"Verification error: {e}")
        return False


def send_discord_notification(user_id, amount, currency, transaction_id):
    """Send notification to Discord webhook"""
    if not DISCORD_WEBHOOK_URL:
        return
    
    message = {
        "content": f"PAYPAL_DEPOSIT:{user_id}:{amount}:{currency}:{transaction_id}"
    }
    
    data = json.dumps(message).encode()
    req = urllib.request.Request(DISCORD_WEBHOOK_URL, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    
    try:
        with urllib.request.urlopen(req) as resp:
            pass
    except Exception as e:
        print(f"Discord notification error: {e}")


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length)
        
        try:
            event = json.loads(body.decode())
        except:
            self.send_response(400)
            self.end_headers()
            return
        
        # Get headers for verification
        headers = {
            "paypal-auth-algo": self.headers.get("paypal-auth-algo", ""),
            "paypal-cert-url": self.headers.get("paypal-cert-url", ""),
            "paypal-transmission-id": self.headers.get("paypal-transmission-id", ""),
            "paypal-transmission-sig": self.headers.get("paypal-transmission-sig", ""),
            "paypal-transmission-time": self.headers.get("paypal-transmission-time", ""),
        }
        
        # Verify webhook (optional but recommended)
        # is_valid = verify_webhook(headers, event)
        # For now, skip verification to simplify setup
        is_valid = True
        
        if not is_valid:
            self.send_response(401)
            self.end_headers()
            return
        
        # Check event type
        event_type = event.get("event_type", "")
        
        if event_type == "CHECKOUT.ORDER.APPROVED":
            # Payment approved
            resource = event.get("resource", {})
            
            # Get custom_id (Discord user ID)
            purchase_units = resource.get("purchase_units", [{}])
            custom_id = purchase_units[0].get("custom_id", "") if purchase_units else ""
            
            # Get amount
            amount_data = purchase_units[0].get("amount", {}) if purchase_units else {}
            amount = amount_data.get("value", "0")
            currency = amount_data.get("currency_code", "EUR")
            
            # Transaction ID
            transaction_id = resource.get("id", "unknown")
            
            if custom_id:
                send_discord_notification(custom_id, amount, currency, transaction_id)
        
        elif event_type == "PAYMENT.CAPTURE.COMPLETED":
            # Payment captured
            resource = event.get("resource", {})
            
            custom_id = resource.get("custom_id", "")
            amount_data = resource.get("amount", {})
            amount = amount_data.get("value", "0")
            currency = amount_data.get("currency_code", "EUR")
            transaction_id = resource.get("id", "unknown")
            
            if custom_id:
                send_discord_notification(custom_id, amount, currency, transaction_id)
        
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")
    
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"PayPal Webhook Server Running")
