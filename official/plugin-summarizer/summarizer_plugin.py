"""
Summarizer Plugin v1.0.0
Plugin resmi SimpleContext — ringkasan otomatis percakapan ke episodic memory.

Mengapa penting:
  Working memory terus bertambah → context window penuh → retrieval noise.
  Plugin ini compress pesan lama jadi ringkasan episodic yang compact dan
  informatif, sehingga context tetap segar tanpa kehilangan informasi penting.

Cara kerja:
  on_message_saved → hitung pesan, trigger jika > threshold
  on_before_llm    → sisipkan ringkasan terakhir ke konteks jika ada

app_commands:
  /summary              — ringkas percakapan hari ini
  /summary last <N>     — ringkas N pesan terakhir
  /summary_list         — lihat semua ringkasan tersimpan

Config di config.yaml:
    plugins:
      summarizer_plugin:
        enabled: true
        threshold: 20            # auto-trigger setelah N pesan user
        keep_last: 5             # pertahankan N pesan terbaru setelah compress
        llm_provider: gemini     # gemini | openai | ollama
        llm_model: ""            # kosong = pakai default per provider
        llm_api_key: ""
        llm_base_url: ""         # untuk ollama
        language: auto           # auto | en | id
        max_tokens: 300          # panjang maksimum ringkasan
        inject_last_summary: true # inject ringkasan terakhir ke konteks
"""

import logging
from datetime import datetime, timezone

from simplecontext.plugins.base import BasePlugin, AppCommandContext

logger = logging.getLogger(__name__)

# ── Prompt Templates ──────────────────────────────────────

_PROMPT_EN = """Summarize this conversation for long-term memory. Capture:
1. Key facts about the user (name, skills, projects, preferences)
2. Important topics discussed
3. Decisions made or tasks identified
4. Context useful for future conversations

Write in third person. Be specific. Skip pleasantries. Max {max_tokens} words.

CONVERSATION:
{conversation}

SUMMARY:"""

_PROMPT_ID = """Ringkas percakapan ini untuk memori jangka panjang. Tangkap:
1. Fakta penting tentang user (nama, keahlian, proyek, preferensi)
2. Topik penting yang dibahas
3. Keputusan atau tugas yang diidentifikasi
4. Konteks yang berguna untuk percakapan mendatang

Tulis dengan sudut pandang ketiga. Spesifik. Tanpa basa-basi. Maks {max_tokens} kata.

PERCAKAPAN:
{conversation}

RINGKASAN:"""

_DEFAULT_MODELS = {
    "gemini": "gemini/gemini-2.0-flash",
    "openai": "gpt-4o-mini",
    "ollama": "llama3",
}

_ID_STOPWORDS = {"yang", "dan", "di", "ke", "dari", "ini", "itu", "adalah", "saya", "aku", "kamu"}


def _detect_lang(text: str) -> str:
    words = set(text.lower().split())
    return "id" if len(words & _ID_STOPWORDS) >= 2 else "en"


def _call_llm(provider: str, model: str, api_key: str,
               base_url: str, prompt: str, max_tokens: int) -> str | None:
    try:
        import litellm
        kwargs: dict = {"model": model, "messages": [{"role": "user", "content": prompt}],
                        "max_tokens": max_tokens}
        if provider == "ollama":
            kwargs["api_base"] = base_url or "http://localhost:11434"
            if not model.startswith("ollama/"):
                kwargs["model"] = f"ollama/{model}"
        elif api_key:
            kwargs["api_key"] = api_key
        return litellm.completion(**kwargs).choices[0].message.content.strip()
    except ImportError:
        logger.warning("[summarizer] litellm not installed")
        return None
    except Exception as e:
        logger.warning(f"[summarizer] LLM error: {e}")
        return None


class SummarizerPlugin(BasePlugin):
    """Auto-compress working memory ke episodic summary via LLM."""

    name        = "summarizer_plugin"
    version     = "1.0.0"
    description = "Ringkasan otomatis percakapan ke episodic memory via LLM."
    depends_on  = []

    app_commands = {
        "summary": {
            "description": "Ringkas percakapan dan simpan ke memory",
            "usage":       "/summary | /summary last <N> | /summary --force",
            "handler":     "handle_summary",
            "args_hint":   "[last <N> | --force]",
        },
        "summary_list": {
            "description": "Lihat semua ringkasan percakapan tersimpan",
            "usage":       "/summary_list",
            "handler":     "handle_summary_list",
        },
    }

    # ── Lifecycle ─────────────────────────────────────────

    def setup(self):
        self._threshold      = int(self.config.get("threshold", 20))
        self._keep_last      = int(self.config.get("keep_last", 5))
        self._provider       = self.config.get("llm_provider", "gemini")
        self._model          = self.config.get("llm_model", "") or _DEFAULT_MODELS.get(self._provider, "gemini/gemini-2.0-flash")
        self._api_key        = self.config.get("llm_api_key", "")
        self._base_url       = self.config.get("llm_base_url", "")
        self._language       = self.config.get("language", "auto")
        self._max_tokens     = int(self.config.get("max_tokens", 300))
        self._inject_summary = self.config.get("inject_last_summary", True)
        logger.info(f"[summarizer] Initialized — threshold={self._threshold} model={self._model}")

    # ── Core ──────────────────────────────────────────────

    def _build_summary(self, history: list[dict], lang: str) -> str | None:
        """Format history ke conversation string lalu panggil LLM."""
        lines = []
        for msg in history:
            role    = msg.get("role", "")
            content = msg.get("content", "")
            if isinstance(content, str) and content.strip() and role in ("user", "assistant"):
                prefix = "User" if role == "user" else "Assistant"
                lines.append(f"{prefix}: {content[:400]}")
        if len(lines) < 3:
            return None

        template = _PROMPT_ID if lang == "id" else _PROMPT_EN
        prompt   = template.format(conversation="\n".join(lines),
                                   max_tokens=self._max_tokens // 4)
        return _call_llm(self._provider, self._model, self._api_key,
                         self._base_url, prompt, self._max_tokens)

    def _save_to_episodic(self, sc, user_id: str, summary: str):
        """Simpan summary ke episodic tier."""
        try:
            from simplecontext.enums import NodeKind
            ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
            sc.context(user_id).episodic.add(
                f"[Summary {ts}]\n{summary}",
                NodeKind.SUMMARY,
                importance=0.7,
            )
            self.state.set(f"last_summary:{user_id}", summary[:500])
            self.state.increment("total_summaries")
        except Exception as e:
            logger.warning(f"[summarizer] Failed to save: {e}")

    def _do_summarize(self, sc, user_id: str, limit: int = None) -> str | None:
        """Jalankan summarization. Return summary text atau None."""
        try:
            mem     = sc.memory(user_id)
            count   = mem.count()
            history = mem.get_for_llm(limit=limit or count)
        except Exception as e:
            logger.warning(f"[summarizer] Failed to get memory: {e}")
            return None

        if len(history) < 3:
            return None

        lang    = self._language if self._language != "auto" else _detect_lang(
            " ".join(m.get("content", "") for m in history[:5] if isinstance(m.get("content"), str))
        )
        summary = self._build_summary(history, lang)
        if summary:
            self._save_to_episodic(sc, user_id, summary)
            try:
                mem.compress(keep_last=self._keep_last)
            except Exception:
                pass
        return summary

    # ── Hooks ─────────────────────────────────────────────

    def on_message_saved(self, user_id: str, role: str, content: str,
                         tags: list, metadata: dict):
        """Cek threshold tiap 5 pesan untuk efisiensi."""
        if role != "user":
            return
        count = self.state.increment(f"msg_count:{user_id}")
        if count % 5 != 0:
            return
        # sc tidak tersedia via hook — auto-summarize dihandle oleh command
        # atau bisa dipanggil dari luar via plugin.force_summarize(sc, user_id)

    def on_before_llm(self, user_id: str, agent_id: str,
                      messages: list[dict]) -> list[dict]:
        """Inject ringkasan terakhir ke konteks jika tersedia."""
        if not self._inject_summary:
            return messages
        last = self.state.get(f"last_summary:{user_id}")
        if not last:
            return messages
        if messages and messages[0]["role"] == "system":
            messages[0]["content"] += f"\n\n[Previous session summary]\n{last}"
        return messages

    # ── Public API ────────────────────────────────────────

    def force_summarize(self, sc, user_id: str) -> str | None:
        """Panggil dari luar plugin untuk trigger summarize."""
        return self._do_summarize(sc, user_id)

    # ── App Command Handlers ───────────────────────────────

    async def handle_summary(self, ctx: AppCommandContext) -> str:
        """
        /summary              → ringkas semua
        /summary last <N>     → ringkas N pesan terakhir
        /summary --force      → paksa ringkas sekarang
        """
        sc   = ctx.sc
        args = ctx.args

        if sc is None:
            return "❌ SimpleContext tidak tersedia."

        # Parse args
        limit = None
        if len(args) >= 2 and args[0].lower() == "last":
            try:
                limit = int(args[1])
            except ValueError:
                return "❌ Format: `/summary last <N>` — contoh: `/summary last 20`"

        try:
            count = sc.memory(ctx.user_id).count()
        except Exception as e:
            return f"❌ Error: {e}"

        if count < 3:
            return (
                f"📝 *Summary*\n\n"
                f"_Baru ada {count} pesan — belum cukup untuk diringkas (min 3)._"
            )

        summary = self._do_summarize(sc, ctx.user_id, limit=limit)

        if not summary:
            return (
                "❌ Gagal membuat ringkasan.\n"
                "Pastikan `llm_api_key` sudah dikonfigurasi di `config.yaml`."
            )

        total = self.state.get("total_summaries", 0)
        preview = summary[:500] + ("..." if len(summary) > 500 else "")
        return (
            f"✅ *Summary saved*\n\n"
            f"_{preview}_\n\n"
            f"_Total summaries: {total}_"
        )

    async def handle_summary_list(self, ctx: AppCommandContext) -> str:
        """Tampilkan semua episodic summary user."""
        sc = ctx.sc
        if sc is None:
            return "❌ SimpleContext tidak tersedia."

        try:
            from simplecontext.enums import Tier, NodeKind
            nodes = sc._storage.get_nodes(
                ctx.user_id, tier=Tier.EPISODIC.value,
                status="active", limit=20,
            )
            summaries = [n for n in nodes if n.kind == NodeKind.SUMMARY]
            summaries.sort(key=lambda n: n.created_at, reverse=True)
        except Exception as e:
            return f"❌ Error: {e}"

        if not summaries:
            return (
                "📚 *Conversation Summaries*\n\n"
                "_Belum ada ringkasan tersimpan._\n\n"
                "Gunakan `/summary` untuk membuat ringkasan."
            )

        lines = [f"📚 *Summaries* ({len(summaries)} total)\n"]
        for i, node in enumerate(summaries[:5], 1):
            ts      = node.created_at.strftime("%Y-%m-%d %H:%M") if node.created_at else "—"
            preview = node.content.replace("\n", " ")[:180]
            if len(node.content) > 180:
                preview += "..."
            lines.append(f"*{i}. {ts}*\n_{preview}_")

        if len(summaries) > 5:
            lines.append(f"\n_... dan {len(summaries) - 5} ringkasan lainnya._")

        return "\n\n".join(lines)
