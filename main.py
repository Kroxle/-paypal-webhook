from flask import Flask, request, jsonify
import json
import os
import urllib.request
import base64

app = Flask(__name__)

PAYPAL_CLIENT_ID = os.environ.get("PAYPAL_CLIENT_ID")
PAYPAL_SECRET = os.environ.get("PAYPAL_SECRET")
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
PAYPAL_WEBHOOK_ID = os.environ.get("PAYPAL_WEBHOOK_ID")
PAYPAL_API_BASE = "https://api-m.paypal.com"  # Live


def get_paypal_access_token():
    """Get OAuth token from PayPal"""
    url = f"{PAYPAL_API_BASE}/v1/oauth2/token"
    data = "grant_type=client_credentials".encode()
    
    credentials = f"{PAYPAL_CLIENT_ID}:{PAYPAL_SECRET}"
    auth = base64.b64encode(credentials.encode()).decode()
    
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Authorization", f"Basic {auth}")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode())
            return result.get("access_token")
    except Exception as e:
        print(f"Failed to get PayPal token: {e}")
        return None


def create_paypal_order(amount_eur: float, user_id: str, return_url: str, cancel_url: str):
    """Create a PayPal order and return approval URL"""
    access_token = get_paypal_access_token()
    if not access_token:
        return None, "Failed to authenticate with PayPal"
    
    url = f"{PAYPAL_API_BASE}/v2/checkout/orders"
    
    order_data = {
        "intent": "CAPTURE",
        "purchase_units": [{
            "amount": {
                "currency_code": "EUR",
                "value": f"{amount_eur:.2f}"
            },
            "custom_id": str(user_id),
            "description": f"Deposit for Discord User {user_id}"
        }],
        "application_context": {
            "return_url": return_url,
            "cancel_url": cancel_url,
            "brand_name": "SMM Service",
            "user_action": "PAY_NOW"
        }
    }
    
    data = json.dumps(order_data).encode()
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Authorization", f"Bearer {access_token}")
    req.add_header("Content-Type", "application/json")
    
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode())
            
            for link in result.get("links", []):
                if link.get("rel") == "approve":
                    return link.get("href"), None
            
            return None, "No approval URL in response"
    except Exception as e:
        print(f"Failed to create PayPal order: {e}")
        return None, str(e)


def capture_paypal_order(order_id: str):
    """Capture a PayPal order after approval"""
    access_token = get_paypal_access_token()
    if not access_token:
        return None, "Failed to authenticate with PayPal"
    
    url = f"{PAYPAL_API_BASE}/v2/checkout/orders/{order_id}/capture"
    
    req = urllib.request.Request(url, data=b"", method="POST")
    req.add_header("Authorization", f"Bearer {access_token}")
    req.add_header("Content-Type", "application/json")
    
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode())
            return result, None
    except Exception as e:
        print(f"Failed to capture PayPal order: {e}")
        return None, str(e)


def send_discord_notification(user_id, amount, currency, transaction_id):
    """Send notification to Discord webhook"""
    if not DISCORD_WEBHOOK_URL:
        print("No Discord webhook URL configured")
        return False
    
    message = {
        "content": f"PAYPAL_DEPOSIT:{user_id}:{amount}:{currency}:{transaction_id}"
    }
    
    data = json.dumps(message).encode()
    req = urllib.request.Request(DISCORD_WEBHOOK_URL, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            print(f"Discord notification sent: {user_id} - {amount} {currency}")
            return True
    except Exception as e:
        print(f"Discord notification error: {e}")
        return False


@app.route("/", methods=["GET"])
def home():
    return "PayPal Webhook Server Running"


@app.route("/webhook", methods=["GET", "POST"])
def webhook():
    if request.method == "GET":
        return "PayPal Webhook Endpoint Ready"
    
    try:
        event = request.get_json()
    except:
        return jsonify({"error": "Invalid JSON"}), 400
    
    event_type = event.get("event_type", "")
    print(f"Received PayPal event: {event_type}")
    
    if event_type == "CHECKOUT.ORDER.APPROVED":
        resource = event.get("resource", {})
        order_id = resource.get("id")
        
        purchase_units = resource.get("purchase_units", [])
        if purchase_units:
            custom_id = purchase_units[0].get("custom_id", "")
            amount_data = purchase_units[0].get("amount", {})
            amount = amount_data.get("value", "0")
            currency = amount_data.get("currency_code", "EUR")
            
            print(f"Order approved: {order_id}, User: {custom_id}, Amount: {amount} {currency}")
            
            if order_id:
                capture_result, error = capture_paypal_order(order_id)
                if capture_result:
                    print(f"Payment captured successfully!")
                else:
                    print(f"Capture failed: {error}")
    
    elif event_type == "PAYMENT.CAPTURE.COMPLETED":
        resource = event.get("resource", {})
        custom_id = resource.get("custom_id", "")
        amount_data = resource.get("amount", {})
        amount = amount_data.get("value", "0")
        currency = amount_data.get("currency_code", "EUR")
        transaction_id = resource.get("id", "unknown")
        
        print(f"Payment captured: User {custom_id}, Amount: {amount} {currency}, TX: {transaction_id}")
        
        if custom_id:
            send_discord_notification(custom_id, amount, currency, transaction_id)
        else:
            print("No custom_id found in payment capture!")
    
    elif event_type == "CHECKOUT.ORDER.COMPLETED":
        resource = event.get("resource", {})
        purchase_units = resource.get("purchase_units", [])
        
        if purchase_units:
            custom_id = purchase_units[0].get("custom_id", "")
            amount_data = purchase_units[0].get("amount", {})
            amount = amount_data.get("value", "0")
            currency = amount_data.get("currency_code", "EUR")
            
            payments = purchase_units[0].get("payments", {})
            captures = payments.get("captures", [])
            transaction_id = captures[0].get("id", "unknown") if captures else "unknown"
            
            print(f"Order completed: User {custom_id}, Amount: {amount} {currency}")
            
            if custom_id:
                send_discord_notification(custom_id, amount, currency, transaction_id)
    
    return jsonify({"status": "ok"}), 200


@app.route("/create-order", methods=["POST"])
def create_order():
    """API endpoint to create a PayPal order"""
    try:
        data = request.get_json()
        amount = float(data.get("amount", 0))
        user_id = str(data.get("user_id", ""))
        
        if amount < 1:
            return jsonify({"error": "Minimum amount is 1 EUR"}), 400
        
        if not user_id:
            return jsonify({"error": "User ID required"}), 400
        
        base_url = request.host_url.rstrip("/")
        return_url = f"{base_url}/payment-success"
        cancel_url = f"{base_url}/payment-cancelled"
        
        approval_url, error = create_paypal_order(amount, user_id, return_url, cancel_url)
        
        if approval_url:
            return jsonify({
                "success": True,
                "approval_url": approval_url
            })
        else:
            return jsonify({
                "success": False,
                "error": error
            }), 500
            
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/payment-success", methods=["GET"])
def payment_success():
    return """
    <html>
    <head><title>Payment Successful</title></head>
    <body style="font-family: Arial; text-align: center; padding: 50px;">
        <h1>Payment Successful!</h1>
        <p>Your balance will be credited automatically within a few seconds.</p>
        <p>You can close this window and return to Discord.</p>
    </body>
    </html>
    """


@app.route("/payment-cancelled", methods=["GET"])
def payment_cancelled():
    return """
    <html>
    <head><title>Payment Cancelled</title></head>
    <body style="font-family: Arial; text-align: center; padding: 50px;">
        <h1>Payment Cancelled</h1>
        <p>Your payment was cancelled. No money was charged.</p>
        <p>You can close this window and return to Discord.</p>
    </body>
    </html>
    """


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
