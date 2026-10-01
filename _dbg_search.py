"""Live probe: isolate each provider leg and the tier semantics.

The earlier probe fell all the way through to Google News, which is consistent
with DuckDuckGo being rate-limited from this machine. This checks that leg
directly, so the fallback behaviour is observed provider by provider.
"""

import sys

sys.path.insert(0, "backend")

from services.research import brave  # noqa: E402
from services.research import search as search_module  # noqa: E402

print("=== DuckDuckGo directly ===")
ddg = search_module._duckduckgo("stock photography market trends", limit=3, timeout=25)
print(f"ok={ddg.ok} error={ddg.error!r} results={len(ddg.results)}")

print()
print("=== the Brave leg with an invalid key ===")
b = brave.brave_search("stock photography", api_key="BSA-invalid", limit=3, timeout=20)
print(f"ok={b.ok} error={b.error!r}")

print()
print("=== tier semantics (constructed, no network) ===")
for label, degraded in (("DuckDuckGo", False), ("Google News", True)):
    response = search_module.SearchResponse(
        query="q",
        results=[
            search_module.SearchResult(title="T", url="https://stock.adobe.com/x")
        ],
        provider=label.lower().replace(" ", "_"),
        provider_label=label,
        used_fallback=True,
        degraded_source=degraded,
    )
    text = response.to_tool_text()
    caveat = "news and" in text
    print(
        f"{label:12} used_fallback=True degraded_source={degraded!s:5} "
        f"caveat_shown={caveat}"
    )
