"""Render outbound message text the way WhatsApp itself displays it: plain
URLs become tappable links, and WhatsApp's own `*bold*`/`_italic_` markdown
(used in messages.yaml, e.g. "*Total ₹135.00*") renders as actual
bold/italic instead of showing the literal asterisks/underscores. Used only
by the /sim UI — a real WhatsApp client does this rendering on its own."""

from __future__ import annotations

import re
import uuid

from markupsafe import Markup, escape

_URL_RE = re.compile(r"https?://[^\s<]+")
_BOLD_RE = re.compile(r"\*([^*\n]+)\*")
_ITALIC_RE = re.compile(r"_([^_\n]+)_")


def whatsapp_format(text: str | None) -> Markup:
    if not text:
        return Markup("")
    safe = str(escape(text))

    # Pull URLs out first and replace with a placeholder that contains no
    # '*'/'_' — pay-page tokens routinely contain underscores, which would
    # otherwise get misread as italic markers and corrupt the link.
    links: dict[str, str] = {}

    def _stash_url(m: re.Match) -> str:
        key = f"\x00LINK{uuid.uuid4().hex}\x00"
        url = m.group(0)
        links[key] = f'<a href="{url}" target="_blank" rel="noopener">{url}</a>'
        return key

    safe = _URL_RE.sub(_stash_url, safe)
    safe = _BOLD_RE.sub(r"<b>\1</b>", safe)
    safe = _ITALIC_RE.sub(r"<i>\1</i>", safe)
    for key, html in links.items():
        safe = safe.replace(key, html)
    return Markup(safe)
