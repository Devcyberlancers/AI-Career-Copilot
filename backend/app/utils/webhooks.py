import os
import json
import urllib.request
import threading
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

def trigger_n8n_webhook(event_name: str, payload: dict):
    """
    Sends a JSON webhook event payload asynchronously to n8n if N8N_WEBHOOK_URL is configured.
    """
    # Reload environment variables from .env dynamically
    load_dotenv(override=True)
    webhook_url = os.getenv("N8N_WEBHOOK_URL")

    if not webhook_url:
        print("[Webhook] Warning: N8N_WEBHOOK_URL is not set. Webhook skipped.")
        return

    data = {
        "event": event_name,
        "timestamp": datetime.utcnow().isoformat(),
        "data": payload
    }

    def send_request():
        try:
            import ssl
            # Bypass SSL certificate verification for local/self-signed n8n setups
            context = ssl._create_unverified_context()
            
            req = urllib.request.Request(
                webhook_url,
                data=json.dumps(data, default=str).encode('utf-8'),
                headers={'Content-Type': 'application/json'},
                method='POST'
            )
            with urllib.request.urlopen(req, timeout=5, context=context) as response:
                response.read()
            print(f"[Webhook] Event '{event_name}' successfully sent to n8n.")
        except Exception as e:
            print(f"[Webhook] Failed to send '{event_name}' event to n8n: {e}")

    threading.Thread(target=send_request, daemon=True).start()
