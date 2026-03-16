"""
Vector Search Plugin v1.0.0
Plugin resmi SimpleContext — semantic similarity search berbasis embedding.

Melengkapi keyword-based retrieval yang ada di ContextRetriever/ContextScorer
dengan pendekatan vector similarity, sehingga query "laptop rusak" bisa
menemukan memory "notebook error" meski kata-katanya berbeda.

Cara kerja:
  1. on_message_saved   → embed konten node baru, simpan ke vector index
  2. on_context_build   → embed query user terakhir, cari top-K node
                          paling mirip, inject ke messages sebagai context
  3. on_before_llm      → pass-through (context sudah ada)

Provider embedding yang didukung (via config):
  - "local"   : TF-IDF cosine — zero dependency, langsung jalan (default)
  - "openai"  : text-embedding-3-small via OpenAI API
  - "ollama"  : model lokal via Ollama REST API (misal: nomic-embed-text)

Pasang:
  Salin file ini ke folder plugins/ di project SimpleContext kamu.

Config di config.yaml:
    plugins:
      vector_search_plugin:
        enabled: true
        provider: local
        top_k: 5
        min_score: 0.15
        inject_as_system: true
        context_prefix: "\\n\\n[Vector Context]\\n"
        tiers: [semantic, episodic]
        # Untuk OpenAI:
        # provider: openai
        # openai_api_key: sk-...
        # openai_model: text-embedding-3-small
        # Untuk Ollama:
        # provider: ollama
        # ollama_url: http://localhost:11434
        # ollama_model: nomic-embed-text
"""

import re
import math
import json
import logging
from collections import defaultdict

from simplecontext.plugins.base import BasePlugin

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────

def _l2_normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in vec))
    if norm == 0.0:
        return vec
    return [x / norm for x in vec]


def _cosine(a: list[float], b: list[float]) -> float:
    """Cosine similarity dua vektor. Asumsi keduanya sudah ternormalisasi."""
    n = min(len(a), len(b))
    if n == 0:
        return 0.0
    return sum(a[i] * b[i] for i in range(n))


def _pad(vec: list[float], target: int) -> list[float]:
    if len(vec) >= target:
        return vec[:target]
    return vec + [0.0] * (target - len(vec))


# ──────────────────────────────────────────────────────────
# Embedding Providers
# ──────────────────────────────────────────────────────────

_STOPWORDS = {
    "yang", "dan", "di", "ke", "dari", "ini", "itu", "dengan", "untuk",
    "adalah", "ada", "saya", "kamu", "aku", "bisa", "mau", "pada", "akan",
    "the", "a", "an", "is", "are", "was", "i", "you", "we", "to", "of",
    "in", "it", "and", "or", "but", "do", "does", "did",
}


class LocalEmbedder:
    """
    TF-IDF embedder — zero dependency, vocab tumbuh dinamis seiring indexing.
    Cocok untuk development, small-scale, atau offline deployment.
    """

    def __init__(self):
        self._vocab:     dict[str, int]   = {}
        self._df:        dict[str, int]   = {}   # document frequency per term
        self._doc_count: int              = 0

    def _tokenize(self, text: str) -> list[str]:
        tokens = re.findall(r'\b[a-zA-Z0-9\u00C0-\u024F]{2,}\b', text.lower())
        return [t for t in tokens if t not in _STOPWORDS]

    def fit(self, texts: list[str]):
        """Update vocab dan IDF dari kumpulan teks baru."""
        for text in texts:
            tokens = set(self._tokenize(text))
            self._doc_count += 1
            for t in tokens:
                if t not in self._vocab:
                    self._vocab[t] = len(self._vocab)
                self._df[t] = self._df.get(t, 0) + 1

    def _idf(self, term: str) -> float:
        df = self._df.get(term, 0)
        if df == 0:
            return 0.0
        return math.log((self._doc_count + 1) / (df + 1)) + 1.0

    def embed(self, text: str) -> list[float]:
        tokens = self._tokenize(text)
        if not tokens or not self._vocab:
            return self._hash_embed(text)

        tf: dict[str, float] = defaultdict(float)
        for t in tokens:
            tf[t] += 1.0 / len(tokens)

        dim = len(self._vocab)
        vec = [0.0] * dim
        for term, freq in tf.items():
            idx = self._vocab.get(term)
            if idx is not None:
                vec[idx] = freq * self._idf(term)

        return _l2_normalize(vec)

    def _hash_embed(self, text: str, dim: int = 256) -> list[float]:
        """Fallback hash embedding 256-dim saat vocab masih kosong."""
        vec = [0.0] * dim
        for i, ch in enumerate(text.lower()):
            vec[ord(ch) % dim] += 1.0 / (i + 1)
        return _l2_normalize(vec)

    def state_dict(self) -> dict:
        return {
            "vocab":     self._vocab,
            "df":        self._df,
            "doc_count": self._doc_count,
        }

    def load_state(self, d: dict):
        self._vocab     = d.get("vocab", {})
        self._df        = d.get("df", {})
        self._doc_count = d.get("doc_count", 0)


class OpenAIEmbedder:
    """Embedding via OpenAI API (text-embedding-3-small, 1536-dim)."""

    def __init__(self, api_key: str, model: str = "text-embedding-3-small"):
        self._api_key = api_key
        self._model   = model

    def fit(self, texts: list[str]):
        pass  # stateless

    def embed(self, text: str) -> list[float]:
        import urllib.request
        payload = json.dumps({
            "input": text[:8000],
            "model": self._model,
        }).encode()
        req = urllib.request.Request(
            "https://api.openai.com/v1/embeddings",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._api_key}",
            },
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        return data["data"][0]["embedding"]

    def state_dict(self) -> dict:
        return {"model": self._model}

    def load_state(self, d: dict):
        self._model = d.get("model", self._model)


class OllamaEmbedder:
    """Embedding via Ollama REST API (jalankan model lokal)."""

    def __init__(self, url: str = "http://localhost:11434",
                 model: str = "nomic-embed-text"):
        self._url   = url.rstrip("/")
        self._model = model

    def fit(self, texts: list[str]):
        pass  # stateless

    def embed(self, text: str) -> list[float]:
        import urllib.request
        payload = json.dumps({
            "model":  self._model,
            "prompt": text[:4000],
        }).encode()
        req = urllib.request.Request(
            f"{self._url}/api/embeddings",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        return data["embedding"]

    def state_dict(self) -> dict:
        return {"url": self._url, "model": self._model}

    def load_state(self, d: dict):
        self._url   = d.get("url",   self._url)
        self._model = d.get("model", self._model)


# ──────────────────────────────────────────────────────────
# Plugin
# ──────────────────────────────────────────────────────────

class VectorSearchPlugin(BasePlugin):
    """
    Tambahkan semantic vector search ke SimpleContext sebagai komplemen
    keyword-based retrieval yang sudah ada.

    Drop file ini ke folder plugins/ kamu — tidak perlu install apa pun
    jika menggunakan provider "local" (default).
    """

    name        = "vector_search_plugin"
    version     = "1.0.0"
    description = "Semantic vector search berbasis embedding — komplemen keyword retrieval."
    depends_on  = []   # tidak bergantung plugin lain

    # ── Lifecycle ─────────────────────────────────────────

    def setup(self):
        cfg = self.config

        self._provider         = cfg.get("provider",         "local")
        self._top_k            = int(cfg.get("top_k",         5))
        self._min_score        = float(cfg.get("min_score",   0.15))
        self._inject_as_system = cfg.get("inject_as_system",  True)
        self._context_prefix   = cfg.get("context_prefix",   "\n\n[Vector Context]\n")
        self._tiers            = set(cfg.get("tiers",         ["semantic", "episodic"]))

        self._embedder = self._build_embedder(cfg)

        # Restore state embedder (penting untuk LocalEmbedder vocab/IDF)
        if self.state:
            saved = self.state.get("embedder_state")
            if saved and hasattr(self._embedder, "load_state"):
                try:
                    self._embedder.load_state(saved)
                    logger.info("[vector_search] Embedder state restored.")
                except Exception as e:
                    logger.warning(f"[vector_search] Gagal restore embedder state: {e}")

        logger.info(
            f"[vector_search] Ready — provider={self._provider} "
            f"top_k={self._top_k} min_score={self._min_score} "
            f"tiers={self._tiers}"
        )

    def teardown(self):
        # Persist embedder state saat shutdown
        if self.state and hasattr(self._embedder, "state_dict"):
            try:
                self.state.set("embedder_state", self._embedder.state_dict())
            except Exception:
                pass
        logger.info("[vector_search] Teardown — state tersimpan.")

    def _build_embedder(self, cfg: dict):
        provider = cfg.get("provider", "local")

        if provider == "openai":
            api_key = cfg.get("openai_api_key", "")
            model   = cfg.get("openai_model", "text-embedding-3-small")
            if not api_key:
                logger.warning("[vector_search] openai_api_key tidak diset, fallback ke local.")
                return LocalEmbedder()
            return OpenAIEmbedder(api_key=api_key, model=model)

        if provider == "ollama":
            url   = cfg.get("ollama_url",   "http://localhost:11434")
            model = cfg.get("ollama_model", "nomic-embed-text")
            return OllamaEmbedder(url=url, model=model)

        return LocalEmbedder()

    # ── Index helpers ─────────────────────────────────────

    def _load_index(self, user_id: str) -> dict:
        """
        Load vector index user dari plugin state.
        Format: { node_id: {"vec": [...], "content": "...", "tier": "..."} }
        """
        if not self.state:
            return {}
        raw = self.state.get(f"idx:{user_id}")
        if not raw:
            return {}
        return raw if isinstance(raw, dict) else {}

    def _save_index(self, user_id: str, index: dict):
        if not self.state:
            return
        try:
            self.state.set(f"idx:{user_id}", index)
            # Persist embedder vocab/IDF setiap kali index diupdate
            if hasattr(self._embedder, "state_dict"):
                self.state.set("embedder_state", self._embedder.state_dict())
        except Exception as e:
            logger.warning(f"[vector_search] Gagal simpan index: {e}")

    def _index_node(self, user_id: str, node_id: str,
                    content: str, tier: str):
        """Embed satu dokumen dan tambahkan ke index."""
        try:
            if hasattr(self._embedder, "fit"):
                self._embedder.fit([content])
            vec   = self._embedder.embed(content)
            index = self._load_index(user_id)
            index[node_id] = {
                "vec":     vec,
                "content": content[:500],
                "tier":    tier,
            }
            self._save_index(user_id, index)
        except Exception as e:
            logger.warning(f"[vector_search] Gagal index node {node_id!r}: {e}")

    def _search(self, user_id: str, query: str) -> list[dict]:
        """
        Cari top-K node paling relevan via cosine similarity.
        Return: [{"content": str, "score": float, "tier": str}, ...]
        """
        index = self._load_index(user_id)
        if not index:
            return []

        try:
            q_vec = self._embedder.embed(query)
        except Exception as e:
            logger.warning(f"[vector_search] Gagal embed query: {e}")
            return []

        results = []
        for entry in index.values():
            s_vec = entry.get("vec", [])
            if not s_vec:
                continue
            # Sesuaikan dimensi (vocab bisa berkembang setelah indexing pertama)
            dim = max(len(q_vec), len(s_vec))
            score = _cosine(_pad(q_vec, dim), _pad(s_vec, dim))
            if score >= self._min_score:
                results.append({
                    "content": entry.get("content", ""),
                    "score":   round(score, 4),
                    "tier":    entry.get("tier", ""),
                })

        results.sort(key=lambda x: x["score"], reverse=True)
        return results[: self._top_k]

    # ── Hooks ─────────────────────────────────────────────

    def on_message_saved(self, user_id: str, role: str, content: str,
                         tags: list, metadata: dict):
        """
        Setiap pesan yang disimpan ke tier yang dikonfigurasi akan langsung
        di-embed dan ditambahkan ke vector index user.
        """
        tier = (metadata or {}).get("tier", "working")
        if tier not in self._tiers:
            return

        # Gunakan node_id dari metadata kalau ada, fallback ke hash
        node_id = (metadata or {}).get("node_id") or f"{user_id}:{role}:{hash(content)}"
        self._index_node(user_id, node_id, content, tier)

    def on_context_build(self, user_id: str,
                         messages: list[dict]) -> list[dict]:
        """
        Saat context dibangun untuk LLM:
        1. Ambil query dari pesan user terakhir
        2. Jalankan vector search ke index
        3. Inject hasilnya ke system message

        Ini berjalan setelah keyword retrieval yang ada, sehingga LLM
        mendapat konteks dari kedua pendekatan.
        """
        if not messages:
            return messages

        # Ambil pesan user terakhir sebagai query
        query = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                c = msg.get("content", "")
                query = c if isinstance(c, str) else str(c)
                break

        if not query:
            return messages

        hits = self._search(user_id, query)
        if not hits:
            return messages

        lines = []
        for hit in hits:
            pct        = int(hit["score"] * 100)
            tier_label = hit["tier"].capitalize() if hit["tier"] else "Memory"
            lines.append(f"• [{tier_label} | {pct}% match] {hit['content']}")

        injected = self._context_prefix + "\n".join(lines)

        if self._inject_as_system and messages and messages[0]["role"] == "system":
            messages[0]["content"] += injected
        else:
            messages.insert(0, {
                "role":    "system",
                "content": injected.strip(),
            })

        logger.debug(
            f"[vector_search] {len(hits)} hits injected "
            f"untuk user={user_id!r} query={query[:40]!r}"
        )
        return messages

    def on_before_llm(self, user_id: str, agent_id: str,
                      messages: list[dict]) -> list[dict]:
        """Context sudah di-inject di on_context_build, tidak perlu apa-apa di sini."""
        return messages

    # ── Public API ────────────────────────────────────────

    def index_size(self, user_id: str) -> int:
        """Jumlah dokumen yang sudah di-index untuk user tertentu."""
        return len(self._load_index(user_id))

    def clear_index(self, user_id: str):
        """Hapus seluruh vector index untuk user tertentu."""
        if self.state:
            self.state.set(f"idx:{user_id}", {})
            logger.info(f"[vector_search] Index cleared — user={user_id!r}")

    def reindex(self, user_id: str, nodes: list):
        """
        Bangun ulang vector index dari list ContextNode.
        Berguna setelah ganti provider atau pertama kali setup.

        Contoh:
            plugin = sc.plugins.get("vector_search_plugin")
            nodes  = sc.context(user_id).get_all_active()
            plugin.reindex(user_id, nodes)
        """
        self.clear_index(user_id)
        texts = [n.content for n in nodes if hasattr(n, "content")]
        if texts and hasattr(self._embedder, "fit"):
            self._embedder.fit(texts)

        for node in nodes:
            tier = getattr(node.tier, "value", str(getattr(node, "tier", "")))
            if tier in self._tiers:
                self._index_node(user_id, node.id, node.content, tier)

        logger.info(
            f"[vector_search] Reindex selesai — "
            f"{self.index_size(user_id)} nodes untuk user={user_id!r}"
        )
