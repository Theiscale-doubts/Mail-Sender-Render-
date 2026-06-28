# -*- coding: utf-8 -*-
"""
Mail Sender - Web edition (Flask)  |  full replica of the desktop tool.

Run locally:  python app.py   ->  http://127.0.0.1:5000
Deploy:       one Render web service serves BOTH the page and the API.
              See README.md.
"""
import os
from datetime import datetime
from collections import deque
from flask import (Flask, render_template, request, jsonify,
                   session, redirect, url_for)

from excel_reader import read_workbook
from email_sender import send_emails, fill
from sheets import download_xlsx
from config_store import (
    load_config, save_config, get_credentials, save_credentials, save_urls,
    record_stats,
)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024
# Session signing key. Set SECRET_KEY in Render so logins survive restarts;
# otherwise a random per-process key is used (you just re-login after a restart).
app.secret_key = os.environ.get("SECRET_KEY") or os.urandom(32)

# in-memory recent activity log (resets on restart)
ACTIVITY = deque(maxlen=300)

WB_LABELS = {"basic": "Basic Workbook", "main": "Main Workbook"}


def log(msg, kind=""):
    ACTIVITY.appendleft({
        "ts": datetime.now().strftime("%H:%M:%S"),
        "msg": msg, "kind": kind,
    })


def url_for_wb(cfg, wb):
    return cfg.get("basic_url" if wb == "basic" else "main_url", "")


# ── auth (single shared password) ───────────────────────────────────────────
# Protection is ACTIVE only when APP_PASSWORD is set. If it's unset (e.g. local
# dev) the app is open. Set APP_PASSWORD in Render to lock the public URL.
_PUBLIC_ENDPOINTS = {"login", "logout", "static"}


@app.before_request
def _require_login():
    gate = os.environ.get("APP_PASSWORD", "")
    if not gate:
        return  # no password configured -> protection disabled
    if request.endpoint in _PUBLIC_ENDPOINTS or session.get("authed"):
        return
    if request.path.startswith("/api/"):
        return jsonify({"ok": False, "auth": False,
                        "error": "Session expired. Please log in again."}), 401
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    gate = os.environ.get("APP_PASSWORD", "")
    if not gate:
        return redirect(url_for("index"))
    error = ""
    if request.method == "POST":
        if request.form.get("password", "") == gate:
            session["authed"] = True
            return redirect(url_for("index"))
        error = "Incorrect password."
    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ── pages ──────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return render_template("index.html")


# ── config / state ─────────────────────────────────────────────────────────
@app.route("/api/state")
def api_state():
    cfg = load_config()
    email, pwd = get_credentials()
    return jsonify({
        "email": email,
        "has_password": bool(pwd),
        "basic_url": cfg.get("basic_url", ""),
        "main_url": cfg.get("main_url", ""),
        "templates": {
            "basic": {"subject": cfg.get("basic_subject", ""),
                      "body": cfg.get("basic_body", "")},
            "main": {"subject": cfg.get("main_subject", ""),
                     "body": cfg.get("main_body", "")},
        },
        "stats": cfg.get("stats", {}),
        "activity": list(ACTIVITY)[:50],
    })


@app.route("/api/credentials", methods=["POST"])
def api_credentials():
    d = request.get_json(force=True)
    email = (d.get("email") or "").strip()
    pwd = (d.get("password") or "").replace(" ", "").strip()
    if not email or "@" not in email:
        return jsonify({"ok": False, "error": "Enter a valid Gmail address."}), 400
    if len(pwd) < 16:
        return jsonify({"ok": False, "error": "App Password must be 16 characters."}), 400
    try:
        save_credentials(email, pwd)
    except Exception as e:
        return jsonify({"ok": False, "error": f"Could not save: {e}"}), 500
    log("Gmail credentials saved.", "ok")
    return jsonify({"ok": True})


@app.route("/api/settings", methods=["POST"])
def api_settings():
    """Sheet URLs -> .env (live); templates -> config.json."""
    d = request.get_json(force=True)
    # URLs go to the environment (single source of truth), applied immediately.
    if "basic_url" in d or "main_url" in d:
        save_urls(basic_url=d.get("basic_url") if "basic_url" in d else None,
                  main_url=d.get("main_url") if "main_url" in d else None)
    cfg = load_config()
    for wb in ("basic", "main"):
        t = (d.get("templates") or {}).get(wb)
        if t:
            cfg[f"{wb}_subject"] = t.get("subject", cfg.get(f"{wb}_subject", ""))
            cfg[f"{wb}_body"] = t.get("body", cfg.get(f"{wb}_body", ""))
    save_config(cfg)
    log("Settings saved.", "ok")
    return jsonify({"ok": True})


# ── load a workbook from its Google Sheet URL ──────────────────────────────
@app.route("/api/load", methods=["POST"])
def api_load():
    d = request.get_json(force=True)
    wb = d.get("workbook")
    if wb not in ("basic", "main"):
        return jsonify({"ok": False, "error": "Unknown workbook."}), 400
    cfg = load_config()
    url = url_for_wb(cfg, wb)
    if not url:
        return jsonify({"ok": False,
                        "error": f"No Google Sheet URL set for the {WB_LABELS[wb]}. "
                                 "Add it in Settings."}), 400
    try:
        data = download_xlsx(url)
        sheets = read_workbook(data)
    except Exception as e:
        log(f"Load failed ({WB_LABELS[wb]}): {e}", "err")
        return jsonify({"ok": False, "error": str(e)}), 400

    summary = [{"sheet_name": s["sheet_name"], "count": len(s["recipients"])}
               for s in sheets]
    total = sum(s["count"] for s in summary)
    log(f"Loaded {WB_LABELS[wb]} — {len(summary)} sheet(s), {total} recipient(s).", "info")
    return jsonify({"ok": True, "sheets": summary, "total": total})


# ── preview (first recipient of first selected sheet) ──────────────────────
@app.route("/api/preview", methods=["POST"])
def api_preview():
    d = request.get_json(force=True)
    wb = d.get("workbook")
    cfg = load_config()
    url = url_for_wb(cfg, wb)
    if not url:
        return jsonify({"ok": False, "error": "No sheet URL set."}), 400
    try:
        sheets = read_workbook(download_xlsx(url))
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    selected = d.get("sheets") or []
    pool = [s for s in sheets if not selected or s["sheet_name"] in selected]
    recip = next((r for s in pool for r in s["recipients"]), None)
    if not recip:
        return jsonify({"ok": False, "error": "No recipients to preview."}), 400
    return jsonify({
        "ok": True,
        "to": recip.get("Email", ""),
        "subject": fill(d.get("subject", ""), recip),
        "body": fill(d.get("body", ""), recip),
    })


# ── send ───────────────────────────────────────────────────────────────────
@app.route("/api/send", methods=["POST"])
def api_send():
    d = request.get_json(force=True)
    wb = d.get("workbook")
    if wb not in ("basic", "main"):
        return jsonify({"ok": False, "error": "Unknown workbook."}), 400

    sender, pwd = get_credentials()
    if not sender or not pwd:
        return jsonify({"ok": False,
                        "error": "No Gmail credentials. Add them in Settings."}), 400

    subject = (d.get("subject") or "").strip()
    body = d.get("body") or ""
    selected = d.get("sheets") or []
    if not subject:
        return jsonify({"ok": False, "error": "Subject cannot be empty."}), 400

    cfg = load_config()
    url = url_for_wb(cfg, wb)
    if not url:
        return jsonify({"ok": False, "error": "No sheet URL set for this workbook."}), 400

    # persist the templates being used
    cfg[f"{wb}_subject"] = subject
    cfg[f"{wb}_body"] = body
    save_config(cfg)

    try:
        sheets = read_workbook(download_xlsx(url))
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400

    if selected:
        sheets = [s for s in sheets if s["sheet_name"] in selected]
    recipients = [r for s in sheets for r in s["recipients"]]
    if not recipients:
        return jsonify({"ok": False, "error": "No recipients in the selected sheets."}), 400

    log(f"--- {WB_LABELS[wb]}: sending to {len(recipients)} recipient(s) ---", "info")
    lines = []

    def cb(m):
        lines.append(m)
        log(m, "ok" if m.startswith("OK") else "err")

    try:
        ok, fail, _ = send_emails(sender, pwd, recipients, subject, body, log_callback=cb)
    except RuntimeError as e:
        log(f"ERROR: {e}", "err")
        return jsonify({"ok": False, "error": str(e)}), 400

    record_stats(cfg, ok, fail)
    summary = f"{ok} sent, {fail} failed."
    log(f"Done — {summary}", "ok" if fail == 0 else "err")
    return jsonify({"ok": True, "sent": ok, "failed": fail,
                    "log": lines, "summary": summary})


if __name__ == "__main__":
    _email, _pwd = get_credentials()
    if _email and _pwd:
        print(f"[Mail Sender] Credentials loaded: {_email} (password OK)")
    else:
        print("[Mail Sender] WARNING: no credentials loaded from .env "
              "(email set: %s, password set: %s)" % (bool(_email), bool(_pwd)))
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
