"""
Web Search Plugin v1.0.0
Plugin resmi SimpleContext — pencarian internet real-time untuk agen.

Memberi agen akses ke informasi terkini di luar memorinya.
Default provider: DuckDuckGo Instant Answer API (free, no API key).

Cara kerja:
  on_before_llm → jika intent = "knowledge" dan query mengandung trigger word,
                  ambil snippet dari web dan inject ke context sebelum LLM

app_commands:
  /search <query>         — cari dan ringkas hasil
  /search --urls <query>  — kembalikan list URL saja

Config di config.yaml:
    plugins:
      web_search_plugin:
        enabled: true
        provider: duckduckgo       # duckduckgo | bing | google
        bing_api_key: ""           # untuk provider=bing
        google_api_key: ""         # untuk provider=google
        google_cx: ""              # Google Custom Search Engine ID
        max_results: 3             # jumlah hasil maksimum
        max_snippet_chars: 400     # panjang snippet per hasil
        cache_ttl: 300             # cache hasil selama N detik (0 = no cache)
        auto_search: true          # otomatis search saat intent=knowledge
        trigger_words:             # kata yang trigger auto-search
          - what is
          - how to
          - apa itu
          - bagaimana cara
          - latest
          - terbaru
          - 2024
          - 2025
          - 2026
"""

import json
import time
import logging
import urllib.request
import urllib.parse
import urllib.error

from simplecontext.plugins.base import BasePlugin, AppCommandContext

logger = logging.getLogger(__name__)


def _fetch_json(url: str, headers: dict = None, timeout: int = 8) -> dict | None:
    """Fetch JSON dari URL. Return dict atau None jika gagal."""
    try:
        req = urllib.request.Request(url, headers=headers or {
            "User-Agent": "SimpleContext-Bot/1.0 (compatible)"
        })
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        logger.warning(f"[web_search] Fetch failed: {e}")
        return None


# ── Search Providers ──────────────────────────────────────

def _search_duckduckgo(query: str, max_results: int) -> list[dict]:
    """DuckDuckGo Instant Answer API — free, no key needed."""
    encoded = urllib.parse.quote(query)
    url     = f"https://api.duckduckgo.com/?q={encoded}&format=json&no_html=1&skip_disambig=1"
    data    = _fetch_json(url)

    if not data:
        return []

    results = []

    # Abstract (best result)
    if data.get("AbstractText"):
        results.append({
            "title":   data.get("Heading", ""),
            "snippet": data["AbstractText"],
            "url":     data.get("AbstractURL", ""),
        })

    # Answer (instant answers like calculations)
    if data.get("Answer") and len(results) < max_results:
        results.append({
            "title":   "Direct Answer",
            "snippet": data["Answer"],
            "url":     "",
        })

    # Related topics
    for topic in data.get("RelatedTopics", []):
        if len(results) >= max_results:
            break
        if isinstance(topic, dict) and topic.get("Text"):
            results.append({
                "title":   topic.get("Text", "")[:80],
                "snippet": topic.get("Text", ""),
                "url":     topic.get("FirstURL", ""),
            })

    return results[:max_results]


def _search_bing(query: str, api_key: str, max_results: int) -> list[dict]:
    """Bing Web Search API."""
    encoded = urllib.parse.quote(query)
    url     = f"https://api.bing.microsoft.com/v7.0/search?q={encoded}&count={max_results}"
    data    = _fetch_json(url, headers={
        "Ocp-Apim-Subscription-Key": api_key,
        "User-Agent": "SimpleContext-Bot/1.0",
    })

    if not data:
        return []

    results = []
    for item in data.get("webPages", {}).get("value", [])[:max_results]:
        results.append({
            "title":   item.get("name", ""),
            "snippet": item.get("snippet", ""),
            "url":     item.get("url", ""),
        })
    return results


def _search_google(query: str, api_key: str, cx: str, max_results: int) -> list[dict]:
    """Google Custom Search JSON API."""
    encoded = urllib.parse.quote(query)
    url     = (
        f"https://www.googleapis.com/customsearch/v1"
        f"?key={api_key}&cx={cx}&q={encoded}&num={min(max_results, 10)}"
    )
    data = _fetch_json(url)

    if not data:
        return []

    results = []
    for item in data.get("items", [])[:max_results]:
        results.append({
            "title":   item.get("title", ""),
            "snippet": item.get("snippet", ""),
            "url":     item.get("link", ""),
        })
    return results


class WebSearchPlugin(BasePlugin):
    """Pencarian internet real-time untuk SimpleContext."""

    name        = "web_search_plugin"
    version     = "1.0.0"
    description = "Pencarian internet real-time — DuckDuckGo (free), Bing, atau Google."
    depends_on  = []

    app_commands = {
        "search": {
            "description": "Cari informasi dari internet",
            "usage":       "/search <query> | /search --urls <query>",
            "handler":     "handle_search",
            "args_hint":   "<query>",
        },
    }

    # ── Lifecycle ─────────────────────────────────────────

    def setup(self):
        self._provider      = self.config.get("provider", "duckduckgo")
        self._bing_key      = self.config.get("bing_api_key", "")
        self._google_key    = self.config.get("google_api_key", "")
        self._google_cx     = self.config.get("google_cx", "")
        self._max_results   = int(self.config.get("max_results", 3))
        self._max_snippet   = int(self.config.get("max_snippet_chars", 400))
        self._cache_ttl     = int(self.config.get("cache_ttl", 300))
        self._auto_search   = self.config.get("auto_search", True)
        self._trigger_words = [w.lower() for w in self.config.get("trigger_words", [
            "what is", "how to", "apa itu", "bagaimana cara",
            "latest", "terbaru", "2025", "2026",
        ])]
        logger.info(f"[web_search] Initialized — provider={self._provider} auto={self._auto_search}")

    # ── Core Search ───────────────────────────────────────

    def _search(self, query: str) -> list[dict]:
        """Jalankan search dengan provider yang dikonfigurasi."""
        # Cek cache
        if self._cache_ttl > 0:
            cache_key = f"cache:{hash(query.lower())}"
            cached    = self.state.get(cache_key)
            if cached and isinstance(cached, dict):
                ts = cached.get("ts", 0)
                if time.time() - ts < self._cache_ttl:
                    logger.debug(f"[web_search] Cache hit: {query[:40]!r}")
                    return cached.get("results", [])

        # Search
        if self._provider == "bing" and self._bing_key:
            results = _search_bing(query, self._bing_key, self._max_results)
        elif self._provider == "google" and self._google_key and self._google_cx:
            results = _search_google(query, self._google_key, self._google_cx, self._max_results)
        else:
            results = _search_duckduckgo(query, self._max_results)

        # Trim snippet
        for r in results:
            if len(r.get("snippet", "")) > self._max_snippet:
                r["snippet"] = r["snippet"][:self._max_snippet] + "..."

        # Save ke cache
        if self._cache_ttl > 0 and results:
            self.state.set(f"cache:{hash(query.lower())}", {
                "ts": time.time(), "results": results
            })

        self.state.increment("total_searches")
        return results

    def _should_auto_search(self, query: str) -> bool:
        """Cek apakah query harus di-search otomatis."""
        if not self._auto_search:
            return False
        q = query.lower()
        return any(tw in q for tw in self._trigger_words)

    def _format_for_context(self, results: list[dict]) -> str:
        """Format hasil search untuk inject ke context."""
        if not results:
            return ""
        lines = ["[Web Search Results]"]
        for i, r in enumerate(results, 1):
            title   = r.get("title", "")
            snippet = r.get("snippet", "")
            url     = r.get("url", "")
            line    = f"{i}. {title}: {snippet}"
            if url:
                line += f" ({url})"
            lines.append(line)
        return "\n".join(lines)

    # ── Hooks ─────────────────────────────────────────────

    def on_before_llm(self, user_id: str, agent_id: str,
                      messages: list[dict]) -> list[dict]:
        """
        Auto-search jika query mengandung trigger word.
        Inject hasil ke system message sebelum LLM dipanggil.
        """
        if not messages:
            return messages

        # Ambil query dari pesan user terakhir
        query = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                c = msg.get("content", "")
                query = c if isinstance(c, str) else str(c)
                break

        if not query or not self._should_auto_search(query):
            return messages

        results = self._search(query)
        if not results:
            return messages

        context_text = self._format_for_context(results)
        if messages[0]["role"] == "system":
            messages[0]["content"] += f"\n\n{context_text}"
        else:
            messages.insert(0, {"role": "system", "content": context_text})

        logger.debug(f"[web_search] Injected {len(results)} results for: {query[:40]!r}")
        return messages

    # ── App Command Handlers ───────────────────────────────

    async def handle_search(self, ctx: AppCommandContext) -> str:
        """
        /search <query>          → cari dan tampilkan snippets
        /search --urls <query>   → tampilkan URL saja
        """
        args  = ctx.args
        if not args:
            return (
                "🔍 *Web Search*\n\n"
                "Usage:\n"
                "  `/search <query>` — cari dan ringkas hasil\n"
                "  `/search --urls <query>` — tampilkan URL saja\n\n"
                "Contoh:\n"
                "  `/search cara deploy django ke VPS`\n"
                "  `/search --urls python async tutorial`"
            )

        urls_only = False
        if args[0] == "--urls":
            urls_only = True
            args      = args[1:]

        query   = " ".join(args).strip()
        if not query:
            return "❌ Masukkan query pencarian."

        results = self._search(query)

        if not results:
            return f"🔍 Tidak ada hasil untuk: *{query}*"

        total = self.state.get("total_searches", 0)

        if urls_only:
            lines = [f"🔗 *URLs for:* `{query}`\n"]
            for i, r in enumerate(results, 1):
                url   = r.get("url", "—")
                title = r.get("title", "")[:60]
                lines.append(f"{i}. [{title}]({url})" if url else f"{i}. {title}")
            lines.append(f"\n_Search #{total}_")
            return "\n".join(lines)

        lines = [f"🔍 *Search results for:* `{query}`\n"]
        for i, r in enumerate(results, 1):
            title   = r.get("title", "")
            snippet = r.get("snippet", "")
            url     = r.get("url", "")
            lines.append(
                f"*{i}. {title}*\n"
                f"_{snippet}_"
                + (f"\n{url}" if url else "")
            )
        lines.append(f"\n_Search #{total} · Provider: {self._provider}_")
        return "\n\n".join(lines)
