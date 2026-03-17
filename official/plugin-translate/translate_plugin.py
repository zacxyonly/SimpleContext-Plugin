"""
Translate Plugin v1.0.0
Plugin resmi SimpleContext — penerjemah multi-bahasa otomatis.

Cara kerja:
  on_before_llm → terjemahkan input user ke bahasa agent jika perlu
  on_after_llm  → terjemahkan response ke bahasa preferensi user

Provider yang didukung:
  - "llm"    : gunakan LLM yang sudah dikonfigurasi (default, no extra dep)
  - "libre"  : LibreTranslate self-hosted (free, open source)
  - "mymemory": MyMemory API (free tier tersedia, no key untuk basic)

app_commands:
  /translate <lang>         — set bahasa output (id, en, ja, ko, zh, ar, ...)
  /translate auto           — kembali ke auto-detect
  /translate this to <lang> — terjemahkan pesan terakhir ke bahasa tertentu

Config di config.yaml:
    plugins:
      translate_plugin:
        enabled: true
        provider: llm            # llm | libre | mymemory
        agent_language: en       # bahasa default agent
        auto_detect: true        # auto-detect bahasa user
        libre_url: http://localhost:5000  # untuk provider=libre
        mymemory_email: ""       # email untuk mymemory (optional, tingkatkan limit)
        llm_provider: gemini     # untuk provider=llm
        llm_model: ""
        llm_api_key: ""
        llm_base_url: ""
"""

import logging
import urllib.request
import urllib.parse
import json

from simplecontext.plugins.base import BasePlugin, AppCommandContext

logger = logging.getLogger(__name__)

# ISO 639-1 language names
_LANG_NAMES = {
    "id": "Indonesian", "en": "English", "ja": "Japanese", "ko": "Korean",
    "zh": "Chinese", "ar": "Arabic", "es": "Spanish", "fr": "French",
    "de": "German", "pt": "Portuguese", "ru": "Russian", "hi": "Hindi",
    "th": "Thai", "vi": "Vietnamese", "ms": "Malay", "nl": "Dutch",
    "it": "Italian", "tr": "Turkish", "pl": "Polish", "sv": "Swedish",
}

_ID_WORDS = {"yang", "dan", "di", "ke", "dari", "ini", "itu", "adalah", "saya", "aku", "tidak", "bisa"}
_JA_RANGE = (0x3040, 0x30FF)
_KO_RANGE = (0xAC00, 0xD7A3)
_ZH_RANGE = (0x4E00, 0x9FFF)
_AR_RANGE = (0x0600, 0x06FF)

_DEFAULT_MODELS = {
    "gemini": "gemini/gemini-2.0-flash",
    "openai": "gpt-4o-mini",
    "ollama": "llama3",
}


def _detect_lang(text: str) -> str:
    """Deteksi bahasa sederhana berbasis heuristic."""
    if not text:
        return "en"

    # Cek karakter non-Latin
    for ch in text:
        cp = ord(ch)
        if _JA_RANGE[0] <= cp <= _JA_RANGE[1]:
            return "ja"
        if _KO_RANGE[0] <= cp <= _KO_RANGE[1]:
            return "ko"
        if _ZH_RANGE[0] <= cp <= _ZH_RANGE[1]:
            return "zh"
        if _AR_RANGE[0] <= cp <= _AR_RANGE[1]:
            return "ar"

    # Cek kata Indonesia
    words = set(text.lower().split())
    if len(words & _ID_WORDS) >= 2:
        return "id"

    return "en"


def _translate_with_llm(text: str, target_lang: str, provider: str,
                         model: str, api_key: str, base_url: str) -> str | None:
    """Terjemahkan menggunakan LLM."""
    lang_name = _LANG_NAMES.get(target_lang, target_lang)
    prompt    = (
        f"Translate the following text to {lang_name}. "
        f"Return ONLY the translation, no explanation, no quotes.\n\n"
        f"Text: {text}"
    )
    try:
        import litellm
        kwargs: dict = {
            "model":      model,
            "messages":   [{"role": "user", "content": prompt}],
            "max_tokens": 500,
        }
        if provider == "ollama":
            kwargs["api_base"] = base_url or "http://localhost:11434"
            if not model.startswith("ollama/"):
                kwargs["model"] = f"ollama/{model}"
        elif api_key:
            kwargs["api_key"] = api_key
        return litellm.completion(**kwargs).choices[0].message.content.strip()
    except Exception as e:
        logger.warning(f"[translate] LLM error: {e}")
        return None


def _translate_libre(text: str, source: str, target: str, url: str) -> str | None:
    """Terjemahkan via LibreTranslate."""
    try:
        payload = json.dumps({
            "q": text, "source": source, "target": target, "format": "text"
        }).encode()
        req = urllib.request.Request(
            f"{url.rstrip('/')}/translate", data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read())
        return data.get("translatedText")
    except Exception as e:
        logger.warning(f"[translate] LibreTranslate error: {e}")
        return None


def _translate_mymemory(text: str, source: str, target: str, email: str = "") -> str | None:
    """Terjemahkan via MyMemory API (free tier)."""
    try:
        encoded = urllib.parse.quote(text[:500])
        url     = f"https://api.mymemory.translated.net/get?q={encoded}&langpair={source}|{target}"
        if email:
            url += f"&de={email}"
        req  = urllib.request.Request(url, headers={"User-Agent": "SimpleContext-Bot/1.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read())
        if data.get("responseStatus") == 200:
            return data["responseData"]["translatedText"]
        return None
    except Exception as e:
        logger.warning(f"[translate] MyMemory error: {e}")
        return None


class TranslatePlugin(BasePlugin):
    """Penerjemah multi-bahasa untuk SimpleContext."""

    name        = "translate_plugin"
    version     = "1.0.0"
    description = "Penerjemah multi-bahasa — auto-detect bahasa user dan terjemahkan response."
    depends_on  = []

    app_commands = {
        "translate": {
            "description": "Set bahasa atau terjemahkan teks",
            "usage":       "/translate <lang> | /translate auto | /translate this to <lang>",
            "handler":     "handle_translate",
            "args_hint":   "<lang|auto|this to <lang>>",
        },
    }

    # ── Lifecycle ─────────────────────────────────────────

    def setup(self):
        self._provider       = self.config.get("provider", "llm")
        self._agent_lang     = self.config.get("agent_language", "en")
        self._auto_detect    = self.config.get("auto_detect", True)
        self._libre_url      = self.config.get("libre_url", "http://localhost:5000")
        self._mm_email       = self.config.get("mymemory_email", "")
        self._llm_provider   = self.config.get("llm_provider", "gemini")
        self._llm_model      = self.config.get("llm_model", "") or _DEFAULT_MODELS.get(self._llm_provider, "gemini/gemini-2.0-flash")
        self._llm_api_key    = self.config.get("llm_api_key", "")
        self._llm_base_url   = self.config.get("llm_base_url", "")
        logger.info(f"[translate] Initialized — provider={self._provider} agent_lang={self._agent_lang}")

    # ── Core Translation ──────────────────────────────────

    def _translate(self, text: str, source: str, target: str) -> str | None:
        if source == target:
            return text
        if self._provider == "libre":
            return _translate_libre(text, source, target, self._libre_url)
        if self._provider == "mymemory":
            return _translate_mymemory(text, source, target, self._mm_email)
        # Default: LLM
        return _translate_with_llm(
            text, target,
            self._llm_provider, self._llm_model,
            self._llm_api_key, self._llm_base_url,
        )

    def _get_user_lang(self, user_id: str) -> str:
        return self.state.get(f"lang:{user_id}", "auto")

    def _set_user_lang(self, user_id: str, lang: str):
        self.state.set(f"lang:{user_id}", lang)

    # ── Hooks ─────────────────────────────────────────────

    def on_before_llm(self, user_id: str, agent_id: str,
                      messages: list[dict]) -> list[dict]:
        """
        Jika user memakai bahasa non-agent, inject instruksi ke system message
        agar LLM reply dalam bahasa yang sama dengan user.
        """
        if not self._auto_detect or not messages:
            return messages

        user_lang = self._get_user_lang(user_id)

        # Ambil teks user terakhir untuk deteksi bahasa
        user_text = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                c = msg.get("content", "")
                user_text = c if isinstance(c, str) else ""
                break

        if not user_text:
            return messages

        # Tentukan bahasa aktual
        if user_lang == "auto":
            detected = _detect_lang(user_text)
        else:
            detected = user_lang

        # Simpan bahasa terdeteksi untuk on_after_llm
        self.state.set(f"detected:{user_id}", detected)

        # Inject instruksi bahasa ke system message
        if detected and detected != self._agent_lang:
            lang_name = _LANG_NAMES.get(detected, detected)
            instruction = f"\n\nIMPORTANT: The user is writing in {lang_name}. Reply in {lang_name}."
            if messages[0]["role"] == "system":
                messages[0]["content"] += instruction
            else:
                messages.insert(0, {"role": "system", "content": instruction.strip()})

        return messages

    def on_after_llm(self, user_id: str, agent_id: str, response: str) -> str:
        """
        Terjemahkan response jika user sudah set bahasa eksplisit
        yang berbeda dari bahasa agent, dan provider bukan 'llm'
        (kalau llm, instruksi di on_before_llm sudah cukup).
        """
        if self._provider == "llm":
            return response  # sudah ditangani via system prompt

        user_lang = self._get_user_lang(user_id)
        if user_lang in ("auto", self._agent_lang, ""):
            return response

        translated = self._translate(response, self._agent_lang, user_lang)
        if translated:
            self.state.increment("total_translations")
            return translated
        return response

    # ── App Command Handlers ───────────────────────────────

    async def handle_translate(self, ctx: AppCommandContext) -> str:
        """
        /translate id            → set bahasa ke Indonesia
        /translate auto          → kembali ke auto-detect
        /translate this to en    → terjemahkan pesan terakhir
        /translate               → lihat bahasa aktif
        """
        args = ctx.args
        uid  = ctx.user_id

        if not args:
            current   = self._get_user_lang(uid)
            lang_name = _LANG_NAMES.get(current, current)
            lines     = [
                f"🌐 *Language Settings*\n",
                f"Current: `{current}` ({lang_name})\n",
                "Set with: `/translate <lang_code>`\n",
                "Supported codes:",
            ]
            codes = ", ".join(f"`{k}`" for k in sorted(_LANG_NAMES.keys()))
            lines.append(codes)
            return "\n".join(lines)

        # /translate auto
        if args[0].lower() == "auto":
            self._set_user_lang(uid, "auto")
            return "✅ Language set to *auto-detect*."

        # /translate this to <lang>
        if len(args) >= 3 and args[0].lower() == "this" and args[1].lower() == "to":
            target    = args[2].lower()
            sc        = ctx.sc
            last_text = ""

            if sc:
                try:
                    history = sc.memory(uid).get_for_llm(limit=5)
                    for msg in reversed(history):
                        if msg.get("role") == "assistant":
                            c = msg.get("content", "")
                            last_text = c if isinstance(c, str) else ""
                            break
                except Exception:
                    pass

            if not last_text:
                return "❌ Tidak ada pesan sebelumnya yang bisa diterjemahkan."

            source      = _detect_lang(last_text)
            translated  = self._translate(last_text, source, target)

            if not translated:
                return f"❌ Gagal menerjemahkan. Cek konfigurasi provider `{self._provider}`."

            lang_name = _LANG_NAMES.get(target, target)
            self.state.increment("total_translations")
            return f"🌐 *Translated to {lang_name}:*\n\n{translated}"

        # /translate <lang_code>
        lang = args[0].lower()
        if lang not in _LANG_NAMES:
            supported = ", ".join(f"`{k}`" for k in sorted(_LANG_NAMES.keys()))
            return (
                f"❌ Bahasa `{lang}` tidak dikenal.\n\n"
                f"Kode yang didukung:\n{supported}"
            )

        self._set_user_lang(uid, lang)
        lang_name = _LANG_NAMES[lang]
        return (
            f"✅ Language set to *{lang_name}* (`{lang}`).\n\n"
            f"Semua respons berikutnya akan dalam {lang_name}.\n"
            f"Reset: `/translate auto`"
        )
