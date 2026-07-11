"""SMTP email sending (self-contained for the web app).

Delivery-first strategy: every recipient must get the mail. A first pass
sends to everyone; anyone who failed is queued and retried again at the end
in slower rounds with much longer waits and a fresh SMTP connection.
"""
import smtplib
import ssl
import time
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

from email_template import render_html

# Waits (seconds) before each end-of-run retry round for recipients that
# failed the first pass. Escalating — the last stragglers get the longest
# cool-down before we try them again.
RETRY_ROUND_WAITS = (30, 90, 180)


def fill(template, recipient=None):
    """Fill placeholders. General-purpose: only {date} is substituted
    (no per-recipient name/column personalization)."""
    return (template or "").replace("{date}", datetime.now().strftime("%d %B %Y"))


def _connect(sender_email, app_password, context):
    """Open and authenticate a fresh SMTP connection (20s timeout so a
    blocked SMTP port fails fast instead of hanging until the web worker
    is killed)."""
    server = smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context,
                              timeout=20)
    try:
        server.login(sender_email, app_password)
    except Exception:
        server.close()
        raise
    return server


def send_emails(sender_email, app_password, recipients, subject_tpl, body_tpl,
                log_callback=None):
    """
    recipients : list of dicts (keys match Excel column headers)
    Returns (success_count, fail_count, error_list)
    """
    success, fail, errors = 0, 0, []
    context = ssl.create_default_context()

    def log(msg):
        if log_callback:
            log_callback(msg)

    def build_msg(r, email):
        subject = fill(subject_tpl, r)
        body = fill(body_tpl, r)
        msg = MIMEMultipart("alternative")
        msg["From"] = sender_email
        msg["To"] = email
        msg["Subject"] = subject
        # plain-text first (fallback), branded HTML second (preferred)
        msg.attach(MIMEText(body, "plain"))
        msg.attach(MIMEText(render_html(body, r), "html"))
        return msg

    def send_batch(server, batch, final):
        """Send to each recipient in batch; return the ones that failed.
        On the final round failures are counted and logged as FAIL."""
        nonlocal success, fail
        pending = []
        for r in batch:
            email = (r.get("Email", "") or "").strip()
            name = (r.get("Name", "") or "").strip()
            if not email or "@" not in email:
                continue
            try:
                server.sendmail(sender_email, email,
                                build_msg(r, email).as_string())
                success += 1
                log(f"OK   Sent -> {name} <{email}>")
            except Exception as e:
                if final:
                    fail += 1
                    errors.append(f"{email}: {e}")
                    log(f"FAIL Failed -> {name} <{email}>  ({e})")
                else:
                    pending.append(r)
                    log(f"WARN Deferred -> {name} <{email}>  ({e}) — "
                        "will retry at the end")
        return pending

    try:
        # ---- first pass: everyone ----------------------------------------
        with _connect(sender_email, app_password, context) as server:
            failed_recipients = send_batch(server, recipients, final=False)

        # ---- end-of-run retry rounds: only the ones that failed -----------
        for round_no, wait in enumerate(RETRY_ROUND_WAITS, start=1):
            if not failed_recipients:
                break
            final = round_no == len(RETRY_ROUND_WAITS)
            log(f"WARN {len(failed_recipients)} recipient(s) still pending — "
                f"waiting {wait}s before retry round "
                f"{round_no}/{len(RETRY_ROUND_WAITS)}")
            time.sleep(wait)
            try:
                # fresh connection per round — the old one may have died or
                # been throttled during the wait
                with _connect(sender_email, app_password, context) as server:
                    failed_recipients = send_batch(server, failed_recipients,
                                                   final=final)
            except smtplib.SMTPAuthenticationError:
                raise
            except Exception as e:
                if final:
                    for r in failed_recipients:
                        email = (r.get("Email", "") or "").strip()
                        fail += 1
                        errors.append(f"{email}: {e}")
                        log(f"FAIL Failed -> <{email}>  ({e})")
                    failed_recipients = []
                else:
                    log(f"WARN Retry round {round_no} could not connect "
                        f"({e}) — will try again")

    except smtplib.SMTPAuthenticationError:
        raise RuntimeError(
            "Gmail authentication failed. You must use a Gmail App Password "
            "(not your regular password). Enable 2-Step Verification, then create "
            "an App Password at myaccount.google.com -> Security -> App Passwords."
        )
    except (TimeoutError, OSError) as e:
        raise RuntimeError(
            "Could not connect to Gmail's mail server (SMTP). This usually means "
            "the host is blocking outbound SMTP ports — common on free hosting like "
            "Render. Use an email API (e.g. Brevo/Resend over HTTPS) or a host that "
            f"allows SMTP. [{e}]"
        )
    except Exception as e:
        raise RuntimeError(f"SMTP error: {e}")

    return success, fail, errors
