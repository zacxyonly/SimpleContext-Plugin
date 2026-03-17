# Changelog

Semua perubahan penting pada repositori ini dicatat di sini.

Format mengikuti [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [1.2.0] — 2026-03-17

### Added
- **`plugin-analytics` v1.0.0** — usage analytics per user/agent, `/analytics`, `/analytics_global`
- **`plugin-summarizer` v1.0.0** — ringkasan otomatis percakapan ke episodic memory, `/summary`, `/summary_list`
- **`plugin-web-search` v1.0.0** — pencarian internet real-time (DuckDuckGo free, Bing, Google), `/search`
- **`plugin-translate` v1.0.0** — penerjemah multi-bahasa auto-detect 20+ bahasa, `/translate`
- **`plugin-sentiment` v1.0.0** — analisis sentimen rule-based, adaptasi tone agent, `/sentiment`
- **`plugin-rate-limiter` v1.0.0** — batasi request per jam/hari, estimasi token, `/usage`

---

## [1.1.0] — 2026-03-17

### Changed
- **`plugin-vector-search`**: migrate `BOT_COMMANDS` → `app_commands` (SimpleContext v4.3 contract)
- **`plugin-vector-search`**: update handler signature ke `AppCommandContext`
  - Sebelum: `async def bot_cmd_semantic(self, sc, update, ctx, args)`
  - Sekarang: `async def bot_cmd_semantic(self, ctx: AppCommandContext)`
- Handler tidak lagi Telegram-specific — bisa dipanggil dari platform apapun

### Docs
- Update `CONTRIBUTING.md` dengan konvensi `app_commands` dan handler signature baru

> **Requires:** SimpleContext v4.3.0+

---

## [1.0.0] — 2026-03-17

### Added
- Inisialisasi struktur repositori `SimpleContext-Plugin`
- **`plugin-vector-search` v1.0.0** — semantic vector search dengan 3 provider:
  - `local`: TF-IDF cosine similarity, zero dependency
  - `openai`: text-embedding-3-small via OpenAI API
  - `ollama`: model lokal via Ollama REST API
- `CONTRIBUTING.md` — panduan lengkap membuat dan submit plugin komunitas
- `templates/plugin-starter/` — template plugin dengan semua hook terdokumentasi
- `community/` — folder siap menerima kontribusi komunitas
