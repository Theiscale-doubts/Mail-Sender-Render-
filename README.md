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

## Sending email when hosted: use the Gmail API (free hosts block SMTP)

Render's free tier **blocks outbound SMTP**, so the App Password method only
works locally. For hosting, the app uses the **Gmail API over HTTPS** instead —
free, sends from your real Gmail, no footer, ~500/day. The app auto-uses the
Gmail API when its env vars are set; otherwise it falls back to SMTP.

### One-time setup (~15 min)

**A. Google Cloud Console** — https://console.cloud.google.com
1. Create a project (top bar → New Project).
2. **APIs & Services → Library →** search **Gmail API** → **Enable**.
3. **APIs & Services → OAuth consent screen:**
   - User type **External** → fill app name, your email for support + developer.
   - **Add yourself as a Test user.**
   - **Publish the app** (Publishing status → **Publish → Confirm**). This is
     important: in "Testing" mode the refresh token expires after 7 days; in
     "Production" it lasts indefinitely. The "unverified app" warning is fine
     for personal use.
4. **APIs & Services → Credentials → Create Credentials → OAuth client ID:**
   - Application type **Desktop app** → Create → **Download JSON**.
   - Save it as `client_secret.json` inside this `web_app` folder.

**B. Get your refresh token (run locally)**
```bash
cd web_app
pip install -r requirements.txt
python get_gmail_token.py
```
A browser opens → sign in with the Gmail you want to send **from** → **Allow**.
The script prints four values. Copy them.

**C. Put the values where the app reads them**
- **Locally:** paste into `.env` (`GMAIL_ADDRESS`, `GMAIL_CLIENT_ID`,
  `GMAIL_CLIENT_SECRET`, `GMAIL_REFRESH_TOKEN`).
- **On Render:** add the same four as Environment variables (below). You can
  then remove `GMAIL_APP_PASSWORD` — it's not used when the API is configured.

> `client_secret.json`, `.env`, and tokens are gitignored — they never reach GitHub.

---

## Deploy free on Render (recommended)

1. Push this `web_app` folder to a **GitHub repo**.
2. https://render.com → free account → **New → Web Service** → connect the repo.
3. Settings:
   - **Root Directory:** `web_app` (only if it's a subfolder of the repo)
   - **Build:** `pip install -r requirements.txt`
   - **Start:** `gunicorn app:app --bind 0.0.0.0:$PORT --timeout 120`
   - **Instance type:** Free
4. Open the **Environment** tab and add these variables:
   | Key | Value |
   |-----|-------|
   | `GMAIL_ADDRESS` | your@gmail.com (the sender) |
   | `GMAIL_CLIENT_ID` | from get_gmail_token.py |
   | `GMAIL_CLIENT_SECRET` | from get_gmail_token.py |
   | `GMAIL_REFRESH_TOKEN` | from get_gmail_token.py |
   | `APP_PASSWORD` | access password for the web page (login) |
   | `SECRET_KEY` | any long random string (keeps logins across restarts) |
   | `BASIC_SHEET_URL` | (optional) Basic sheet link |
   | `MAIN_SHEET_URL` | (optional) Main sheet link |

   (`GMAIL_APP_PASSWORD` is **not** needed on Render — SMTP is blocked there;
   the Gmail API vars above are what make sending work.)
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
