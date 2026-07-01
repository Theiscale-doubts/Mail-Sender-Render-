"""
Send email through the Gmail API over HTTPS (works on hosts that block SMTP,
e.g. Render). Uses OAuth2: a long-lived refresh token is exchanged for a
short-lived access token, then messages are POSTed to the Gmail REST API.

Runtime needs only `requests`. Get the refresh token once by running
get_gmail_token.py locally (see README).
"""
import base64
import requests
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from email_sender import fill   # reuse the {placeholder} filler
from email_template import render_html

TOKEN_URL = "https://oauth2.googleapis.com/token"
SEND_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"


def _access_token(client_id, client_secret, refresh_token):
    try:
        r = requests.post(TOKEN_URL, timeout=20, data={
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        })
    except requests.RequestException as e:
        raise RuntimeError(f"Could not reach Google to refresh token: {e}")
    if r.status_code != 200:
        raise RuntimeError(
            "Gmail API token refresh failed. Your refresh token may be invalid "
            "or expired (re-run get_gmail_token.py). "
            f"[{r.status_code}: {r.text[:160]}]"
        )
    return r.json().get("access_token")


def send_emails_api(sender_email, client_id, client_secret, refresh_token,
                    recipients, subject_tpl, body_tpl, log_callback=None):
    """Same contract as email_sender.send_emails -> (success, fail, errors)."""
    success, fail, errors = 0, 0, []

    def log(msg):
        if log_callback:
            log_callback(msg)

    token = _access_token(client_id, client_secret, refresh_token)
    headers = {"Authorization": f"Bearer {token}"}

    for r in recipients:
        email = (r.get("Email", "") or "").strip()
        name = (r.get("Name", "") or "").strip()
        if not email or "@" not in email:
            continue

        body = fill(body_tpl, r)
        msg = MIMEMultipart("alternative")
        msg["From"] = sender_email
        msg["To"] = email
        msg["Subject"] = fill(subject_tpl, r)
        # plain-text first (fallback), branded HTML second (preferred)
        msg.attach(MIMEText(body, "plain"))
        msg.attach(MIMEText(render_html(body, r), "html"))
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()

        try:
            resp = requests.post(SEND_URL, headers=headers, timeout=20,
                                 json={"raw": raw})
            if resp.status_code == 200:
                success += 1
                log(f"OK   Sent -> {name} <{email}>")
            else:
                fail += 1
                errors.append(f"{email}: {resp.status_code} {resp.text[:150]}")
                log(f"FAIL Failed -> {name} <{email}>  ({resp.status_code})")
        except requests.RequestException as e:
            fail += 1
            errors.append(f"{email}: {e}")
            log(f"FAIL Failed -> {name} <{email}>  ({e})")

    return success, fail, errors
