"""Download a public Google Sheet as an in-memory .xlsx workbook."""
import io
import re
import requests

_ID_RE = re.compile(r"/spreadsheets/d/([a-zA-Z0-9-_]+)")


def extract_id(url: str) -> str:
    """Pull the spreadsheet ID out of a full Google Sheets URL (or accept a raw ID)."""
    url = (url or "").strip()
    if not url:
        raise ValueError("No Google Sheet URL provided.")
    m = _ID_RE.search(url)
    if m:
        return m.group(1)
    # maybe the user pasted just the ID
    if re.fullmatch(r"[a-zA-Z0-9-_]{20,}", url):
        return url
    raise ValueError("That doesn't look like a Google Sheets URL.")


def download_xlsx(url: str) -> io.BytesIO:
    """
    Returns a BytesIO of the whole workbook exported as .xlsx.
    The sheet must be shared as 'Anyone with the link -> Viewer'.
    """
    sheet_id = extract_id(url)
    export = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=xlsx"
    try:
        r = requests.get(export, timeout=30, allow_redirects=True)
    except requests.RequestException as e:
        raise RuntimeError(f"Could not reach Google Sheets: {e}")

    ctype = r.headers.get("Content-Type", "")
    # Google returns an HTML sign-in page when the sheet isn't public.
    if r.status_code != 200 or "text/html" in ctype:
        raise RuntimeError(
            "Cannot read this sheet. Open it in Google Sheets -> Share -> "
            "'Anyone with the link' -> Viewer, then paste the link again."
        )
    return io.BytesIO(r.content)
