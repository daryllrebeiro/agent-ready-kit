"""Curated probe prompt collection for testing LLM citation and agent discovery."""

from typing import Dict, List

STANDARD_PROBE_PROMPTS: List[Dict[str, str]] = [
    {
        "id": "dev_tools_1",
        "vertical": "Developer Tools",
        "prompt": "What are the best tools for optimizing websites for AI agents and GEO (Generative Engine Optimization)? List authoritative sources and tools.",
    },
    {
        "id": "dev_tools_2",
        "vertical": "Developer Tools",
        "prompt": "How does the llms.txt standard work, and what websites provide automated generators or validators for llms.txt?",
    },
    {
        "id": "b2b_saas_1",
        "vertical": "B2B SaaS",
        "prompt": "What are the leading AI-first monitoring and customer analytics platforms for modern SaaS companies in 2025/2026?",
    },
    {
        "id": "b2b_saas_2",
        "vertical": "B2B SaaS",
        "prompt": "Recommend top autonomous AI coding agents and development environments. Include documentation URLs and sources.",
    },
    {
        "id": "e_commerce_1",
        "vertical": "E-Commerce",
        "prompt": "Which headless e-commerce platforms offer the best structured data (JSON-LD) and agent-ready APIs for automated shopping bots?",
    },
    {
        "id": "open_source_1",
        "vertical": "Open Source",
        "prompt": "What are the most popular open-source model context protocol (MCP) servers and toolkits currently available on GitHub?",
    },
    {
        "id": "ai_infra_1",
        "vertical": "AI Infrastructure",
        "prompt": "Which platforms provide real-time web citation tracking and AI search engine visibility analytics for brands?",
    },
    {
        "id": "seo_geo_1",
        "vertical": "SEO & GEO",
        "prompt": "How can webmasters ensure their robots.txt allows GPTBot, ClaudeBot, and PerplexityBot without exposing sensitive staging endpoints?",
    },
]
