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
PAYPAL_API_BASE = "https://api-m.paypal.com"


def send_discord_notification(user_id, amount, currency, transaction_id):
    """Send notification to Discord webhook"""
    if not DISCORD_WEBHOOK_URL:
        print("No Discord webhook URL configured")
        return
    
    message = {
        "content": f"PAYPAL_DEPOSIT:{user_id}:{amount}:{currency}:{transaction_id}"
    }
    
    data = json.dumps(message).encode()
    req = urllib.request.Request(DISCORD_WEBHOOK_URL, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    
    try:
        with urllib.request.urlopen(req) as resp:
            print(f"Discord notification sent: {user_id} - {amount} {currency}")
    except Exception as e:
        print(f"Discord notification error: {e}")


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
        purchase_units = resource.get("purchase_units", [{}])
        custom_id = purchase_units[0].get("custom_id", "") if purchase_units else ""
        amount_data = purchase_units[0].get("amount", {}) if purchase_units else {}
        amount = amount_data.get("value", "0")
        currency = amount_data.get("currency_code", "EUR")
        transaction_id = resource.get("id", "unknown")
        
        if custom_id:
            send_discord_notification(custom_id, amount, currency, transaction_id)
    
    elif event_type == "PAYMENT.CAPTURE.COMPLETED":
        resource = event.get("resource", {})
        custom_id = resource.get("custom_id", "")
        amount_data = resource.get("amount", {})
        amount = amount_data.get("value", "0")
        currency = amount_data.get("currency_code", "EUR")
        transaction_id = resource.get("id", "unknown")
        
        if custom_id:
            send_discord_notification(custom_id, amount, currency, transaction_id)
    
    return jsonify({"status": "ok"}), 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
