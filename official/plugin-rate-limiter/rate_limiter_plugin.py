"""
Rate Limiter Plugin v1.0.0
Plugin resmi SimpleContext — manajemen penggunaan dan pencegahan abuse.

Fitur:
  - Batasi jumlah request per user per jam/hari
  - Estimasi token usage dan biaya (opsional)
  - Whitelist user tertentu
  - Dua mode: per-hour dan per-day

app_commands:
  /usage          — tampilkan usage hari ini
  /usage reset    — reset counter (admin only)

Hook yang digunakan:
  on_before_llm → cek quota, tolak jika melebihi
  on_after_llm  → estimasi token, update counter

Config di config.yaml:
    plugins:
      rate_limiter_plugin:
        enabled: true
        requests_per_hour: 20        # 0 = unlimited
        requests_per_day: 100        # 0 = unlimited
        block_message: "⚠️ Batas penggunaan tercapai. Coba lagi nanti."
        whitelist: []                # user_id yang tidak terkena limit
        admin_users: []              # user_id yang bisa /usage reset
        estimate_tokens: true        # estimasi token usage
        cost_per_1k_tokens: 0.0      # estimasi biaya per 1k token (USD)
"""

import time
import logging
from datetime import datetime, timezone

from simplecontext.plugins.base import BasePlugin, AppCommandContext

logger = logging.getLogger(__name__)


def _estimate_tokens(text: str) -> int:
    """Estimasi token count (approx 4 chars = 1 token)."""
    return max(1, len(text) // 4)


class RateLimiterPlugin(BasePlugin):
    """Manajemen penggunaan dan pencegahan abuse untuk SimpleContext."""

    name        = "rate_limiter_plugin"
    version     = "1.0.0"
    description = "Batasi request per user per jam/hari, estimasi token dan biaya."
    depends_on  = []

    app_commands = {
        "usage": {
            "description": "Tampilkan usage hari ini",
            "usage":       "/usage | /usage reset",
            "handler":     "handle_usage",
            "args_hint":   "[reset]",
        },
    }

    # ── Lifecycle ─────────────────────────────────────────

    def setup(self):
        self._per_hour       = int(self.config.get("requests_per_hour", 20))
        self._per_day        = int(self.config.get("requests_per_day", 100))
        self._block_msg      = self.config.get(
            "block_message",
            "⚠️ Batas penggunaan tercapai. Coba lagi nanti."
        )
        self._whitelist      = [str(u) for u in self.config.get("whitelist", [])]
        self._admins         = [str(u) for u in self.config.get("admin_users", [])]
        self._est_tokens     = self.config.get("estimate_tokens", True)
        self._cost_per_1k    = float(self.config.get("cost_per_1k_tokens", 0.0))

        logger.info(
            f"[rate_limiter] Initialized — "
            f"per_hour={self._per_hour} per_day={self._per_day}"
        )

    # ── Helpers ───────────────────────────────────────────

    def _hour_key(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H")

    def _day_key(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def _get_user_counts(self, user_id: str) -> tuple[int, int]:
        """Return (hour_count, day_count) untuk user."""
        uid  = str(user_id)
        hour = self.state.get(f"h:{uid}:{self._hour_key()}", 0)
        day  = self.state.get(f"d:{uid}:{self._day_key()}", 0)
        return hour, day

    def _increment_user(self, user_id: str):
        """Increment request counter user."""
        uid = str(user_id)
        self.state.increment(f"h:{uid}:{self._hour_key()}")
        self.state.increment(f"d:{uid}:{self._day_key()}")
        self.state.increment("global:total_requests")
        self.state.increment(f"global:day:{self._day_key()}")

    def _is_limited(self, user_id: str) -> tuple[bool, str]:
        """
        Cek apakah user terkena limit.
        Return: (is_limited, reason)
        """
        uid = str(user_id)
        if uid in self._whitelist:
            return False, ""

        hour_count, day_count = self._get_user_counts(uid)

        if self._per_hour > 0 and hour_count >= self._per_hour:
            return True, f"hourly limit ({hour_count}/{self._per_hour})"
        if self._per_day > 0 and day_count >= self._per_day:
            return True, f"daily limit ({day_count}/{self._per_day})"

        return False, ""

    # ── Hooks ─────────────────────────────────────────────

    def on_before_llm(self, user_id: str, agent_id: str,
                      messages: list[dict]) -> list[dict]:
        """Cek quota sebelum LLM dipanggil. Ganti pesan jika limited."""
        limited, reason = self._is_limited(str(user_id))

        if not limited:
            self._increment_user(str(user_id))
            return messages

        # Track blocked
        self.state.increment("global:total_blocked")
        self.state.increment(f"blocked:{str(user_id)}:{self._day_key()}")
        logger.info(f"[rate_limiter] Blocked user={user_id} reason={reason}")

        # Ganti pesan user terakhir
        for i in range(len(messages) - 1, -1, -1):
            if messages[i]["role"] == "user":
                messages[i]["content"] = self._block_msg
                break
        return messages

    def on_after_llm(self, user_id: str, agent_id: str, response: str) -> str:
        """Estimasi dan catat token usage."""
        if not self._est_tokens:
            return response

        # Estimasi token dari response
        tokens = _estimate_tokens(response)
        self.state.increment(f"tokens:{str(user_id)}:{self._day_key()}", by=tokens)
        self.state.increment("global:total_tokens", by=tokens)
        return response

    # ── App Command Handlers ───────────────────────────────

    async def handle_usage(self, ctx: AppCommandContext) -> str:
        """
        /usage       → lihat usage hari ini
        /usage reset → reset counter (admin only)
        """
        uid  = ctx.user_id
        args = ctx.args

        # /usage reset
        if args and args[0].lower() == "reset":
            if self._admins and uid not in self._admins:
                return "❌ Hanya admin yang bisa reset usage."
            # Reset semua counter hari ini untuk user ini
            day = self._day_key()
            self.state.set(f"d:{uid}:{day}", 0)
            self.state.set(f"tokens:{uid}:{day}", 0)
            return f"✅ Usage untuk user `{uid}` direset."

        # /usage
        hour_count, day_count = self._get_user_counts(uid)
        day        = self._day_key()
        tokens_day = self.state.get(f"tokens:{uid}:{day}", 0)
        blocked    = self.state.get(f"blocked:{uid}:{day}", 0)

        is_whitelisted = uid in self._whitelist

        # Progress bars
        def _bar(used: int, limit: int) -> str:
            if limit == 0:
                return "∞"
            pct    = min(1.0, used / limit)
            filled = int(pct * 10)
            return f"{'█' * filled}{'░' * (10 - filled)} {used}/{limit}"

        hour_bar = _bar(hour_count, self._per_hour) if self._per_hour else f"{hour_count} (no limit)"
        day_bar  = _bar(day_count, self._per_day)   if self._per_day  else f"{day_count} (no limit)"

        lines = [f"📊 *Usage Today* ({day})\n"]

        if is_whitelisted:
            lines.append("✅ You are whitelisted — no limits apply.\n")

        lines += [
            f"⏰ This hour: `{hour_bar}`",
            f"📅 Today:     `{day_bar}`",
        ]

        if self._est_tokens and tokens_day > 0:
            lines.append(f"🔤 Tokens:    `~{tokens_day:,}`")
            if self._cost_per_1k > 0:
                cost = (tokens_day / 1000) * self._cost_per_1k
                lines.append(f"💰 Est. cost: `~${cost:.4f}`")

        if blocked > 0:
            lines.append(f"🚫 Blocked:   `{blocked}` requests today")

        # Global stats (admin only)
        if uid in self._admins:
            global_req   = self.state.get(f"global:day:{day}", 0)
            global_block = self.state.get("global:total_blocked", 0)
            global_tok   = self.state.get("global:total_tokens", 0)
            lines += [
                f"\n*Global Stats (admin):*",
                f"  Total requests today: `{global_req}`",
                f"  Total blocked (all time): `{global_block}`",
                f"  Total tokens (all time): `~{global_tok:,}`",
            ]

        return "\n".join(lines)
