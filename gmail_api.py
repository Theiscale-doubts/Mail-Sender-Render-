"""
Send email through the Gmail API over HTTPS (works on hosts that block SMTP,
e.g. Render). Uses OAuth2: a long-lived refresh token is exchanged for a
short-lived access token, then messages are POSTed to the Gmail REST API.

Delivery-first strategy: every recipient must get the mail. A first pass sends
to everyone (with short in-flight retries); anyone who still failed is queued
and retried again at the end in slower rounds with much longer waits.

Runtime needs only `requests`. Get the refresh token once by running
get_gmail_token.py locally (see README).
"""
import base64
import threading
import time
from concurrent.futures import ThreadPoolExecutor

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


# Parallel workers for the first pass. Delivery is the priority, speed second:
# 4 workers stays well under Gmail's sustained rate limit so far fewer sends
# hit 429 in the first place.
MAX_WORKERS = 4

# In-flight backoff (seconds) when a single send hits a transient error.
FIRST_PASS_BACKOFF = (2, 5, 10)
RETRY_PASS_BACKOFF = (10, 30, 60)

# Waits (seconds) before each end-of-run retry round for recipients that
# failed the whole first pass. Escalating — the last stragglers get the
# longest cool-down before we try them again.
RETRY_ROUND_WAITS = (30, 90, 180)

# Statuses worth retrying (rate limit / transient server trouble).
TRANSIENT = (429, 500, 502, 503)

# One requests.Session per worker thread: keeps the TLS connection to Gmail
# open across sends instead of re-handshaking for every email.
# (Session objects are not guaranteed thread-safe, hence per-thread.)
_thread_local = threading.local()


def _session():
    s = getattr(_thread_local, "session", None)
    if s is None:
        s = requests.Session()
        _thread_local.session = s
    return s


def send_emails_api(sender_email, client_id, client_secret, refresh_token,
                    recipients, subject_tpl, body_tpl, log_callback=None):
    """Same contract as email_sender.send_emails -> (success, fail, errors)."""
    counters = {"success": 0, "fail": 0}
    errors = []
    failed_recipients = []          # recipients to retry at the end
    lock = threading.Lock()

    def log(msg):
        if log_callback:
            log_callback(msg)

    token = _access_token(client_id, client_secret, refresh_token)
    headers = {"Authorization": f"Bearer {token}"}

    def build_raw(r, email):
        body = fill(body_tpl, r)
        msg = MIMEMultipart("alternative")
        msg["From"] = sender_email
        msg["To"] = email
        msg["Subject"] = fill(subject_tpl, r)
        # plain-text first (fallback), branded HTML second (preferred)
        msg.attach(MIMEText(body, "plain"))
        msg.attach(MIMEText(render_html(body, r), "html"))
        return base64.urlsafe_b64encode(msg.as_bytes()).decode()

    def send_one(r, backoffs, final):
        """Try to send to one recipient, retrying transient errors with the
        given backoff schedule. On failure: queue for the end-of-run retry
        rounds, or count as failed if this was the final round."""
        email = (r.get("Email", "") or "").strip()
        name = (r.get("Name", "") or "").strip()
        if not email or "@" not in email:
            return

        raw = build_raw(r, email)
        last_err = None
        attempts = len(backoffs) + 1
        for i in range(attempts):
            try:
                resp = _session().post(SEND_URL, headers=headers, timeout=20,
                                       json={"raw": raw})
                if resp.status_code == 200:
                    with lock:
                        counters["success"] += 1
                    log(f"OK   Sent -> {name} <{email}>")
                    return
                last_err = f"{resp.status_code} {resp.text[:150]}"
                if resp.status_code not in TRANSIENT:
                    break               # permanent error — backoff won't help
            except requests.RequestException as e:
                last_err = str(e)
            if i < len(backoffs):
                time.sleep(backoffs[i])

        if final:
            with lock:
                counters["fail"] += 1
                errors.append(f"{email}: {last_err}")
            log(f"FAIL Failed -> {name} <{email}>  ({last_err})")
        else:
            with lock:
                failed_recipients.append(r)
            log(f"WARN Deferred -> {name} <{email}>  ({last_err}) — "
                "will retry at the end")

    # ---- first pass: everyone ------------------------------------------
    workers = min(MAX_WORKERS, max(1, len(recipients)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(lambda r: send_one(r, FIRST_PASS_BACKOFF, final=False),
                      recipients))

    # ---- end-of-run retry rounds: only the ones that failed -------------
    for round_no, wait in enumerate(RETRY_ROUND_WAITS, start=1):
        if not failed_recipients:
            break
        pending, failed_recipients = failed_recipients, []
        final = round_no == len(RETRY_ROUND_WAITS)
        log(f"WARN {len(pending)} recipient(s) still pending — waiting "
            f"{wait}s before retry round {round_no}/{len(RETRY_ROUND_WAITS)}")
        time.sleep(wait)
        # fresh access token: retry rounds can start long after the first
        # pass, and it also recovers from a token gone stale mid-run
        try:
            headers["Authorization"] = (
                "Bearer "
                + _access_token(client_id, client_secret, refresh_token))
        except RuntimeError as e:
            log(f"WARN Token refresh failed before retry round: {e}")
        # sequential + long backoffs: slow on purpose, delivery over speed
        for r in pending:
            send_one(r, RETRY_PASS_BACKOFF, final=final)

    return counters["success"], counters["fail"], errors
