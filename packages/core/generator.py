"""Generator module for producing compliant llms.txt, llms-full.txt, and structured data."""

import re
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse
import requests
from bs4 import BeautifulSoup


class LLMsGenerator:
    """Generates llms.txt and related agent-readiness files from site metadata or sitemaps."""

    def __init__(self, timeout_seconds: float = 10.0):
        self.timeout_seconds = timeout_seconds

    def parse_sitemap(self, sitemap_url: str, max_urls: int = 50) -> List[str]:
        """Fetch and extract URLs from a sitemap XML."""
        urls: List[str] = []
        try:
            resp = requests.get(sitemap_url, timeout=self.timeout_seconds)
            if resp.status_code != 200:
                return urls

            root = ET.fromstring(resp.content)
            # Remove namespace if present
            ns = {"ns": root.tag.split("}")[0].strip("{")} if "}" in root.tag else {}

            loc_nodes = root.findall(".//ns:loc", ns) if ns else root.findall(".//loc")
            for node in loc_nodes:
                if node.text and node.text.strip():
                    urls.append(node.text.strip())
                if len(urls) >= max_urls:
                    break
        except Exception:
            pass
        return urls

    def extract_page_summary(self, url: str) -> Dict[str, str]:
        """Extract title and meta description for a given URL."""
        title = urlparse(url).path.strip("/").replace("-", " ").replace("_", " ").title() or "Home"
        description = ""
        try:
            resp = requests.get(url, timeout=self.timeout_seconds)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                if soup.title and soup.title.string:
                    title = soup.title.string.strip()
                desc_tag = soup.find("meta", attrs={"name": "description"}) or soup.find("meta", attrs={"property": "og:description"})
                if desc_tag and desc_tag.get("content"):
                    description = desc_tag.get("content", "").strip()
        except Exception:
            pass
        return {"url": url, "title": title, "description": description}

    def generate_llms_txt(
        self,
        site_name: str,
        site_description: str,
        pages: List[Dict[str, str]],
    ) -> str:
        """Generate spec-compliant llms.txt markdown."""
        lines = [
            f"# {site_name}",
            "",
            f"> {site_description}",
            "",
            "## Documentation & Core Resources",
            "",
        ]

        if not pages:
            lines.append("- [Overview](https://example.com/docs): Comprehensive product documentation and reference guides.")
        else:
            for page in pages:
                title = page.get("title", "Resource")
                url = page.get("url", "#")
                desc = page.get("description")
                if desc:
                    lines.append(f"- [{title}]({url}): {desc}")
                else:
                    lines.append(f"- [{title}]({url})")

        lines.extend([
            "",
            "## Optional",
            "",
            "- [Full Context](/llms-full.txt): Consolidated single-document context for deep retrieval.",
        ])

        return "\n".join(lines)

    def generate_json_ld_template(
        self,
        site_name: str,
        site_url: str,
        site_description: str,
    ) -> str:
        """Generate starter JSON-LD Organization and WebSite markup."""
        template = {
            "@context": "https://schema.org",
            "@graph": [
                {
                    "@type": "WebSite",
                    "@id": f"{site_url}/#website",
                    "url": site_url,
                    "name": site_name,
                    "description": site_description,
                },
                {
                    "@type": "Organization",
                    "@id": f"{site_url}/#organization",
                    "name": site_name,
                    "url": site_url,
                    "description": site_description,
                },
            ],
        }
        import json
        return json.dumps(template, indent=2)
