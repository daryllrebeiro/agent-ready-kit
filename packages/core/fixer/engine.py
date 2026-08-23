"""Automated remediation engine generating drop-in fixes for AI agent readiness."""

import json
import os
from typing import Any, Dict, Optional
from urllib.parse import urlparse
from packages.core.generator import LLMsGenerator
from packages.core.schemas import Score
from packages.core.scorer import Scorer


class FixerEngine:
    """Generates turnkey file fixes (llms.txt, robots.txt, schema-ld.json) for a website."""

    def __init__(self):
        self.generator = LLMsGenerator()
        self.scorer = Scorer()

    def generate_all_fixes(
        self,
        url: str,
        site_name: Optional[str] = None,
        site_description: Optional[str] = None,
    ) -> Dict[str, str]:
        """Generate full remediation bundle for a target URL."""
        parsed = urlparse(url if "://" in url else f"https://{url}")
        domain = parsed.netloc or parsed.path
        name = site_name or domain.replace("www.", "").split(".")[0].title()
        desc = site_description or f"Official agent-ready documentation and API reference for {name}."
        root_url = f"{parsed.scheme or 'https'}://{domain}"

        # 1. Generate llms.txt
        pages = [self.generator.extract_page_summary(root_url)]
        llms_txt = self.generator.generate_llms_txt(name, desc, pages)

        # 2. Generate llms-full.txt stub
        llms_full_txt = f"# {name} — Full Context\n\n> {desc}\n\n## Overview\nComplete product context and system guides for AI agents.\n"

        # 3. Generate optimal AI-friendly robots.txt
        robots_txt = (
            "# AgentReady Optimized robots.txt\n"
            "User-agent: *\n"
            "Allow: /\n\n"
            "# Major AI Crawlers\n"
            "User-agent: GPTBot\n"
            "Allow: /\n\n"
            "User-agent: ClaudeBot\n"
            "Allow: /\n\n"
            "User-agent: PerplexityBot\n"
            "Allow: /\n\n"
            "User-agent: Google-Extended\n"
            "Allow: /\n\n"
            f"Sitemap: {root_url}/sitemap.xml\n"
        )

        # 4. Generate JSON-LD Schema snippet
        schema_json = self.generator.generate_json_ld_template(name, root_url, desc)

        return {
            "llms.txt": llms_txt,
            "llms-full.txt": llms_full_txt,
            "robots.txt": robots_txt,
            "schema-ld.json": schema_json,
        }

    def apply_fixes_to_directory(self, fixes: Dict[str, str], output_dir: str) -> Dict[str, str]:
        """Write generated fix files to disk."""
        os.makedirs(output_dir, exist_ok=True)
        written_paths = {}
        for filename, content in fixes.items():
            path = os.path.join(output_dir, filename)
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            written_paths[filename] = path
        return written_paths
