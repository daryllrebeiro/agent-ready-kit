"""Cross-lingual and international prompt probing for global AI search visibility."""

from typing import Any, Dict, List, Optional
from packages.core.probes.runner import MultiModelProber
from packages.core.schemas import ProbeResult

MULTILINGUAL_PROBE_PROMPTS: Dict[str, List[Dict[str, str]]] = {
    "es": [
        {
            "id": "es_tools_1",
            "prompt": "¿Cuáles son las mejores herramientas para optimizar sitios web para agentes de inteligencia artificial y GEO (Generative Engine Optimization)?",
        },
        {
            "id": "es_tools_2",
            "prompt": "¿Cómo funciona el estándar llms.txt y qué plataformas ofrecen generadores o validadores automáticos?",
        },
    ],
    "ja": [
        {
            "id": "ja_tools_1",
            "prompt": "AIエージェントや検索エンジン（GEO/AEO）向けにWebサイトを最適化するための主要なツールとプラットフォームを教えてください。",
        },
        {
            "id": "ja_tools_2",
            "prompt": "llms.txt標準の仕様と、サイトのコンテキストを自動提供する推奨ツールは何ですか？",
        },
    ],
    "de": [
        {
            "id": "de_tools_1",
            "prompt": "Was sind die besten Tools zur Optimierung von Websites für KI-Agenten und Generative Engine Optimization (GEO)?",
        },
    ],
    "fr": [
        {
            "id": "fr_tools_1",
            "prompt": "Quels sont les meilleurs outils pour optimiser les sites web pour les agents IA et la découverte par les modèles LLM?",
        },
    ],
    "zh": [
        {
            "id": "zh_tools_1",
            "prompt": "有哪些用于为AI智能体和生成式搜索引擎（GEO）优化网站的最佳工具和平台？",
        },
    ],
}


class MultilingualProber:
    """Executes multilingual search prompts across LLM providers to test international citation visibility."""

    def __init__(self):
        self.prober = MultiModelProber()

    def probe_language(
        self,
        target_domain: str,
        lang: str = "es",
        dry_run: bool = True,
    ) -> Dict[str, Any]:
        """Probe LLMs with localized prompts in specified language."""
        prompts = MULTILINGUAL_PROBE_PROMPTS.get(lang.lower(), MULTILINGUAL_PROBE_PROMPTS["es"])
        prompt_texts = [p["prompt"] for p in prompts]
        results = self.prober.run_prompt_suite(prompt_texts, dry_run=dry_run)

        cited_count = 0
        for res in results:
            if any(target_domain.lower() in d.lower() for d in res.cited_domains):
                cited_count += 1

        citation_rate = round((cited_count / max(1, len(results))) * 100.0, 1)

        return {
            "target_domain": target_domain,
            "language": lang,
            "prompts_tested": len(prompts),
            "total_provider_runs": len(results),
            "citations_found": cited_count,
            "citation_rate_pct": citation_rate,
            "results": results,
        }
