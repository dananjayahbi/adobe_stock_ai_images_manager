"""Read one web page as plain text — for the research agent's deeper passes.

Search snippets are enough to see *that* a niche is discussed; judging whether a
concept is saturated needs the actual page. This module fetches and flattens a
page to text, with two guards that matter more than the extraction itself:

* **A refusal must not read as emptiness.** The same anti-bot interstitial that
  DuckDuckGo serves on search is served on some result pages; it is detected and
  reported as a failure so the agent never concludes "this page says nothing".
* **A URL from a search result is not a trusted URL.** It is model-chosen text
  derived from a third-party page, so only ``http(s)`` is followed and
  loopback/private/link-local hosts are refused. Without that, the "web" tool
  would be a request-forgery primitive pointed at the local network.

Extraction is deliberately crude (strip scripts, styles and tags). The backend
carries no HTML parser dependency, and a readability algorithm would add one for
a feature whose output is fed to a language model, not rendered.
"""

from __future__ import annotations

import html as html_module
import ipaddress
import logging
import re
import socket
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

from services.research.search import (
    MAX_BODY_BYTES,
    USER_AGENT,
    looks_blocked,
)

logger = logging.getLogger(__name__)

#: Longest extract a single page contributes. Long enough for an article's
#: argument, short enough that five fetches cannot swallow the context window.
MAX_TEXT_CHARS = 6_000

#: Only these schemes are followed.
_ALLOWED_SCHEMES = ("http", "https")

_SCRIPT = re.compile(r"<(script|style|noscript|template|svg)\b.*?</\1>", re.S | re.I)
_COMMENT = re.compile(r"<!--.*?-->", re.S)
_BLOCK_TAG = re.compile(
    r"</?(?:p|div|br|li|tr|h[1-6]|section|article|header|footer|blockquote)\b[^>]*>",
    re.S | re.I,
)
_TAG = re.compile(r"<[^>]+>")
_WHITESPACE = re.compile(r"[ \t\r\f\v]+")
_BLANK_LINES = re.compile(r"\n\s*\n+")

#: Hosts never fetched. ``localhost``-style names are checked as well as IP
#: literals, because a name can resolve to a private address.
_BLOCKED_HOSTNAMES = frozenset(
    {"localhost", "localhost.localdomain", "metadata.google.internal"}
)


@dataclass
class PageContent:
    """The outcome of reading one page."""

    url: str
    title: str = ""
    text: str = ""
    ok: bool = True
    error: str = ""
    truncated: bool = False

    def to_dict(self) -> dict:
        payload: dict = {
            "url": self.url,
            "ok": self.ok,
            "title": self.title,
            "chars": len(self.text),
            "truncated": self.truncated,
            "text": self.text,
        }
        if self.error:
            payload["error"] = self.error
        return payload

    def to_tool_text(self) -> str:
        if not self.ok:
            return (
                f"Could not read {self.url}: {self.error}\n"
                "Do not treat this as evidence that the page is empty or "
                "irrelevant — it simply could not be read."
            )
        note = " (truncated)" if self.truncated else ""
        return f"Content of {self.url}{note}:\nTitle: {self.title}\n\n{self.text}"


def _host_is_private(hostname: str) -> bool:
    """Whether a hostname resolves to a non-public address.

    Every resolved address must be public: a name with one public and one
    private record would otherwise be an SSRF bypass.
    """
    if hostname.lower() in _BLOCKED_HOSTNAMES:
        return True
    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        # Unresolvable is refused as well: nothing to fetch, and treating a
        # resolution failure as "public" would let a DNS-rebinding name through.
        return True

    for info in infos:
        address = info[4][0]
        try:
            parsed = ipaddress.ip_address(address)
        except ValueError:
            return True
        if (
            parsed.is_private
            or parsed.is_loopback
            or parsed.is_link_local
            or parsed.is_reserved
            or parsed.is_multicast
            or parsed.is_unspecified
        ):
            return True
    return False


def is_fetchable(url: str) -> tuple[bool, str]:
    """Validate a URL before any request is made.

    Returns ``(ok, reason)``. The reason is shown to the model so it can pick a
    different source instead of retrying the same blocked one.
    """
    candidate = (url or "").strip()
    if not candidate:
        return False, "empty URL"
    try:
        parts = urllib.parse.urlsplit(candidate)
    except ValueError:
        return False, "the URL could not be parsed"
    if parts.scheme.lower() not in _ALLOWED_SCHEMES:
        return False, f"only http/https URLs can be read (got {parts.scheme or 'no scheme'!r})"
    if not parts.hostname:
        return False, "the URL has no host"
    if _host_is_private(parts.hostname):
        return False, "that host is not publicly reachable, so it is not fetched"
    return True, ""


def extract_text(body: str) -> str:
    """Flatten HTML to readable text."""
    without_scripts = _SCRIPT.sub(" ", body or "")
    without_comments = _COMMENT.sub(" ", without_scripts)
    with_breaks = _BLOCK_TAG.sub("\n", without_comments)
    without_tags = _TAG.sub(" ", with_breaks)
    unescaped = html_module.unescape(without_tags)
    spaced = _WHITESPACE.sub(" ", unescaped)
    lines = [line.strip() for line in spaced.split("\n")]
    joined = "\n".join(line for line in lines if line)
    return _BLANK_LINES.sub("\n\n", joined).strip()


def _extract_title(body: str) -> str:
    """Best-effort page title, preferring ``<title>``."""
    match = re.search(r"<title[^>]*>(?P<title>.*?)</title>", body or "", re.S | re.I)
    if match:
        return re.sub(r"\s+", " ", html_module.unescape(match.group("title"))).strip()[:200]
    heading = re.search(r"<h1[^>]*>(?P<h1>.*?)</h1>", body or "", re.S | re.I)
    if heading:
        return extract_text(heading.group("h1"))[:200]
    return ""


def fetch_page(url: str, *, max_chars: int = MAX_TEXT_CHARS, timeout: int = 25) -> PageContent:
    """Fetch one page and return its text, reporting failure explicitly."""
    ok, reason = is_fetchable(url)
    if not ok:
        return PageContent(url=url, ok=False, error=reason)

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,text/plain",
            "Accept-Language": "en-US,en;q=0.9",
        },
        method="GET",
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            content_type = (response.headers.get("content-type") or "").lower()
            raw = response.read(MAX_BODY_BYTES).decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return PageContent(url=url, ok=False, error=f"HTTP {exc.code}")
    except Exception as exc:  # noqa: BLE001 - every failure is a reported step
        logger.warning("Fetch failed for %s: %s", url, exc)
        return PageContent(url=url, ok=False, error=f"{type(exc).__name__}: {exc}")

    if looks_blocked(raw):
        return PageContent(
            url=url, ok=False, error="the site served an anti-bot challenge page"
        )

    if "html" in content_type or "<html" in raw[:2000].lower():
        text = extract_text(raw)
        title = _extract_title(raw)
    else:
        # A plain-text or JSON response is already the content.
        text = raw.strip()
        title = ""

    if not text:
        return PageContent(
            url=url,
            ok=False,
            error="the page loaded but no readable text could be extracted",
        )

    truncated = len(text) > max_chars
    return PageContent(
        url=url,
        title=title,
        text=text[:max_chars],
        truncated=truncated,
    )
