#!/usr/bin/env python3
"""
scripts/update_readme.py
Auto-generate tabel plugin di README.md berdasarkan folder official/.

Cara kerja:
  - Scan semua folder di official/plugin-*/
  - Baca metadata dari file .py (name, version, description, app_commands)
  - Generate tabel Markdown
  - Replace section antara marker <!-- PLUGINS_TABLE_START --> dan <!-- PLUGINS_TABLE_END -->

Dijalankan oleh GitHub Actions setiap push ke main.
"""

import os
import re
import ast
import sys
from pathlib import Path


# Emoji per plugin name
PLUGIN_EMOJI = {
    "vector_search_plugin": "🔍",
    "analytics_plugin":     "📊",
    "summarizer_plugin":    "📝",
    "web_search_plugin":    "🌐",
    "translate_plugin":     "🌏",
    "sentiment_plugin":     "😊",
    "rate_limiter_plugin":  "⏱",
}

DEFAULT_EMOJI = "🔌"

MARKERS = (
    "<!-- PLUGINS_TABLE_START -->",
    "<!-- PLUGINS_TABLE_END -->",
)


def extract_plugin_meta(py_file: Path) -> dict | None:
    """
    Extract metadata plugin dari file .py tanpa mengeksekusinya.
    Baca class attributes: name, version, description, app_commands.
    """
    try:
        source = py_file.read_text(encoding="utf-8")
        tree   = ast.parse(source)
    except Exception as e:
        print(f"  ⚠️  Parse error {py_file.name}: {e}", file=sys.stderr)
        return None

    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue

        meta = {"name": "", "version": "1.0.0", "description": "", "commands": []}

        for item in node.body:
            if not isinstance(item, ast.Assign):
                continue
            for target in item.targets:
                if not isinstance(target, ast.Name):
                    continue
                key = target.id

                if key == "name" and isinstance(item.value, ast.Constant):
                    meta["name"] = item.value.value

                elif key == "version" and isinstance(item.value, ast.Constant):
                    meta["version"] = item.value.value

                elif key == "description" and isinstance(item.value, ast.Constant):
                    meta["description"] = item.value.value

                elif key == "app_commands" and isinstance(item.value, ast.Dict):
                    for k in item.value.keys:
                        if isinstance(k, ast.Constant):
                            meta["commands"].append(k.value)

        if meta["name"]:
            return meta

    return None


def scan_plugins(official_dir: Path) -> list[dict]:
    """Scan semua plugin di official/ dan kembalikan metadata."""
    plugins = []

    for plugin_dir in sorted(official_dir.iterdir()):
        if not plugin_dir.is_dir() or not plugin_dir.name.startswith("plugin-"):
            continue

        # Cari file .py plugin (bukan __init__)
        py_files = [f for f in plugin_dir.glob("*.py") if not f.name.startswith("_")]
        if not py_files:
            print(f"  ⚠️  No .py found in {plugin_dir.name}", file=sys.stderr)
            continue

        meta = extract_plugin_meta(py_files[0])
        if not meta:
            continue

        meta["folder"]   = plugin_dir.name
        meta["filename"] = py_files[0].name
        plugins.append(meta)
        print(f"  ✅ {plugin_dir.name} — {meta['name']} v{meta['version']}")

    return plugins


def build_table(plugins: list[dict]) -> str:
    """Build Markdown tabel dari list plugin metadata."""
    lines = [
        "| Plugin | Deskripsi | Versi | Commands |",
        "|--------|-----------|-------|----------|",
    ]

    for p in plugins:
        emoji    = PLUGIN_EMOJI.get(p["name"], DEFAULT_EMOJI)
        folder   = p["folder"]
        name     = p["name"].replace("_", "-")
        version  = p["version"]
        desc     = p["description"]
        commands = ", ".join(f"`/{c}`" for c in p["commands"]) if p["commands"] else "—"
        link     = f"[`{folder}`](./official/{folder}/)"

        lines.append(f"| {emoji} {link} | {desc} | `{version}` | {commands} |")

    return "\n".join(lines)


def update_readme(readme_path: Path, table: str) -> bool:
    """Replace konten antara markers di README dengan tabel baru."""
    content = readme_path.read_text(encoding="utf-8")

    start_marker, end_marker = MARKERS
    pattern = re.compile(
        re.escape(start_marker) + r".*?" + re.escape(end_marker),
        re.DOTALL,
    )

    new_section = f"{start_marker}\n{table}\n{end_marker}"

    if not re.search(pattern, content):
        print(f"  ❌ Markers tidak ditemukan di {readme_path}", file=sys.stderr)
        print(f"     Tambahkan:\n     {start_marker}\n     {end_marker}", file=sys.stderr)
        return False

    new_content = re.sub(pattern, new_section, content)

    if new_content == content:
        print("  ℹ️  README tidak berubah.")
        return True

    readme_path.write_text(new_content, encoding="utf-8")
    print(f"  ✅ README updated: {readme_path}")
    return True


def main():
    repo_root    = Path(__file__).parent.parent
    official_dir = repo_root / "official"
    readme_path  = repo_root / "README.md"

    if not official_dir.exists():
        print(f"❌ Folder tidak ditemukan: {official_dir}", file=sys.stderr)
        sys.exit(1)

    print("🔍 Scanning plugins...")
    plugins = scan_plugins(official_dir)
    print(f"\n📦 Found {len(plugins)} plugins\n")

    table = build_table(plugins)
    print("Generated table:\n")
    print(table)
    print()

    if not update_readme(readme_path, table):
        sys.exit(1)

    print(f"\n✅ Done — {len(plugins)} plugins in table")


if __name__ == "__main__":
    main()
