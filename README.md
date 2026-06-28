# Mail Sender — Web Edition

A hostable web replica of the Mail Sender desktop tool, with the same pages —
**Dashboard · Workbooks · Compose · Sent Log · Settings** — and the same navy/blue
look. Differences from the desktop app:

- **Separate Google Sheet URLs** for the **Basic** and **Main** workbooks
  (instead of local Excel files).
- **Credentials stored in `.env`** (and on Render as secret env vars) so you set
  them once and never re-enter them.

This folder is **self-contained** — nothing outside `web_app/` is needed.

---

## Is the frontend hosted separately?

**No.** Flask serves the web page itself, so the frontend and backend are the
**same single Render web service**. You deploy once and open the Render URL — the
interface loads from the same server that sends the email. No separate frontend
host, no CORS setup.

---

## Run locally

```bash
cd web_app
python -m venv venv
venv\Scripts\activate              # Windows  (mac/linux: source venv/bin/activate)
pip install -r requirements.txt
copy .env.example .env             # then edit .env with your Gmail + sheet URLs
python app.py
```

Open http://127.0.0.1:5000

You can also set everything from the **Settings** page in the UI — saving
credentials there writes them into `.env` for you.

---

## Prepare your Google Sheets

1. Open each sheet → **Share** → **Anyone with the link** → **Viewer**.
2. Copy the link (looks like `https://docs.google.com/spreadsheets/d/XXXX/edit`).
3. Paste the Basic and Main links in the app's **Settings → Google Sheet URLs**.

Layout the app expects: headers in **row 1**, recipient data from **row 6**
(`Email`, `Name`, `Enrollment Month`, `Enrollment ending Month`, `DA`). Multiple
tabs per sheet are supported and selectable on the Compose page.

---

## Deploy free on Render (recommended)

1. Push this `web_app` folder to a **GitHub repo**.
2. https://render.com → free account → **New → Web Service** → connect the repo.
3. Settings (auto-detected from `render.yaml`):
   - **Root Directory:** `web_app` (only if it's a subfolder of the repo)
   - **Build:** `pip install -r requirements.txt`
   - **Start:** `gunicorn app:app`
   - **Instance type:** Free
4. Open the **Environment** tab and add these secret variables:
   | Key | Value |
   |-----|-------|
   | `GMAIL_ADDRESS` | your@gmail.com |
   | `GMAIL_APP_PASSWORD` | your 16-char app password |
   | `BASIC_SHEET_URL` | (optional) Basic sheet link |
   | `MAIN_SHEET_URL` | (optional) Main sheet link |
5. **Create Web Service** → you get a public URL like
   `https://mail-sender-web.onrender.com`.

> Don't commit `.env` (it's gitignored). On Render the env vars above replace it.
> Free Render instances sleep after ~15 min idle; first request then takes ~30s.

Alternatives: **Railway** (uses the `Procfile`) and **PythonAnywhere** also work
the same way — set the same environment variables there.

---

## Files

| File | Purpose |
|------|---------|
| `app.py` | Flask app — serves the page + JSON API |
| `templates/index.html` | The whole UI (Dashboard/Workbooks/Compose/Log/Settings) |
| `sheets.py` | Downloads a public Google Sheet as an in-memory workbook |
| `excel_reader.py` | Parses sheets into recipient rows |
| `email_sender.py` | Gmail SMTP sending + placeholder filling |
| `config_store.py` | `.env` credentials + `config.json` settings/stats |
| `render.yaml`, `Procfile`, `runtime.txt` | Deploy configs |
| `.env.example` | Template for your secrets |

---

## Security notes

- Credentials live only in `.env` / Render secret env vars — never in the repo,
  never sent to the browser (the page only learns *whether* a password is set).
- Sheet data is fetched and processed in memory per request; nothing is stored.
