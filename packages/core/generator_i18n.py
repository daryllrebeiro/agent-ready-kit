"""Multilingual /llms.txt generator and international directory bundler."""

import os
from typing import Dict, List, Optional

LANGUAGE_TEMPLATES = {
    "en": {"title_suffix": "Documentation", "desc": "Official developer and agent documentation"},
    "es": {"title_suffix": "Documentación", "desc": "Documentación oficial para desarrolladores y agentes de IA"},
    "ja": {"title_suffix": "ドキュメント", "desc": "AIエージェントおよび開発者向け公式ドキュメント"},
    "de": {"title_suffix": "Dokumentation", "desc": "Offizielle Entwickler- und KI-Agenten-Dokumentation"},
    "fr": {"title_suffix": "Documentation", "desc": "Documentation officielle pour les développeurs et les agents IA"},
    "zh": {"title_suffix": "文档", "desc": "面向AI智能体和开发者的官方技术文档"},
}


class MultilingualLLMsGenerator:
    """Generates localized /llms.txt suites across international languages."""

    def generate_multilingual_bundle(
        self,
        site_name: str,
        root_url: str,
        languages: Optional[List[str]] = None,
    ) -> Dict[str, str]:
        """Generate root index llms.txt and language-specific subdirectories."""
        langs = languages or ["en", "es", "ja", "de", "fr", "zh"]
        clean_root = root_url.rstrip("/")
        files: Dict[str, str] = {}

        # 1. Root index llms.txt
        index_lines = [
            f"# {site_name} — Multilingual Index",
            "",
            f"> Central AI agent discovery directory for {site_name}. Select a language variant below.",
            "",
            "## International Language Portals",
            "",
        ]
        for l in langs:
            meta = LANGUAGE_TEMPLATES.get(l, {"title_suffix": "Docs", "desc": f"{site_name} documentation in {l}"})
            index_lines.append(f"- [{site_name} ({l.upper()})]({clean_root}/{l}/llms.txt): {meta['desc']}")

        files["llms.txt"] = "\n".join(index_lines)

        # 2. Localized llms.txt for each language
        for l in langs:
            meta = LANGUAGE_TEMPLATES.get(l, {"title_suffix": "Documentation", "desc": f"{site_name} documentation in {l}"})
            lines = [
                f"# {site_name} — {meta['title_suffix']}",
                "",
                f"> {meta['desc']}",
                "",
                "## Core Documentation",
                "",
                f"- [Overview]({clean_root}/{l}/docs/overview): Product overview and key capabilities in {l}.",
                f"- [API Reference]({clean_root}/{l}/docs/api): Complete API endpoints and schemas.",
                f"- [Full Context]({clean_root}/{l}/llms-full.txt): Complete raw markdown context for LLM ingestion.",
            ]
            files[f"{l}/llms.txt"] = "\n".join(lines)

        return files

    def write_bundle_to_disk(self, bundle: Dict[str, str], output_dir: str) -> Dict[str, str]:
        """Save multilingual bundle to disk with nested directories."""
        written = {}
        for rel_path, content in bundle.items():
            full_path = os.path.join(output_dir, rel_path)
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            with open(full_path, "w", encoding="utf-8") as f:
                f.write(content)
            written[rel_path] = full_path
        return written
