"""
my_plugin.py — Template Plugin SimpleContext

Rename file ini dan ubah class sesuai kebutuhan.
Override hanya hook yang kamu butuhkan.

Taruh file ini di folder plugins/ project SimpleContext kamu.

Config di config.yaml:
    plugins:
      my_plugin:
        enabled: true
        option_a: value
"""

from simplecontext.plugins.base import BasePlugin


class MyPlugin(BasePlugin):
    name        = "my_plugin"           # unik, snake_case, samakan dengan config.yaml
    version     = "1.0.0"
    description = "Deskripsi singkat plugin ini."
    depends_on  = []                    # ["nama_plugin_lain"] jika perlu

    def setup(self):
        """
        Dipanggil saat plugin diinit.
        self.config  → dict dari config.yaml
        self.state   → persistent state (disimpan ke DB)
        """
        self.option_a = self.config.get("option_a", "default")

    def teardown(self):
        """Dipanggil saat SimpleContext ditutup. Cleanup di sini."""

    # ── Hook: Memory ──────────────────────────────────────

    def on_message_saved(self, user_id: str, role: str, content: str,
                         tags: list, metadata: dict):
        """Dipanggil setiap pesan baru disimpan ke memori."""
        # Contoh: hitung total pesan
        # self.state.increment("total")

    def on_messages_cleared(self, user_id: str):
        """Dipanggil saat memori user dihapus."""

    def on_context_build(self, user_id: str,
                         messages: list[dict]) -> list[dict]:
        """
        Dipanggil saat history disiapkan untuk LLM.
        Bisa filter, enrich, atau inject messages.
        WAJIB return list messages.
        """
        return messages

    # ── Hook: LLM ─────────────────────────────────────────

    def on_before_llm(self, user_id: str, agent_id: str,
                      messages: list[dict]) -> list[dict]:
        """
        Dipanggil SEBELUM messages dikirim ke LLM.
        Contoh: inject system info, timestamp, dsb.
        WAJIB return list messages.
        """
        return messages

    def on_after_llm(self, user_id: str, agent_id: str,
                     response: str) -> str:
        """
        Dipanggil SETELAH LLM menghasilkan response.
        Contoh: tambah disclaimer, filter output, logging.
        WAJIB return string response.
        """
        return response

    # ── Hook: Skills ──────────────────────────────────────

    def on_skill_saved(self, agent_id: str, name: str, content: str):
        """Dipanggil saat skill disimpan/diupdate."""

    def on_skill_deleted(self, agent_id: str, name: str):
        """Dipanggil saat skill dihapus."""

    def on_prompt_build(self, agent_id: str, prompt: str) -> str:
        """
        Dipanggil setelah system prompt dibangun dari skills.
        WAJIB return string prompt.
        """
        return prompt

    # ── Hook: Agent ───────────────────────────────────────

    def on_agent_routed(self, user_id: str, agent_id: str, message: str):
        """Dipanggil saat pesan di-route ke agent."""

    def on_agent_chain(self, user_id: str, from_agent: str,
                       to_agent: str, reason: str):
        """Dipanggil saat terjadi chain antar agent."""

    # ── Hook: Export/Import ───────────────────────────────

    def on_export(self, data: dict) -> dict:
        """Dipanggil saat data di-export. WAJIB return dict."""
        return data

    def on_import(self, data: dict) -> dict:
        """Dipanggil saat data akan di-import. WAJIB return dict."""
        return data
