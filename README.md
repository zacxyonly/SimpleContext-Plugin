<div align="center">

<h1>🧩 SimpleContext-Plugin</h1>

<p><strong>Official & Community Plugin Registry for SimpleContext</strong></p>

[![License](https://img.shields.io/badge/License-MIT-yellow?style=flat-square)](LICENSE)
[![Contributions Welcome](https://img.shields.io/badge/contributions-welcome-brightgreen?style=flat-square)](CONTRIBUTING.md)
[![SimpleContext](https://img.shields.io/badge/SimpleContext-v4.2-blueviolet?style=flat-square)](https://github.com/zacxyonly/SimpleContext)

<br/>

> Plugin repository resmi untuk ekosistem [SimpleContext](https://github.com/zacxyonly/SimpleContext).
> Temukan, pasang, dan kontribusi plugin untuk memperluas kemampuan SimpleContext.

<br/>

[Cara Pasang](#-cara-pasang) · [Plugin Tersedia](#-plugin-tersedia) · [Buat Plugin](#-buat-plugin-baru) · [Kontribusi](#-kontribusi)

</div>

---

## 📦 Plugin Tersedia

### Official Plugins

<!-- PLUGINS_TABLE_START -->
| Plugin | Deskripsi | Versi | Commands |
|--------|-----------|-------|----------|
| 📊 [`plugin-analytics`](./official/plugin-analytics/) | Usage analytics — statistik pesan, agent, dan aktivitas per user. | `1.0.0` | `/analytics`, `/analytics_global` |
| ⏱ [`plugin-rate-limiter`](./official/plugin-rate-limiter/) | Batasi request per user per jam/hari, estimasi token dan biaya. | `1.0.0` | `/usage` |
| 😊 [`plugin-sentiment`](./official/plugin-sentiment/) | Analisis sentimen user — adaptasi tone agent saat user frustrasi. | `1.0.0` | `/sentiment` |
| 📝 [`plugin-summarizer`](./official/plugin-summarizer/) | Ringkasan otomatis percakapan ke episodic memory via LLM. | `1.0.0` | `/summary`, `/summary_list` |
| 🌏 [`plugin-translate`](./official/plugin-translate/) | Penerjemah multi-bahasa — auto-detect bahasa user dan terjemahkan response. | `1.0.0` | `/translate` |
| 🔍 [`plugin-vector-search`](./official/plugin-vector-search/) | Semantic vector search berbasis embedding — komplemen keyword retrieval. | `1.0.0` | `/semantic` |
| 🌐 [`plugin-web-search`](./official/plugin-web-search/) | Pencarian internet real-time — DuckDuckGo (free), Bing, atau Google. | `1.0.0` | `/search` |
<!-- PLUGINS_TABLE_END -->

### Community Plugins

| Plugin | Author | Deskripsi | Status |
|--------|--------|-----------|--------|
| *(kirim plugin kamu!)* | — | — | — |

---

## 🚀 Cara Pasang

### Manual (recommended)

Salin file plugin ke folder `plugins/` di project SimpleContext kamu:

```bash
# Clone repo ini
git clone https://github.com/zacxyonly/SimpleContext-Plugin
cd SimpleContext-Plugin

# Salin plugin yang diinginkan
cp official/plugin-vector-search/vector_search_plugin.py /path/to/your-project/plugins/
```

Aktifkan di `config.yaml`:

```yaml
plugins:
  enabled: true
  folder: ./plugins

  vector_search_plugin:
    enabled: true
    provider: local       # local | openai | ollama
    top_k: 5
    min_score: 0.15
    tiers: [semantic, episodic]
```

### Lewat `sc.use()` (tanpa file)

```python
from plugins.vector_search_plugin import VectorSearchPlugin

sc = SimpleContext("config.yaml")
sc.use(VectorSearchPlugin(config={
    "provider": "local",
    "top_k": 5,
}))
```

---

## 🏗️ Struktur Repositori

```
SimpleContext-Plugin/
├── README.md                          ← Kamu di sini
├── CONTRIBUTING.md                    ← Panduan kontribusi
├── LICENSE
├── official/                          ← Plugin resmi (core team)
│   └── plugin-vector-search/
│       ├── vector_search_plugin.py    ← File plugin (taruh di ./plugins/)
│       └── README.md
├── community/                         ← Kontribusi komunitas
│   └── README.md
└── templates/
    └── plugin-starter/                ← Template untuk plugin baru
        ├── my_plugin.py
        └── README.md
```

---

## 🛠️ Buat Plugin Baru

1. Copy template:
   ```bash
   cp -r templates/plugin-starter community/plugin-namakalian
   ```
2. Edit `my_plugin.py` — rename class dan implementasi hook
3. Test lokal dengan SimpleContext
4. Submit Pull Request

Lihat [CONTRIBUTING.md](CONTRIBUTING.md) untuk detail lengkap.

---

## 🔗 Ekosistem

| Repositori | Deskripsi |
|------------|-----------|
| [SimpleContext](https://github.com/zacxyonly/SimpleContext) | Core engine — Universal AI Brain, zero dependencies |
| [SimpleContext-Plugin](https://github.com/zacxyonly/SimpleContext-Plugin) | Plugin registry *(kamu di sini)* |
| [SimpleContext-Bot](https://github.com/zacxyonly/SimpleContext-Bot) | AI Telegram Bot powered by SimpleContext — one-command setup, auto-downloads engine + agents |
| [SimpleContext-Agents](https://github.com/zacxyonly/SimpleContext-Agents) | Ready-to-use agent definitions for SimpleContext |

---

## 📄 License

MIT © [zacxyonly](https://github.com/zacxyonly)
