# plugin-vector-search

> Plugin resmi SimpleContext — semantic vector search berbasis embedding sebagai komplemen keyword retrieval.

[![SimpleContext](https://img.shields.io/badge/SimpleContext-v4.2-blueviolet?style=flat-square)](https://github.com/zacxyonly/SimpleContext)
[![Version](https://img.shields.io/badge/version-1.0.0-blue?style=flat-square)]()
[![Zero Dependency](https://img.shields.io/badge/dependencies-zero%20(local%20mode)-success?style=flat-square)]()

---

## Mengapa Plugin Ini?

SimpleContext sudah punya keyword-based retrieval yang solid di `ContextRetriever` dan `ContextScorer`. Tapi keyword search punya keterbatasan:

```
Query  : "laptop sering hang"
Memory : "notebook error saat multitasking"
Keyword: ❌ tidak match (kata berbeda)
Vector : ✅ match (makna serupa)
```

Plugin ini menambahkan lapisan semantic search di atas keyword retrieval yang sudah ada — keduanya berjalan bersama.

---

## Cara Pasang

1. Salin `vector_search_plugin.py` ke folder `plugins/` di project SimpleContext kamu:

```bash
cp vector_search_plugin.py /path/to/your-project/plugins/
```

2. Aktifkan di `config.yaml`:

```yaml
plugins:
  enabled: true
  folder: ./plugins

  vector_search_plugin:
    enabled: true
    provider: local
    top_k: 5
    min_score: 0.15
    tiers: [semantic, episodic]
```

Selesai. Tidak perlu install package tambahan untuk mode `local`.

---

## Konfigurasi

| Option | Type | Default | Deskripsi |
|--------|------|---------|-----------|
| `provider` | string | `"local"` | Engine embedding: `local`, `openai`, `ollama` |
| `top_k` | int | `5` | Jumlah hasil vector search yang di-inject ke context |
| `min_score` | float | `0.15` | Minimum cosine similarity (0.0–1.0) |
| `inject_as_system` | bool | `true` | Inject ke system message (true) atau buat message baru (false) |
| `context_prefix` | string | `"\n\n[Vector Context]\n"` | Header sebelum daftar hasil |
| `tiers` | list | `["semantic", "episodic"]` | Tier yang di-index dan di-search |

### Provider: local (default)

Tidak perlu setup. TF-IDF cosine similarity dengan vocab yang tumbuh dinamis.

```yaml
vector_search_plugin:
  provider: local
```

### Provider: openai

```yaml
vector_search_plugin:
  provider: openai
  openai_api_key: sk-...
  openai_model: text-embedding-3-small   # default
```

### Provider: ollama

Jalankan Ollama dulu, pull model embedding:
```bash
ollama pull nomic-embed-text
```

```yaml
vector_search_plugin:
  provider: ollama
  ollama_url: http://localhost:11434
  ollama_model: nomic-embed-text
```

---

## Cara Kerja

```
Pesan baru disimpan
        │
        ▼
 on_message_saved
   └── embed konten → simpan ke vector index (plugin state, persisten)

Context mau dikirim ke LLM
        │
        ▼
 on_context_build
   ├── ambil query dari pesan user terakhir
   ├── embed query
   ├── cosine similarity ke seluruh index user
   ├── ambil top-K hits (score ≥ min_score)
   └── inject ke system message:
       • [Semantic | 78% match] user suka Python ...
       • [Episodic | 65% match] error saat install numpy ...
```

Vector search berjalan **setelah** keyword retrieval — LLM mendapat konteks dari kedua pendekatan.

---

## Reindex Ulang

Jika kamu baru pasang plugin tapi memory sudah ada, jalankan reindex:

```python
plugin = sc.plugins.get("vector_search_plugin")
nodes  = sc.context(user_id).get_all_active()
plugin.reindex(user_id, nodes)
```

---

## Debug

```python
plugin = sc.plugins.get("vector_search_plugin")
print(f"Index size: {plugin.index_size(user_id)} nodes")

# Hapus index (akan di-rebuild otomatis saat ada pesan baru)
plugin.clear_index(user_id)
```

---

## License

MIT © [zacxyonly](https://github.com/zacxyonly)
