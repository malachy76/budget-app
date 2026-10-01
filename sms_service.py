# sms_service.py — outbound SMS via Termii (popular Nigerian SMS gateway)
#
# SETUP REQUIRED — this will not send real SMS until you do this:
#   1. Create a free account at https://termii.com
#   2. Grab your API key from the Termii dashboard
#   3. In Streamlit Cloud: your app -> Manage app -> Settings -> Secrets, add:
#        TERMII_API_KEY   = "your-termii-api-key"
#        TERMII_SENDER_ID = "your-approved-sender-id"
#      A custom sender ID (e.g. "BudgetRight") needs Termii's approval
#      (usually same-day). Until approved, omit TERMII_SENDER_ID and Termii
#      will use its shared generic sender for testing.
#
# If you'd rather use a different provider (Africa's Talking, Twilio, etc.),
# only this file needs to change — auth.py just calls send_sms(phone, msg).
import requests
import streamlit as st

TERMII_URL = "https://api.ng.termii.com/api/sms/send"


def send_sms(phone: str, message: str):
    """Send an SMS via Termii. `phone` should be in +234XXXXXXXXXX format
    (use auth.normalize_phone() before calling this)."""
    try:
        api_key = st.secrets["TERMII_API_KEY"]
    except Exception:
        return False, "SMS is not configured yet (missing TERMII_API_KEY in secrets)."
    sender = st.secrets.get("TERMII_SENDER_ID", "Termii")
    try:
        resp = requests.post(
            TERMII_URL,
            json={
                "to": phone.lstrip("+"),
                "from": sender,
                "sms": message,
                "type": "plain",
                "channel": "generic",
                "api_key": api_key,
            },
            timeout=10,
        )
        data = resp.json()
        if resp.status_code == 200 and data.get("message_id"):
            return True, "SMS sent"
        return False, data.get("message", "SMS provider error")
    except Exception as e:
        return False, str(e)
