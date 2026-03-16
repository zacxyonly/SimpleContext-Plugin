# Changelog

Semua perubahan penting pada repositori ini dicatat di sini.

Format mengikuti [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

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
