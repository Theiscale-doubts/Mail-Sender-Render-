"""
Run this ONCE on your own computer to get a Gmail API refresh token.

Prereqs:
  1. In Google Cloud Console: create a project, enable the "Gmail API",
     configure the OAuth consent screen, and create an OAuth client ID of type
     "Desktop app". Download its JSON as  client_secret.json  into this folder.
  2. pip install google-auth-oauthlib requests   (already in requirements.txt)

Usage:
  python get_gmail_token.py
  (optionally:  python get_gmail_token.py path/to/client_secret.json )

A browser window opens -> sign in with the Gmail you want to send FROM ->
click Allow. The script then prints the values to paste into Render env vars.
"""
import sys
import json

try:
    from google_auth_oauthlib.flow import InstalledAppFlow
except ImportError:
    print("Missing dependency. Run:  pip install google-auth-oauthlib")
    sys.exit(1)

SCOPES = ["https://www.googleapis.com/auth/gmail.send"]


def main():
    cs_path = sys.argv[1] if len(sys.argv) > 1 else "client_secret.json"
    try:
        flow = InstalledAppFlow.from_client_secrets_file(cs_path, SCOPES)
    except FileNotFoundError:
        print(f"Could not find {cs_path}. Download your OAuth 'Desktop app' "
              "JSON from Google Cloud Console and save it there.")
        sys.exit(1)

    # access_type=offline + prompt=consent guarantees a refresh token is returned
    creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")

    info = json.load(open(cs_path))
    info = info.get("installed") or info.get("web") or {}

    if not creds.refresh_token:
        print("\nNo refresh token returned. Delete previous access for this app at "
              "https://myaccount.google.com/permissions and run again.")
        sys.exit(1)

    print("\n=========== COPY THESE INTO RENDER → ENVIRONMENT ===========")
    print(f"GMAIL_ADDRESS        = (the gmail you just signed in with)")
    print(f"GMAIL_CLIENT_ID      = {info.get('client_id','')}")
    print(f"GMAIL_CLIENT_SECRET  = {info.get('client_secret','')}")
    print(f"GMAIL_REFRESH_TOKEN  = {creds.refresh_token}")
    print("============================================================")
    print("\n(Keep these secret. They are NOT committed to git.)")


if __name__ == "__main__":
    main()
