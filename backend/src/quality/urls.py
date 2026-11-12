"""URL normalisation shared by the report quality checks.

Only used for comparison; the original URL is always kept for display.
"""
from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlsplit

LOCAL_PREFIX = "local://documents/"

# Query parameters that never change which document is referenced.
_TRACKING_EXACT = {
    "fbclid", "gclid", "igshid", "mc_cid", "mc_eid", "ref", "ref_src",
    "spm", "share_token", "from", "source",
}
_TRACKING_PREFIXES = ("utm_",)


def is_local(url: str | None) -> bool:
    return bool(url) and url.startswith(LOCAL_PREFIX)


def local_document_id(url: str) -> str:
    return url[len(LOCAL_PREFIX):] if is_local(url) else ""


def make_local_url(document_id: str) -> str:
    return f"{LOCAL_PREFIX}{document_id}"


def _is_tracking(key: str) -> bool:
    lowered = key.lower()
    return lowered in _TRACKING_EXACT or any(
        lowered.startswith(prefix) for prefix in _TRACKING_PREFIXES
    )


def normalize(url: str) -> str:
    """Return a stable comparison key for a citation URL.

    local://document URLs collapse to ``local:<id>``; http(s) URLs lose the
    fragment, tracking parameters, ``www.`` and trailing slashes, and http is
    treated as equal to https.
    """
    if not url:
        return ""
    url = url.strip()
    if is_local(url):
        return f"local:{local_document_id(url)}"
    if not url.lower().startswith(("http://", "https://")):
        return url.lower()

    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    port = f":{parts.port}" if parts.port else ""
    path = parts.path.rstrip("/")
    query = urlencode(
        sorted(
            (key, value)
            for key, value in parse_qsl(parts.query, keep_blank_values=True)
            if not _is_tracking(key)
        )
    )
    return f"https://{host}{port}{path}" + (f"?{query}" if query else "")


def domain(url: str) -> str:
    """Return a display-friendly host for a URL."""
    if is_local(url):
        return "本地资料库"
    try:
        host = (urlsplit(url).hostname or "").lower()
    except ValueError:
        return ""
    return host[4:] if host.startswith("www.") else host


def is_http(url: str | None) -> bool:
    return bool(url) and url.lower().startswith(("http://", "https://"))
