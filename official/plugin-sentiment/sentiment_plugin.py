"""
Sentiment Plugin v1.0.0
Plugin resmi SimpleContext — analisis sentimen user dan adaptasi respons agent.

Cara kerja:
  on_message_saved  → analisis sentimen teks user (positif/negatif/netral)
                    → simpan ke metadata dan history
  on_prompt_build   → inject instruksi ke system prompt jika user frustrasi

Sentiment detection: rule-based lexicon (zero dependency).
Mendukung bahasa Indonesia dan Inggris.

app_commands:
  /sentiment          — lihat sentimen percakapan hari ini
  /sentiment history  — tren sentimen 7 hari terakhir

Config di config.yaml:
    plugins:
      sentiment_plugin:
        enabled: true
        negative_threshold: -0.3    # di bawah ini = frustrated
        inject_on_negative: true    # inject instruksi saat user negatif
        window_messages: 5          # hitung sentimen dari N pesan terakhir
        track_history: true         # simpan history sentimen harian
"""

import re
import logging
from datetime import datetime, timezone, timedelta

from simplecontext.plugins.base import BasePlugin, AppCommandContext

logger = logging.getLogger(__name__)

# ── Sentiment Lexicons ────────────────────────────────────

_POSITIVE_EN = {
    "good", "great", "excellent", "amazing", "awesome", "wonderful", "fantastic",
    "love", "like", "enjoy", "happy", "glad", "pleased", "satisfied", "perfect",
    "helpful", "thanks", "thank", "appreciate", "brilliant", "superb", "nice",
    "easy", "solved", "fixed", "works", "success", "clear", "understand", "got it",
}

_NEGATIVE_EN = {
    "bad", "terrible", "awful", "horrible", "hate", "dislike", "frustrated",
    "angry", "annoyed", "confused", "stuck", "broken", "failed", "error",
    "wrong", "useless", "stupid", "ridiculous", "problem", "issue", "bug",
    "crash", "doesn't work", "not working", "cant", "cannot", "impossible",
    "difficult", "hard", "disappointing", "waste", "ugly", "slow",
}

_POSITIVE_ID = {
    "bagus", "baik", "hebat", "luar biasa", "keren", "mantap", "oke", "ok",
    "suka", "senang", "puas", "berhasil", "bisa", "mudah", "jelas",
    "terima kasih", "makasih", "thanks", "bantu", "membantu", "solved",
    "selesai", "done", "benar", "tepat", "cocok", "pas",
}

_NEGATIVE_ID = {
    "buruk", "jelek", "rusak", "error", "gagal", "masalah", "problem",
    "susah", "sulit", "bingung", "tidak bisa", "nggak bisa", "gak bisa",
    "tidak jalan", "tidak bekerja", "salah", "marah", "kesal", "frustrasi",
    "percuma", "sia-sia", "lambat", "lama", "parah", "waduh", "aduh",
}

_NEGATION_EN = {"not", "no", "never", "don't", "doesn't", "didn't", "can't", "won't"}
_NEGATION_ID = {"tidak", "nggak", "gak", "tak", "bukan", "jangan", "belum"}
_INTENSIFIER = {"very", "really", "so", "extremely", "absolutely", "sangat", "banget", "sekali", "amat"}


def _analyze_sentiment(text: str) -> float:
    """
    Analisis sentimen rule-based.
    Return score: -1.0 (sangat negatif) hingga +1.0 (sangat positif).
    0.0 = netral.
    """
    if not text:
        return 0.0

    text_lower = text.lower()
    tokens     = re.findall(r'\b\w+\b', text_lower)
    token_set  = set(tokens)

    score       = 0.0
    word_count  = max(len(tokens), 1)

    for i, token in enumerate(tokens):
        # Cek multi-word phrases
        bigram = f"{tokens[i-1]} {token}" if i > 0 else ""

        is_pos = (token in _POSITIVE_EN or token in _POSITIVE_ID or
                  bigram in _POSITIVE_EN or bigram in _POSITIVE_ID)
        is_neg = (token in _NEGATIVE_EN or token in _NEGATIVE_ID or
                  bigram in _NEGATIVE_EN or bigram in _NEGATIVE_ID)

        if not (is_pos or is_neg):
            continue

        word_score = 1.0 if is_pos else -1.0

        # Cek negation (2 kata sebelumnya)
        context = tokens[max(0, i-2):i]
        if any(w in _NEGATION_EN or w in _NEGATION_ID for w in context):
            word_score *= -1.0

        # Cek intensifier
        if any(w in _INTENSIFIER for w in context):
            word_score *= 1.5

        score += word_score

    # Normalize ke [-1, 1]
    normalized = max(-1.0, min(1.0, score / (word_count ** 0.5)))
    return round(normalized, 3)


def _label(score: float) -> str:
    if score > 0.2:
        return "😊 Positive"
    if score < -0.2:
        return "😟 Negative"
    return "😐 Neutral"


def _emoji(score: float) -> str:
    if score > 0.5:
        return "😄"
    if score > 0.2:
        return "🙂"
    if score > -0.2:
        return "😐"
    if score > -0.5:
        return "😕"
    return "😤"


class SentimentPlugin(BasePlugin):
    """Analisis sentimen dan adaptasi respons agent."""

    name        = "sentiment_plugin"
    version     = "1.0.0"
    description = "Analisis sentimen user — adaptasi tone agent saat user frustrasi."
    depends_on  = []

    app_commands = {
        "sentiment": {
            "description": "Lihat analisis sentimen percakapan",
            "usage":       "/sentiment | /sentiment history",
            "handler":     "handle_sentiment",
            "args_hint":   "[history]",
        },
    }

    # ── Lifecycle ─────────────────────────────────────────

    def setup(self):
        self._neg_threshold  = float(self.config.get("negative_threshold", -0.3))
        self._inject_on_neg  = self.config.get("inject_on_negative", True)
        self._window         = int(self.config.get("window_messages", 5))
        self._track_history  = self.config.get("track_history", True)
        logger.info(
            f"[sentiment] Initialized — threshold={self._neg_threshold} "
            f"window={self._window}"
        )

    # ── Helpers ───────────────────────────────────────────

    def _save_score(self, user_id: str, score: float):
        """Simpan score ke rolling window dan daily history."""
        uid = str(user_id)

        # Rolling window
        window = self.state.get(f"window:{uid}", [])
        window.append(score)
        if len(window) > self._window:
            window = window[-self._window:]
        self.state.set(f"window:{uid}", window)

        # Current mood (moving average)
        avg = sum(window) / len(window)
        self.state.set(f"mood:{uid}", round(avg, 3))

        # Daily history
        if self._track_history:
            today  = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            scores = self.state.get(f"daily:{uid}:{today}", [])
            scores.append(score)
            self.state.set(f"daily:{uid}:{today}", scores)

    def _get_mood(self, user_id: str) -> float:
        return float(self.state.get(f"mood:{str(user_id)}", 0.0))

    # ── Hooks ─────────────────────────────────────────────

    def on_message_saved(self, user_id: str, role: str, content: str,
                         tags: list, metadata: dict):
        """Analisis sentimen tiap pesan user."""
        if role != "user":
            return

        score = _analyze_sentiment(content)
        self._save_score(str(user_id), score)
        self.state.increment("total_analyzed")

        if isinstance(metadata, dict):
            metadata["sentiment_score"] = score
            metadata["sentiment_label"] = _label(score)

        logger.debug(f"[sentiment] user={user_id} score={score} label={_label(score)}")

    def on_prompt_build(self, agent_id: str, prompt: str) -> str:
        """
        NOTE: on_prompt_build tidak punya user_id — ini limitasi arsitektur.
        Instruksi injected di on_before_llm sebagai gantinya.
        """
        return prompt

    def on_before_llm(self, user_id: str, agent_id: str,
                      messages: list[dict]) -> list[dict]:
        """Inject instruksi empati jika user sedang frustrasi."""
        if not self._inject_on_neg or not messages:
            return messages

        mood = self._get_mood(str(user_id))
        if mood >= self._neg_threshold:
            return messages  # mood oke, tidak perlu inject

        instruction = (
            "\n\nNOTE: The user seems frustrated or having difficulties. "
            "Be extra patient, empathetic, and supportive. "
            "Acknowledge their frustration before providing solutions. "
            "Use a warmer, more encouraging tone."
        )

        if messages[0]["role"] == "system":
            messages[0]["content"] += instruction
        else:
            messages.insert(0, {"role": "system", "content": instruction.strip()})

        logger.debug(f"[sentiment] Injected empathy instruction for user={user_id} mood={mood}")
        return messages

    # ── App Command Handlers ───────────────────────────────

    async def handle_sentiment(self, ctx: AppCommandContext) -> str:
        """
        /sentiment          → ringkasan sentimen sekarang
        /sentiment history  → tren 7 hari terakhir
        """
        uid  = ctx.user_id
        args = ctx.args

        if args and args[0].lower() == "history":
            # Tren 7 hari
            today = datetime.now(timezone.utc)
            lines = [f"📈 *Sentiment History (7 days)*\n"]
            has_data = False

            for i in range(6, -1, -1):
                day    = (today - timedelta(days=i)).strftime("%Y-%m-%d")
                scores = self.state.get(f"daily:{uid}:{day}", [])
                if not scores:
                    lines.append(f"`{day}` — no data")
                    continue
                has_data  = True
                avg       = sum(scores) / len(scores)
                bar_width = 10
                filled    = int(((avg + 1) / 2) * bar_width)
                bar       = "█" * filled + "░" * (bar_width - filled)
                lines.append(
                    f"`{day}` {bar} {_emoji(avg)} "
                    f"{avg:+.2f} ({len(scores)} msgs)"
                )

            if not has_data:
                return "📈 *Sentiment History*\n\n_Belum ada data._"

            return "\n".join(lines)

        # Current sentiment
        mood       = self._get_mood(uid)
        window     = self.state.get(f"window:{uid}", [])
        total      = self.state.get("total_analyzed", 0)

        if not window:
            return (
                "😐 *Sentiment Analysis*\n\n"
                "_Belum ada cukup pesan untuk dianalisis._"
            )

        # Distribusi di window
        pos = sum(1 for s in window if s > 0.2)
        neg = sum(1 for s in window if s < -0.2)
        neu = len(window) - pos - neg

        bar_width = 10
        pos_bar   = round((pos / len(window)) * bar_width)
        neg_bar   = round((neg / len(window)) * bar_width)
        neu_bar   = bar_width - pos_bar - neg_bar

        return (
            f"{_emoji(mood)} *Sentiment Analysis*\n\n"
            f"Current mood: `{_label(mood)}` ({mood:+.2f})\n\n"
            f"Last {len(window)} messages:\n"
            f"  😊 Positive: `{pos}` {'█' * pos_bar}\n"
            f"  😐 Neutral:  `{neu}` {'█' * neu_bar}\n"
            f"  😟 Negative: `{neg}` {'█' * neg_bar}\n\n"
            f"_Total messages analyzed: {total}_\n"
            f"_Use `/sentiment history` for 7-day trend_"
        )
