"""
Auto Tagger Plugin v1.0.0
Plugin resmi SimpleContext — tag otomatis setiap pesan berdasarkan keyword rules.

Tags digunakan oleh ContextRetriever untuk boost retrieval — node dengan tag
yang cocok dengan query lebih cepat ditemukan.

Cara kerja:
  on_message_saved → analisis konten pesan → inject tags ke metadata

Built-in tag categories (semua bisa di-override via config):
  - tech     : python, javascript, docker, api, database, ...
  - personal : nama, suka, tidak suka, prefer, hobi, ...
  - task     : todo, selesai, deadline, project, reminder, ...
  - question : apa, kenapa, bagaimana, how, why, what, ...
  - error    : error, bug, crash, failed, traceback, ...
  - positive : bagus, suka, senang, great, love, ...
  - negative : buruk, masalah, gagal, hate, problem, ...

Config di config.yaml:
    plugins:
      auto_tagger_plugin:
        enabled: true
        custom_rules:            # tambah rule sendiri
          work:
            - meeting
            - deadline
            - kantor
            - office
          hobby:
            - gaming
            - musik
            - olahraga
        min_word_length: 3       # abaikan kata < N karakter
        max_tags: 5              # max tags per pesan
        log_tags: false          # log tags ke console (debug)
"""

import re
import logging
from collections import defaultdict

from simplecontext.plugins.base import BasePlugin

logger = logging.getLogger(__name__)

# ── Built-in Tag Rules ────────────────────────────────────

BUILTIN_RULES: dict[str, list[str]] = {
    "tech": [
        "python", "javascript", "typescript", "golang", "rust", "java", "php",
        "html", "css", "sql", "bash", "linux", "docker", "kubernetes", "nginx",
        "api", "rest", "graphql", "database", "redis", "postgres", "mysql",
        "git", "github", "code", "kode", "program", "script", "function",
        "class", "library", "framework", "deploy", "server", "cloud", "aws",
        "gcp", "azure", "devops", "react", "vue", "nextjs", "fastapi", "django",
    ],
    "personal": [
        "nama", "name", "saya", "aku", "suka", "like", "love", "prefer",
        "tidak suka", "dislike", "hate", "hobi", "hobby", "tinggal", "live",
        "kerja", "work", "sekolah", "kuliah", "umur", "age", "lahir", "born",
        "keluarga", "family", "teman", "friend", "pacar", "partner",
    ],
    "task": [
        "todo", "task", "tugas", "selesai", "done", "finish", "deadline",
        "project", "reminder", "ingatkan", "remind", "jadwal", "schedule",
        "rencana", "plan", "target", "goal", "tujuan", "prioritas", "priority",
    ],
    "question": [
        "apa", "kenapa", "mengapa", "bagaimana", "gimana", "kapan", "dimana",
        "siapa", "what", "why", "how", "when", "where", "who", "which",
        "apakah", "bisakah", "bolehkah", "tolong", "bantu", "help", "jelaskan",
        "explain", "ceritakan", "tell",
    ],
    "error": [
        "error", "bug", "crash", "failed", "failure", "traceback", "exception",
        "masalah", "problem", "issue", "broken", "rusak", "tidak bisa",
        "cannot", "gagal", "fail", "undefined", "null", "none",
    ],
    "finance": [
        "uang", "money", "harga", "price", "bayar", "pay", "beli", "buy",
        "jual", "sell", "investasi", "invest", "saham", "stock", "crypto",
        "bitcoin", "tabungan", "saving", "budget", "anggaran", "hutang", "debt",
    ],
    "health": [
        "sakit", "sick", "sehat", "health", "olahraga", "exercise", "makan",
        "food", "tidur", "sleep", "stres", "stress", "anxiety", "diet",
        "vitamin", "obat", "medicine", "dokter", "doctor",
    ],
    "positive": [
        "bagus", "baik", "good", "great", "excellent", "amazing", "awesome",
        "suka", "senang", "happy", "love", "terima kasih", "thanks", "thank",
        "berhasil", "sukses", "success", "solved", "fixed", "works",
    ],
    "negative": [
        "buruk", "jelek", "bad", "terrible", "awful", "hate", "tidak suka",
        "masalah", "problem", "gagal", "fail", "error", "broken", "susah",
        "difficult", "hard", "frustasi", "frustrated", "annoyed",
    ],
}


class AutoTaggerPlugin(BasePlugin):
    """
    Auto-tag pesan berdasarkan keyword rules.
    Tags meningkatkan akurasi retrieval ContextRetriever.
    """

    name        = "auto_tagger_plugin"
    version     = "1.0.0"
    description = "Tag otomatis setiap pesan berdasarkan keyword — meningkatkan akurasi retrieval."
    depends_on  = []

    # ── Lifecycle ─────────────────────────────────────────

    def setup(self):
        self._min_word = int(self.config.get("min_word_length", 3))
        self._max_tags = int(self.config.get("max_tags", 5))
        self._log_tags = self.config.get("log_tags", False)

        # Merge built-in rules dengan custom rules dari config
        custom_rules = self.config.get("custom_rules", {})
        self._rules: dict[str, list[str]] = {**BUILTIN_RULES}
        for tag, keywords in custom_rules.items():
            if tag in self._rules:
                # Tambah ke existing tag
                self._rules[tag] = list(set(self._rules[tag] + keywords))
            else:
                # Tag baru
                self._rules[tag] = keywords

        # Pre-build compiled patterns untuk performa
        self._patterns: dict[str, re.Pattern] = {}
        for tag, keywords in self._rules.items():
            # Urutkan dari keyword terpanjang (multi-kata dulu)
            sorted_kw = sorted(keywords, key=len, reverse=True)
            pattern   = "|".join(re.escape(kw) for kw in sorted_kw if len(kw) >= self._min_word)
            if pattern:
                self._patterns[tag] = re.compile(pattern, re.IGNORECASE)

        total_kw = sum(len(v) for v in self._rules.values())
        logger.info(
            f"[auto_tagger] Initialized — "
            f"{len(self._rules)} categories, {total_kw} keywords, max_tags={self._max_tags}"
        )

    # ── Core Tagging ──────────────────────────────────────

    def _extract_tags(self, content: str) -> list[str]:
        """
        Analisis konten dan return list tag yang cocok.
        Diurutkan berdasarkan jumlah match (tag paling relevan duluan).
        """
        if not content or len(content) < self._min_word:
            return []

        tag_scores: dict[str, int] = {}
        for tag, pattern in self._patterns.items():
            matches = pattern.findall(content)
            if matches:
                # Score = jumlah unique keyword yang match
                tag_scores[tag] = len(set(m.lower() for m in matches))

        if not tag_scores:
            return []

        # Sort by score descending, ambil top N
        sorted_tags = sorted(tag_scores.items(), key=lambda x: x[1], reverse=True)
        return [tag for tag, _ in sorted_tags[: self._max_tags]]

    # ── Hooks ─────────────────────────────────────────────

    def on_message_saved(self, user_id: str, role: str, content: str,
                         tags: list, metadata: dict):
        """
        Setiap pesan yang disimpan dianalisis dan diberi tag.
        Tags ditambahkan ke node via storage update.
        """
        # Hanya tag pesan user dan assistant, skip system
        if role not in ("user", "assistant"):
            return

        new_tags = self._extract_tags(content)
        if not new_tags:
            return

        if self._log_tags:
            logger.info(f"[auto_tagger] user={user_id} role={role} tags={new_tags}")

        # Track stats
        self.state.increment("total_tagged")
        for tag in new_tags:
            self.state.increment(f"tag_count:{tag}")

        # Inject tags ke metadata untuk downstream hooks
        if isinstance(metadata, dict):
            existing = metadata.get("auto_tags", [])
            metadata["auto_tags"] = list(set(existing + new_tags))

    def on_context_build(self, user_id: str,
                         messages: list[dict]) -> list[dict]:
        """
        Inject tag stats ke system message sebagai hint untuk LLM
        (opsional, hanya jika ada pola dominan).
        """
        return messages

    # ── Public API ────────────────────────────────────────

    def get_tag_stats(self) -> dict[str, int]:
        """Return statistik tag yang paling sering muncul."""
        stats = {}
        for tag in self._rules:
            count = self.state.get(f"tag_count:{tag}", 0)
            if count > 0:
                stats[tag] = count
        return dict(sorted(stats.items(), key=lambda x: x[1], reverse=True))

    def tag_text(self, text: str) -> list[str]:
        """Public API untuk tag teks dari luar plugin."""
        return self._extract_tags(text)
