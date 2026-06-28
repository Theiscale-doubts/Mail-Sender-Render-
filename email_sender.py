"""SMTP email sending (self-contained for the web app)."""
import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime


def fill(template, recipient):
    """Replace {ColumnName} and {date} placeholders with recipient values."""
    result = template
    result = result.replace("{date}", datetime.now().strftime("%d %B %Y"))
    for key, val in recipient.items():
        result = result.replace(f"{{{key}}}", val or "")
    return result


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

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
            server.login(sender_email, app_password)

            for r in recipients:
                email = (r.get("Email", "") or "").strip()
                name = (r.get("Name", "") or "").strip()
                if not email or "@" not in email:
                    continue

                subject = fill(subject_tpl, r)
                body = fill(body_tpl, r)

                msg = MIMEMultipart("alternative")
                msg["From"] = sender_email
                msg["To"] = email
                msg["Subject"] = subject
                msg.attach(MIMEText(body, "plain"))

                try:
                    server.sendmail(sender_email, email, msg.as_string())
                    success += 1
                    log(f"OK   Sent -> {name} <{email}>")
                except Exception as e:
                    fail += 1
                    errors.append(f"{email}: {e}")
                    log(f"FAIL Failed -> {name} <{email}>  ({e})")

    except smtplib.SMTPAuthenticationError:
        raise RuntimeError(
            "Gmail authentication failed. You must use a Gmail App Password "
            "(not your regular password). Enable 2-Step Verification, then create "
            "an App Password at myaccount.google.com -> Security -> App Passwords."
        )
    except Exception as e:
        raise RuntimeError(f"SMTP error: {e}")

    return success, fail, errors
