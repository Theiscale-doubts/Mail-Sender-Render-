# -*- coding: utf-8 -*-
"""
Branded HTML "base template" for The iScale emails.

The composer/config still stores a plain-text body (what you edit). At send
time we wrap that text into this responsive, email-client-safe HTML shell so the
message lands looking professional, while the raw text is kept as the plain-text
fallback part of the multipart/alternative message.

Design matches The iScale reference: deep-maroon gradient header, a
"SESSION REMINDER" pill, a waving-hand greeting, a rose callout box, a
"HOW TO JOIN" section with maroon numbered circle badges, and a footer.

Usage:
    from email_template import render_html
    html_body = render_html(plain_text_body)
"""
import re
import html

# Brand palette (deep maroon / burgundy)
PRIMARY = "#8a1c34"
PRIMARY_DARK = "#5a0f1e"
INK = "#2b2f36"
MUTED = "#6b7280"
BG = "#faf1f2"
CARD = "#ffffff"
CALLOUT_BG = "#fdecef"

# Fixed header — always rendered exactly like this, independent of the body text.
BRAND = "The iScale"
TAGLINE = "Simplifying Learning for Every Curious Mind"
BADGE_TEXT = "Session Reminder"

# Fixed footer — always rendered exactly like this, independent of the body text.
FOOTER_LINES = [
    "Have questions? Reach us at doubts@theiscale.com",
    "Visit us at www.theiscale.com",
    "© 2025 The iScale. All rights reserved.",
]

# Key phrases that get bolded wherever they appear (matches the reference look)
KEY_PHRASES = [
    "Live Doubt Class",
    "Enrolled Courses → Start Courses",
    "Start Courses",
    "Live Classes",
    "Batch Tile",
]

_URL_RE = re.compile(r"((?:https?://|www\.)[^\s<>()]+)", re.I)
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_STEP_RE = re.compile(r"^\s*(\d+)[.)]?\s+(.*)$")


def _esc(s):
    return html.escape(s, quote=False)


def _bold_keyphrases(escaped):
    for phrase in KEY_PHRASES:
        esc_phrase = _esc(phrase)
        escaped = escaped.replace(
            esc_phrase, f'<strong style="color:{INK};">{esc_phrase}</strong>'
        )
    return escaped


def _linkify(escaped):
    """Turn URLs and emails in already-escaped text into styled anchors."""
    def _email_sub(m):
        addr = m.group(0)
        return (f'<a href="mailto:{addr}" '
                f'style="color:{PRIMARY};font-weight:600;text-decoration:none;">'
                f'{addr}</a>')

    def _url_sub(m):
        raw = m.group(1)
        href = raw if raw.lower().startswith("http") else "https://" + raw
        return (f'<a href="{href}" '
                f'style="color:{PRIMARY};font-weight:600;text-decoration:underline;">'
                f'{raw}</a>')

    escaped = _EMAIL_RE.sub(_email_sub, escaped)
    escaped = _URL_RE.sub(_url_sub, escaped)
    return escaped


def _rich(text):
    """Escape -> bold key phrases -> linkify."""
    return _linkify(_bold_keyphrases(_esc(text)))


def _step_html(number, text):
    return (
        f'<table role="presentation" cellpadding="0" cellspacing="0" '
        f'style="margin:0 0 14px 0;width:100%;"><tr>'
        f'<td width="30" valign="top">'
        f'<div style="width:26px;height:26px;border-radius:50%;background:{PRIMARY};'
        f'color:#ffffff;text-align:center;line-height:26px;font-size:13px;'
        f'font-weight:700;">{number}</div></td>'
        f'<td style="padding-left:12px;font-size:15px;color:{INK};line-height:1.55;">'
        f'{text}</td></tr></table>'
    )


def _callout_html(text):
    # bold the first sentence, like the reference
    esc = _bold_keyphrases(_esc(text))
    m = re.match(r"(.+?[.!?])(\s+)(.*)", esc, re.S)
    if m:
        inner = (f'<strong style="color:{PRIMARY_DARK};">{m.group(1)}</strong>'
                 f'{m.group(2)}{m.group(3)}')
    else:
        inner = esc
    inner = _linkify(inner)
    return (
        f'<div style="margin:20px 0;padding:14px 18px;background:{CALLOUT_BG};'
        f'border-left:4px solid {PRIMARY};border-radius:6px;color:{INK};'
        f'font-size:15px;line-height:1.6;">{inner}</div>'
    )


def _parse(body_text):
    """Split the plain-text body into body + footer HTML.

    The brand name, tagline and the 📅 line are dropped here — they always
    live in the fixed header, so we never render them (or the subject) again
    inside the message body.
    """
    lines = [ln.rstrip() for ln in body_text.replace("\r\n", "\n").split("\n")]
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()

    # drop a leading brand / tagline line if the body repeats the header
    if lines and lines[0].strip().lower() == BRAND.lower():
        lines.pop(0)
    if lines and lines[0].strip().lower() == TAGLINE.lower():
        lines.pop(0)

    body_parts = []
    steps = []
    step_open = False

    def flush_steps():
        nonlocal steps, step_open
        if steps:
            for i, s in enumerate(steps, 1):
                body_parts.append(_step_html(i, s))
            steps = []
        step_open = False

    for ln in lines:
        stripped = ln.strip()
        m = _STEP_RE.match(ln)
        if m:
            steps.append(_rich(m.group(2)))
            step_open = True
            continue
        if step_open:
            flush_steps()

        if not stripped:
            continue

        low = stripped.lower()
        if stripped.startswith("📅"):
            # the 📅 line belongs to the fixed header pill — never in the body
            continue
        elif stripped.startswith("👋"):
            body_parts.append(
                f'<h1 style="margin:0 0 14px 0;font-size:22px;color:{INK};'
                f'font-weight:800;">{_rich(stripped)}</h1>'
            )
        elif low.startswith("how to join"):
            body_parts.append(
                f'<div style="margin:26px 0 14px 0;font-size:14px;color:{PRIMARY_DARK};'
                f'font-weight:800;letter-spacing:1.5px;text-transform:uppercase;">'
                f'{_esc(stripped)}</div>'
            )
        elif low.startswith(("have questions", "visit us")) or stripped.startswith("©"):
            # footer lines belong to the fixed footer — never in the body
            continue
        elif stripped[:1] in "🔔⚠🎯⏰📢✨":
            body_parts.append(_callout_html(stripped))
        else:
            body_parts.append(
                f'<p style="margin:12px 0;font-size:15px;color:{INK};'
                f'line-height:1.6;">{_rich(stripped)}</p>'
            )

    flush_steps()
    return "".join(body_parts)


def render_html(body_text, recipient=None):
    """Wrap a plain-text body into the branded HTML base template.

    The maroon header (brand / tagline / SESSION REMINDER) and the footer are
    always the same fixed blocks below — they never change with the body, and
    the subject line is not shown inside the message.
    """
    body_html = _parse(body_text or "")
    footer_html = "".join(
        f'<p style="margin:3px 0;font-size:13px;color:{MUTED};'
        f'line-height:1.6;">{_rich(line)}</p>'
        for line in FOOTER_LINES
    )

    tagline_html = (
        f'<div style="margin:8px 0 0 0;font-size:12px;color:#f3d6db;'
        f'letter-spacing:2px;text-transform:uppercase;font-weight:600;">'
        f'{_esc(TAGLINE)}</div>'
    )
    divider_html = (
        '<div style="width:44px;height:2px;background:rgba(255,255,255,0.45);'
        'margin:18px auto;"></div>'
    )
    badge_html = (
        f'<div style="display:inline-block;padding:9px 22px;'
        f'background:rgba(255,255,255,0.14);border:1px solid rgba(255,255,255,0.35);'
        f'border-radius:22px;color:#ffffff;font-size:12px;font-weight:700;'
        f'letter-spacing:1.5px;text-transform:uppercase;">📅 {_esc(BADGE_TEXT)}</div>'
    )

    footer_block = (
        f'<tr><td style="padding:18px 40px 30px 40px;border-top:1px solid #f0e3e5;'
        f'text-align:center;">{footer_html}</td></tr>'
    )

    return f"""\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{_esc(BRAND)}</title>
</head>
<body style="margin:0;padding:0;background:{BG};">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0"
       style="background:{BG};padding:26px 12px;">
  <tr><td align="center">
    <table role="presentation" width="600" cellpadding="0" cellspacing="0"
           style="max-width:600px;width:100%;background:{CARD};border-radius:14px;
                  overflow:hidden;box-shadow:0 6px 20px rgba(90,15,30,0.10);
                  font-family:'Segoe UI',Arial,Helvetica,sans-serif;">
      <!-- header -->
      <tr><td style="background:linear-gradient(135deg,{PRIMARY} 0%,{PRIMARY_DARK} 100%);
                     padding:36px 32px 30px 32px;text-align:center;">
        <div style="font-size:28px;font-weight:800;color:#ffffff;
                    letter-spacing:0.3px;">{_esc(BRAND)}</div>
        {tagline_html}
        {divider_html}
        {badge_html}
      </td></tr>
      <!-- body -->
      <tr><td style="padding:30px 40px 12px 40px;">
        {body_html}
      </td></tr>
      {footer_block}
    </table>
  </td></tr>
</table>
</body>
</html>"""
