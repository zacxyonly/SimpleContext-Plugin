# Panduan Kontribusi — SimpleContext-Plugin

Terima kasih sudah mau berkontribusi! Panduan ini menjelaskan cara membuat dan mengirim plugin komunitas.

---

## Prasyarat

- Python 3.10+
- Familiar dengan [SimpleContext](https://github.com/zacxyonly/SimpleContext) v4
- Pahami cara kerja `BasePlugin` dan hook yang tersedia

---

## Struktur Plugin

Setiap plugin adalah **satu file `.py`** yang berisi satu class turunan `BasePlugin`:

```
community/plugin-nama-kamu/
├── nama_plugin.py      ← file plugin (satu file, taruh di ./plugins/ SC)
└── README.md           ← dokumentasi plugin
```

File plugin mengikuti konvensi penamaan: `nama_plugin.py` (snake_case).

---

## Anatomi Plugin

```python
from simplecontext.plugins.base import BasePlugin

class NamaPlugin(BasePlugin):
    name        = "nama_plugin"        # unik, snake_case
    version     = "1.0.0"
    description = "Apa yang plugin ini lakukan."
    depends_on  = []                   # nama plugin lain yang harus ada dulu

    def setup(self):
        """Dipanggil saat plugin diinit. self.state sudah tersedia di sini."""
        self.option = self.config.get("option", "default")

    def teardown(self):
        """Cleanup saat SimpleContext ditutup."""

    # ── Hooks — override hanya yang diperlukan ────────────

    def on_message_saved(self, user_id, role, content, tags, metadata):
        """Dipanggil setiap pesan baru disimpan ke memori."""

    def on_messages_cleared(self, user_id):
        """Dipanggil saat memori user dihapus."""

    def on_context_build(self, user_id, messages: list) -> list:
        """Dipanggil saat history disiapkan untuk LLM. Wajib return list."""
        return messages

    def on_before_llm(self, user_id, agent_id, messages: list) -> list:
        """Dipanggil SEBELUM pesan dikirim ke LLM. Wajib return list."""
        return messages

    def on_after_llm(self, user_id, agent_id, response: str) -> str:
        """Dipanggil SETELAH LLM reply. Wajib return string."""
        return response

    def on_skill_saved(self, agent_id, name, content): ...
    def on_skill_deleted(self, agent_id, name): ...
    def on_prompt_build(self, agent_id, prompt: str) -> str: return prompt
    def on_agent_routed(self, user_id, agent_id, message): ...
    def on_agent_chain(self, user_id, from_agent, to_agent, reason): ...
    def on_export(self, data: dict) -> dict: return data
    def on_import(self, data: dict) -> dict: return data
```

---

## Persistent State

Plugin punya akses ke `self.state` untuk menyimpan data permanen ke DB:

```python
# Simpan
self.state.set("key", value)

# Baca
value = self.state.get("key", default)

# Increment counter
total = self.state.increment("counter")

# Update banyak key
self.state.update({"key1": val1, "key2": val2})

# Baca semua
all_data = self.state.all()
```

---

## Config

User mengkonfigurasi plugin di `config.yaml` mereka:

```yaml
plugins:
  nama_plugin:
    enabled: true
    option: value
```

Di plugin, akses via `self.config.get("option", "default")`.

---

## Langkah Submit Plugin Komunitas

1. **Fork** repositori ini
2. **Buat folder** `community/plugin-nama-kamu/`
3. **Salin template** dari `templates/plugin-starter/` dan sesuaikan
4. **Test** plugin di project SimpleContext lokal kamu
5. **Buka Pull Request** dengan judul: `[Community Plugin] nama_plugin`

### Checklist sebelum PR:

- [ ] Nama plugin unik, belum ada yang sama
- [ ] Class mewarisi `BasePlugin` dan punya `name`, `version`, `description`
- [ ] Semua hook yang di-override mengembalikan nilai yang benar
- [ ] `README.md` berisi deskripsi, cara pasang, dan contoh config
- [ ] Tidak ada hardcoded credentials/API key
- [ ] Sudah ditest dengan SimpleContext

---

## Proses Review

1. Automated check: import test, struktur validasi
2. Review oleh maintainer (max ~3 hari kerja)
3. Feedback jika ada yang perlu diubah
4. Merge kalau sudah OK 🎉

---

## Lisensi

Dengan berkontribusi, kamu setuju plugin kamu dirilis di bawah **MIT License**.
