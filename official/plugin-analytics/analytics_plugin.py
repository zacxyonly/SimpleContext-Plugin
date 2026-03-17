"""
Analytics Plugin v1.0.0
Plugin resmi SimpleContext — usage analytics dan statistik per user/agent.

Melacak:
  - Total pesan per user dan per hari
  - Distribusi agent yang digunakan
  - Response time LLM (perkiraan via timestamp)
  - Peak hours penggunaan
  - Retention: hari-hari aktif per user

app_commands:
  /analytics           — ringkasan statistik personal user
  /analytics_global    — statistik global semua user (admin only)

Config di config.yaml:
    plugins:
      analytics_plugin:
        enabled: true
        admin_users: []          # list user_id yang boleh akses /analytics_global
        track_agents: true       # track distribusi agent
        track_hours: true        # track peak hours
        retention_days: 30       # window untuk hitung retention
"""

import time
import logging
from datetime import datetime, timezone, timedelta
from collections import defaultdict

from simplecontext.plugins.base import BasePlugin, AppCommandContext

logger = logging.getLogger(__name__)


class AnalyticsPlugin(BasePlugin):
    """
    Usage analytics dan statistik untuk SimpleContext.
    Semua data disimpan ke plugin state (persisten ke DB).
    Zero external dependency.
    """

    name        = "analytics_plugin"
    version     = "1.0.0"
    description = "Usage analytics — statistik pesan, agent, dan aktivitas per user."
    depends_on  = []

    app_commands = {
        "analytics": {
            "description": "Lihat statistik penggunaan kamu",
            "usage":       "/analytics",
            "handler":     "handle_analytics",
        },
        "analytics_global": {
            "description": "Statistik global semua user (admin only)",
            "usage":       "/analytics_global",
            "handler":     "handle_analytics_global",
            "hidden":      True,
        },
    }

    # ── Lifecycle ─────────────────────────────────────────

    def setup(self):
        self._admin_users    = [str(u) for u in self.config.get("admin_users", [])]
        self._track_agents   = self.config.get("track_agents", True)
        self._track_hours    = self.config.get("track_hours", True)
        self._retention_days = int(self.config.get("retention_days", 30))
        logger.info(f"[analytics] Initialized — retention={self._retention_days}d")

    # ── Helpers ───────────────────────────────────────────

    def _today(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def _hour(self) -> int:
        return datetime.now(timezone.utc).hour

    def _user_key(self, user_id: str, key: str) -> str:
        return f"u:{user_id}:{key}"

    def _track_user_message(self, user_id: str):
        """Update semua counter untuk satu pesan user."""
        uid = str(user_id)
        today = self._today()

        # Total messages
        self.state.increment(self._user_key(uid, "total_msgs"))

        # Messages per day
        day_key = self._user_key(uid, f"day:{today}")
        self.state.increment(day_key)

        # Active days (untuk retention)
        active_days = self.state.get(self._user_key(uid, "active_days"), [])
        if today not in active_days:
            active_days.append(today)
            # Simpan hanya N hari terakhir
            cutoff = (datetime.now(timezone.utc) - timedelta(days=self._retention_days)).strftime("%Y-%m-%d")
            active_days = [d for d in active_days if d >= cutoff]
            self.state.set(self._user_key(uid, "active_days"), active_days)

        # Peak hours
        if self._track_hours:
            hour_key = self._user_key(uid, f"hour:{self._hour()}")
            self.state.increment(hour_key)

        # Global counters
        self.state.increment("global:total_msgs")
        self.state.increment(f"global:day:{today}")

        # Track unique users
        users = self.state.get("global:users", [])
        if uid not in users:
            users.append(uid)
            self.state.set("global:users", users)

    def _track_agent(self, user_id: str, agent_id: str):
        """Track distribusi penggunaan agent per user."""
        uid = str(user_id)
        agents = self.state.get(self._user_key(uid, "agents"), {})
        agents[agent_id] = agents.get(agent_id, 0) + 1
        self.state.set(self._user_key(uid, "agents"), agents)

        # Global agent stats
        global_agents = self.state.get("global:agents", {})
        global_agents[agent_id] = global_agents.get(agent_id, 0) + 1
        self.state.set("global:agents", global_agents)

    def _format_bar(self, value: int, max_val: int, width: int = 10) -> str:
        """Buat bar chart sederhana dengan unicode."""
        if max_val == 0:
            return "░" * width
        filled = round((value / max_val) * width)
        return "█" * filled + "░" * (width - filled)

    def _get_peak_hour(self, user_id: str) -> str:
        """Cari jam paling aktif user."""
        uid = str(user_id)
        hour_counts = {}
        for h in range(24):
            count = self.state.get(self._user_key(uid, f"hour:{h}"), 0)
            if count > 0:
                hour_counts[h] = count
        if not hour_counts:
            return "—"
        peak = max(hour_counts, key=hour_counts.get)
        return f"{peak:02d}:00 UTC ({hour_counts[peak]} msgs)"

    def _get_streak(self, user_id: str) -> int:
        """Hitung streak hari berturut-turut aktif."""
        uid = str(user_id)
        active_days = sorted(self.state.get(self._user_key(uid, "active_days"), []), reverse=True)
        if not active_days:
            return 0
        streak = 0
        check  = datetime.now(timezone.utc).date()
        for day_str in active_days:
            day = datetime.strptime(day_str, "%Y-%m-%d").date()
            if day == check:
                streak += 1
                check = check - timedelta(days=1)
            else:
                break
        return streak

    # ── Hooks ─────────────────────────────────────────────

    def on_message_saved(self, user_id: str, role: str, content: str,
                         tags: list, metadata: dict):
        if role != "user":
            return
        self._track_user_message(str(user_id))

    def on_agent_routed(self, user_id: str, agent_id: str, message: str):
        if self._track_agents:
            self._track_agent(str(user_id), agent_id)

    def on_after_llm(self, user_id: str, agent_id: str, response: str) -> str:
        self.state.increment("global:total_llm_calls")
        return response

    # ── App Command Handlers ───────────────────────────────

    async def handle_analytics(self, ctx: AppCommandContext) -> str:
        """Statistik personal untuk user yang memanggil command."""
        uid   = ctx.user_id
        today = self._today()

        total_msgs  = self.state.get(self._user_key(uid, "total_msgs"), 0)
        today_msgs  = self.state.get(self._user_key(uid, f"day:{today}"), 0)
        active_days = self.state.get(self._user_key(uid, "active_days"), [])
        agents      = self.state.get(self._user_key(uid, "agents"), {})
        streak      = self._get_streak(uid)
        peak_hour   = self._get_peak_hour(uid) if self._track_hours else "—"

        # Top agents
        top_agents = ""
        if agents:
            sorted_agents = sorted(agents.items(), key=lambda x: x[1], reverse=True)[:5]
            max_count     = sorted_agents[0][1] if sorted_agents else 1
            lines = []
            for agent, count in sorted_agents:
                bar  = self._format_bar(count, max_count, 8)
                pct  = round((count / total_msgs * 100)) if total_msgs else 0
                lines.append(f"  {agent:<18} {bar} {count} ({pct}%)")
            top_agents = "\n" + "\n".join(lines)

        return (
            f"📊 *Your Analytics*\n\n"
            f"💬 Total messages: `{total_msgs}`\n"
            f"📅 Today: `{today_msgs}` messages\n"
            f"📆 Active days: `{len(active_days)}` (last {self._retention_days}d)\n"
            f"🔥 Current streak: `{streak}` days\n"
            f"⏰ Peak hour: `{peak_hour}`\n"
            + (f"\n🤖 *Top agents:*{top_agents}" if top_agents else "")
        )

    async def handle_analytics_global(self, ctx: AppCommandContext) -> str:
        """Global stats — hanya untuk admin."""
        if self._admin_users and ctx.user_id not in self._admin_users:
            return "❌ Access denied. This command is for admins only."

        today        = self._today()
        total_msgs   = self.state.get("global:total_msgs", 0)
        today_msgs   = self.state.get(f"global:day:{today}", 0)
        total_users  = len(self.state.get("global:users", []))
        total_llm    = self.state.get("global:total_llm_calls", 0)
        global_agents = self.state.get("global:agents", {})

        top_agents = ""
        if global_agents:
            sorted_agents = sorted(global_agents.items(), key=lambda x: x[1], reverse=True)[:5]
            max_count     = sorted_agents[0][1] if sorted_agents else 1
            lines = []
            for agent, count in sorted_agents:
                bar = self._format_bar(count, max_count, 8)
                lines.append(f"  {agent:<18} {bar} {count}")
            top_agents = "\n" + "\n".join(lines)

        avg_per_user = round(total_msgs / total_users, 1) if total_users else 0

        return (
            f"📊 *Global Analytics*\n\n"
            f"👥 Total users: `{total_users}`\n"
            f"💬 Total messages: `{total_msgs}`\n"
            f"📅 Today: `{today_msgs}` messages\n"
            f"🤖 LLM calls: `{total_llm}`\n"
            f"📈 Avg msgs/user: `{avg_per_user}`\n"
            + (f"\n🤖 *Top agents:*{top_agents}" if top_agents else "")
        )
