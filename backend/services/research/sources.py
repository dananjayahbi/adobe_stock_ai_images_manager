"""Operator-supplied priority sources — sites the agent should prefer.

Why this exists
---------------
The general web search is a fallback chain, and a fallback chain fails as a unit:
when the primary provider is rate-limited or serves an anti-bot page the agent
gets editorial coverage instead of the catalogue pages it actually needs. Measured
live: a research run on a stock-photography niche returned *Google News* articles
for every query, and reported "0 of 16 stock marketplaces" — which reads as an
empty market but is really a search that never reached a marketplace.

The operator knows which sites carry the evidence. This module lets them say so in
a file, and then:

* the agent is told those sites are authoritative, so a result from one is trusted
  over a general hit;
* a query can be **restricted to those sites** (`site:` operators), which is the
  only way to reach them when the general index is blocked;
* the agent is told to *fetch* a listed site's page rather than settle for a
  snippet, because the catalogue counts live on the page, not in a search result.

The format
----------
JSON, deliberately simple, and versioned so a future change can migrate rather
than silently misread an old file::

    {
      "version": 1,
      "sources": [
        {
          "url": "https://stock.adobe.com/search",
          "name": "Adobe Stock search",
          "priority": 1,
          "notes": "Catalogue counts appear in the results header.",
          "tags": ["marketplace", "catalogue"]
        }
      ]
    }

Every field but ``url`` is optional: a bare list of URLs is a valid file, because
the operator's first instinct is to paste links and a format that rejects that is
a format they will not use. The parser is tolerant of a bare list, of
``{"sources": [...]}``, and of a single object, and reports *why* a file was
rejected rather than accepting it silently.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from urllib.parse import urlparse

#: The format version this module writes and understands.
SCHEMA_VERSION = 1

#: Most sources one file may declare. A cap because every source becomes part of
#: the system prompt, and a hundred of them would crowd out the instructions.
MAX_SOURCES = 40

#: Longest accepted field values, so a file cannot smuggle a huge blob into the
#: prompt through a "note".
MAX_NAME_CHARS = 80
MAX_NOTES_CHARS = 300
MAX_TAGS = 6

#: Total characters of rendered source guidance. Bounded like the summariser input
#: for the same reason: this text is prepended to every request in the run.
MAX_RENDERED_CHARS = 4_000

#: Only these schemes are accepted. A ``file:`` or ``javascript:`` URL in the list
#: would be handed to the fetch tool, so the allow-list is a security boundary and
#: not a formatting preference.
_ALLOWED_SCHEMES = frozenset({"http", "https"})


@dataclass(frozen=True)
class PrioritySource:
    """One site the operator wants preferred."""

    url: str
    name: str = ""
    #: Lower is more important. 1 is the default so an unranked file is still
    #: ordered deterministically rather than by insertion accident.
    priority: int = 1
    notes: str = ""
    tags: tuple[str, ...] = ()

    @property
    def host(self) -> str:
        """The bare host, used for the ``site:`` query operator."""
        return (urlparse(self.url).hostname or "").removeprefix("www.")

    @property
    def label(self) -> str:
        """A short human name, falling back to the host."""
        return self.name or self.host or self.url

    def to_dict(self) -> dict:
        return {
            "url": self.url,
            "name": self.name,
            "priority": self.priority,
            "notes": self.notes,
            "tags": list(self.tags),
        }


@dataclass
class SourceSet:
    """A parsed source file, plus whatever the operator must be told about it."""

    sources: list[PrioritySource] = field(default_factory=list)
    #: Non-fatal remarks: an entry that was dropped, a field that was trimmed.
    warnings: list[str] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not self.sources

    @property
    def hosts(self) -> list[str]:
        """Distinct hosts, most important first."""
        seen: list[str] = []
        for source in self.sorted():
            if source.host and source.host not in seen:
                seen.append(source.host)
        return seen

    def sorted(self) -> list[PrioritySource]:
        """Sources by priority, then by host, so the order is stable."""
        return sorted(self.sources, key=lambda item: (item.priority, item.host))

    def to_dict(self) -> dict:
        return {
            "version": SCHEMA_VERSION,
            "sources": [source.to_dict() for source in self.sorted()],
            "warnings": list(self.warnings),
        }


class SourceFileError(ValueError):
    """The file could not be read as a source list.

    Carries the operator-facing reason, because a silent rejection of a file the
    operator just uploaded is indistinguishable from the upload not working.
    """


def template() -> dict:
    """The example file the operator downloads.

    A template rather than prose documentation: the operator asked to be able to
    download the exact format, and a file that can be uploaded unchanged (and that
    demonstrably parses) is a better specification than a description of one.
    """
    return {
        "version": SCHEMA_VERSION,
        "sources": [
            {
                "url": "https://stock.adobe.com/search",
                "name": "Adobe Stock search",
                "priority": 1,
                "notes": (
                    "The results header shows the catalogue count. Open the page to "
                    "read it; a search snippet does not contain it."
                ),
                "tags": ["marketplace", "catalogue"],
            },
            {
                "url": "https://www.shutterstock.com/search",
                "name": "Shutterstock search",
                "priority": 1,
                "notes": "Shows a total-results figure for a query.",
                "tags": ["marketplace", "catalogue"],
            },
            {
                "url": "https://stock.adobe.com/uk/contributor",
                "name": "Adobe Stock contributor guidance",
                "priority": 2,
                "notes": "Authoritative on what Adobe accepts and refuses.",
                "tags": ["policy"],
            },
            {
                "url": "https://trends.google.com/trends/explore",
                "name": "Google Trends",
                "priority": 3,
                "notes": "Relative interest over time. A direction, not a volume.",
                "tags": ["demand"],
            },
        ],
    }


def template_json() -> str:
    """The template as pretty-printed JSON, for the download endpoint."""
    return json.dumps(template(), indent=2, ensure_ascii=False) + "\n"


def _clean_text(value: object, limit: int) -> str:
    """Collapse whitespace and bound a free-text field."""
    if not isinstance(value, str):
        return ""
    return " ".join(value.split())[:limit]


def _clean_priority(value: object) -> int:
    """A positive integer priority; anything else falls back to 1."""
    try:
        number = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 1
    return max(1, min(99, number))


def _clean_tags(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    cleaned = [
        " ".join(str(item).split())[:24]
        for item in value[:MAX_TAGS]
        if str(item).strip()
    ]
    return tuple(tag for tag in cleaned if tag)


def normalise_url(raw: object) -> str:
    """Validate and tidy one URL, or return ``""`` when it is unusable.

    The scheme allow-list is a security boundary: these URLs are handed to the
    fetch tool, so ``file:`` or ``javascript:`` must never reach it.
    """
    text = _clean_text(raw, 500)
    if not text:
        return ""
    # A bare host is a common thing to paste; assume https rather than reject it.
    if "://" not in text:
        text = f"https://{text}"
    parsed = urlparse(text)
    if parsed.scheme.lower() not in _ALLOWED_SCHEMES:
        return ""
    if not parsed.hostname or "." not in parsed.hostname:
        return ""
    # Drop the fragment: it never changes what a fetch returns, and it makes two
    # entries for the same page look like two sources.
    return parsed._replace(fragment="").geturl()


def parse(payload: object) -> SourceSet:
    """Parse a decoded JSON payload into a :class:`SourceSet`.

    Accepts the documented object, a bare list of URLs or objects, and a single
    object. Raises :class:`SourceFileError` with an operator-readable reason when
    nothing usable is present — a file that uploads and silently does nothing is
    the failure mode this avoids.
    """
    warnings: list[str] = []

    if isinstance(payload, list):
        entries = payload
    elif isinstance(payload, dict):
        declared = payload.get("version")
        if declared is not None and declared != SCHEMA_VERSION:
            warnings.append(
                f"The file declares version {declared!r}; this tool reads version "
                f"{SCHEMA_VERSION}. It was read as version {SCHEMA_VERSION}."
            )
        raw_sources = payload.get("sources")
        if raw_sources is None:
            # A single source object, which is what a hand-written file often is.
            entries = [payload] if payload.get("url") else []
        elif isinstance(raw_sources, list):
            entries = raw_sources
        else:
            raise SourceFileError(
                "'sources' must be a list of source objects, or a bare list of URLs."
            )
    else:
        raise SourceFileError(
            "The file must contain a JSON object or a list of sources."
        )

    sources: list[PrioritySource] = []
    seen: set[str] = set()
    dropped = 0
    for entry in entries[: MAX_SOURCES * 2]:
        if isinstance(entry, str):
            url = normalise_url(entry)
            name, priority, notes, tags = "", 1, "", ()
        elif isinstance(entry, dict):
            url = normalise_url(entry.get("url") or entry.get("site") or entry.get("host"))
            name = _clean_text(entry.get("name") or entry.get("label"), MAX_NAME_CHARS)
            priority = _clean_priority(entry.get("priority", 1))
            notes = _clean_text(entry.get("notes") or entry.get("note"), MAX_NOTES_CHARS)
            tags = _clean_tags(entry.get("tags"))
        else:
            dropped += 1
            continue

        if not url:
            dropped += 1
            continue
        if url in seen:
            # De-duplicated rather than reported: the same page listed twice is
            # usually a copy-paste, and a warning for it would be noise.
            continue
        seen.add(url)
        sources.append(
            PrioritySource(
                url=url, name=name, priority=priority, notes=notes, tags=tags
            )
        )
        if len(sources) >= MAX_SOURCES:
            warnings.append(
                f"Only the first {MAX_SOURCES} sources are used; the rest were ignored."
            )
            break

    if dropped:
        warnings.append(
            f"{dropped} entr{'y was' if dropped == 1 else 'ies were'} skipped — a "
            "source needs an http(s) URL, for example "
            '{"url": "https://stock.adobe.com/search"}.'
        )
    if not sources:
        raise SourceFileError(
            "No usable sources were found. Each source needs an http(s) URL, for "
            'example {"url": "https://stock.adobe.com/search"}.'
        )

    result = SourceSet(sources=sources, warnings=warnings)
    result.sources = result.sorted()
    return result


def parse_text(text: str) -> SourceSet:
    """Parse a file's text, converting a JSON fault into an operator message."""
    raw = (text or "").strip()
    if not raw:
        raise SourceFileError("The file is empty.")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SourceFileError(
            f"The file is not valid JSON (line {exc.lineno}, column {exc.colno}): "
            f"{exc.msg}. Download the template to see the expected shape."
        ) from exc
    return parse(payload)


def guidance(source_set: SourceSet | None) -> str:
    """The system-prompt section describing the operator's priority sources.

    Empty when there are none, so a run without a source file is byte-identical to
    one from before this feature existed.

    Written as *behaviour* rather than a list: naming the sites is not enough,
    because the agent's default behaviour — search, read the snippets, answer — is
    exactly what misses them. It has to be told to restrict its query and to open
    the page.
    """
    if source_set is None or source_set.is_empty:
        return ""

    lines: list[str] = [
        "PRIORITY SOURCES (the operator supplied these; they outrank general results)",
        "These sites carry the evidence for this task. A finding from one of them is "
        "stronger evidence than a general search hit, and a general result that "
        "contradicts one of them is the one to doubt.",
        "",
        "How to use them:",
        "- To reach them when the general index is thin, RESTRICT the query to them "
        "with the `site:` operator, for example: "
        f"`web_search` with query `warehouse robots site:{source_set.hosts[0]}`. "
        "Several hosts can be chained with OR.",
        "- When a listed site is the source of a claim, OPEN the page with "
        "`fetch_page` rather than relying on a snippet. Catalogue counts, result "
        "totals and policy text live on the page, not in a search result.",
        "- Say which source a figure came from, and say so plainly when a priority "
        "source could not be reached — an unreachable source is not an empty one.",
        "",
        "The sites, most important first:",
    ]
    for source in source_set.sorted():
        entry = f"- {source.label} — {source.url}"
        if source.notes:
            entry += f"\n    {source.notes}"
        lines.append(entry)

    rendered = "\n".join(lines)
    # Bounded: this text goes into every request of the run.
    if len(rendered) > MAX_RENDERED_CHARS:
        rendered = rendered[:MAX_RENDERED_CHARS].rstrip() + "\n[… source list truncated …]"
    return rendered


def queries_for(source_set: SourceSet | None, query: str) -> list[str]:
    """Restricted variants of a query, for the agent to use when the index is thin.

    Returned as data (not applied automatically) because *when* to restrict is a
    judgement: a restricted query that returns nothing must not be mistaken for an
    absence of competition, and only the agent knows whether the general result
    was adequate.
    """
    if source_set is None or source_set.is_empty:
        return []
    hosts = source_set.hosts[:4]
    if not hosts:
        return []
    return [f"{query} site:{host}" for host in hosts]


#: Query separators that must never survive into a ``site:`` expression, or an
#: operator's note could smuggle a second query into the restricted one.
_UNSAFE_QUERY = re.compile(r"[\r\n]")


def sanitise_query(query: str) -> str:
    """Strip newlines from a query before it is combined with a ``site:`` clause."""
    return _UNSAFE_QUERY.sub(" ", query or "").strip()
