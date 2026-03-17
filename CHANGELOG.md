# Changelog

Semua perubahan penting pada repositori ini dicatat di sini.

Format mengikuti [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [1.3.0] — 2026-03-17

### Added
- **`plugin-summarizer` v1.0.0** — ringkasan otomatis percakapan ke episodic memory, `/summary`, `/summary_list`
- **`plugin-web-search` v1.0.0** — pencarian internet real-time (DuckDuckGo free, Bing, Google), `/search`
- **`plugin-translate` v1.0.0** — penerjemah multi-bahasa auto-detect 20+ bahasa, `/translate`
- **`plugin-sentiment` v1.0.0** — analisis sentimen rule-based, adaptasi tone agent, `/sentiment`
- **`plugin-rate-limiter` v1.0.0** — batasi request per jam/hari, estimasi token, `/usage`

### Removed
- `plugin-search` — digabung ke vector-search dan digantikan /search di web-search
- `plugin-auto-tagger` — akan hadir kembali dengan versi yang lebih baik

---

## [1.2.0] — 2026-03-17

### Added
- **`plugin-analytics` v1.0.0** — usage analytics per user/agent dengan `/analytics` dan `/analytics_global` commands
- **`plugin-rate-limiter` v1.0.0** — rate limiting sliding window + token bucket dengan `/ratelimit` command
- **`plugin-search` v1.0.0** — keyword search di memory dengan `/search`, `/search_facts`, `/forget` commands
- **`plugin-auto-tagger` v1.0.0** — auto-tag pesan berdasarkan 9 kategori built-in + custom rules
- **`plugin-summarizer` v1.0.0** — auto-compress working memory ke episodic summary via LLM

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
