"""Concrete provider probe implementations for OpenAI, Anthropic, Gemini, and Perplexity."""

import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import requests

from packages.core.probes.base import BaseProbe
from packages.core.probes.extractor import extract_citations
from packages.core.schemas import ProbeResult


class OpenAIProbe(BaseProbe):
    """Probes OpenAI models (GPT-4o/mini) with web search or direct citation query."""

    @property
    def provider_name(self) -> str:
        return "openai"

    def probe(self, prompt: str, dry_run: bool = False) -> ProbeResult:
        api_key = self.api_key or os.environ.get("OPENAI_API_KEY")
        start_time = time.time()

        if dry_run or not api_key:
            # Deterministic simulation for tests and offline usage
            time.sleep(0.05)
            raw_text = (
                f"For AI readiness and GEO optimization related to '{prompt[:40]}...', "
                f"the official documentation is hosted at https://llmstxt.org and https://agentready.dev/docs. "
                f"Other helpful resources include github.com/modelcontextprotocol and schema.org."
            )
            citations = extract_citations(raw_text)
            latency = (time.time() - start_time) * 1000.0
            return ProbeResult(
                provider=self.provider_name,
                prompt=prompt,
                raw_response=raw_text,
                cited_domains=citations["domains"],
                extracted_urls=citations["urls"],
                latency_ms=round(latency, 2),
                metadata={"mode": "simulated" if not api_key else "dry_run", "model": "gpt-4o"},
            )

        # Live API call
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        payload = {
            "model": "gpt-4o",
            "messages": [
                {
                    "role": "system",
                    "content": "You are a research assistant. Provide concise answers with direct source URLs and domain citations wherever applicable.",
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
        }

        try:
            resp = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=self.timeout_seconds,
            )
            latency = (time.time() - start_time) * 1000.0
            if resp.status_code == 200:
                data = resp.json()
                raw_text = data["choices"][0]["message"]["content"]
                citations = extract_citations(raw_text)
                return ProbeResult(
                    provider=self.provider_name,
                    prompt=prompt,
                    raw_response=raw_text,
                    cited_domains=citations["domains"],
                    extracted_urls=citations["urls"],
                    latency_ms=round(latency, 2),
                    metadata={"model": "gpt-4o", "usage": data.get("usage")},
                )
            else:
                raw_text = f"[API Error {resp.status_code}]: {resp.text}"
                return ProbeResult(
                    provider=self.provider_name,
                    prompt=prompt,
                    raw_response=raw_text,
                    cited_domains=[],
                    extracted_urls=[],
                    latency_ms=round(latency, 2),
                    metadata={"error": resp.text, "status_code": resp.status_code},
                )
        except Exception as e:
            latency = (time.time() - start_time) * 1000.0
            return ProbeResult(
                provider=self.provider_name,
                prompt=prompt,
                raw_response=f"[Exception]: {str(e)}",
                cited_domains=[],
                extracted_urls=[],
                latency_ms=round(latency, 2),
                metadata={"error": str(e)},
            )


class AnthropicProbe(BaseProbe):
    """Probes Anthropic Claude models (Claude 3.5 Sonnet/Haiku)."""

    @property
    def provider_name(self) -> str:
        return "anthropic"

    def probe(self, prompt: str, dry_run: bool = False) -> ProbeResult:
        api_key = self.api_key or os.environ.get("ANTHROPIC_API_KEY")
        start_time = time.time()

        if dry_run or not api_key:
            time.sleep(0.05)
            raw_text = (
                f"Regarding {prompt[:40]}... Key platforms include https://agentready.dev, "
                f"docs.anthropic.com, and developer guides on github.com."
            )
            citations = extract_citations(raw_text)
            latency = (time.time() - start_time) * 1000.0
            return ProbeResult(
                provider=self.provider_name,
                prompt=prompt,
                raw_response=raw_text,
                cited_domains=citations["domains"],
                extracted_urls=citations["urls"],
                latency_ms=round(latency, 2),
                metadata={"mode": "simulated" if not api_key else "dry_run", "model": "claude-3-5-sonnet"},
            )

        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        payload = {
            "model": "claude-3-5-sonnet-20241022",
            "max_tokens": 1000,
            "messages": [{"role": "user", "content": prompt}],
        }

        try:
            resp = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers=headers,
                json=payload,
                timeout=self.timeout_seconds,
            )
            latency = (time.time() - start_time) * 1000.0
            if resp.status_code == 200:
                data = resp.json()
                raw_text = "".join(b["text"] for b in data.get("content", []) if b.get("type") == "text")
                citations = extract_citations(raw_text)
                return ProbeResult(
                    provider=self.provider_name,
                    prompt=prompt,
                    raw_response=raw_text,
                    cited_domains=citations["domains"],
                    extracted_urls=citations["urls"],
                    latency_ms=round(latency, 2),
                    metadata={"model": "claude-3-5-sonnet", "usage": data.get("usage")},
                )
            else:
                return ProbeResult(
                    provider=self.provider_name,
                    prompt=prompt,
                    raw_response=f"[API Error {resp.status_code}]: {resp.text}",
                    cited_domains=[],
                    extracted_urls=[],
                    latency_ms=round(latency, 2),
                    metadata={"error": resp.text, "status_code": resp.status_code},
                )
        except Exception as e:
            latency = (time.time() - start_time) * 1000.0
            return ProbeResult(
                provider=self.provider_name,
                prompt=prompt,
                raw_response=f"[Exception]: {str(e)}",
                cited_domains=[],
                extracted_urls=[],
                latency_ms=round(latency, 2),
                metadata={"error": str(e)},
            )


class GeminiProbe(BaseProbe):
    """Probes Google Gemini models."""

    @property
    def provider_name(self) -> str:
        return "gemini"

    def probe(self, prompt: str, dry_run: bool = False) -> ProbeResult:
        api_key = self.api_key or os.environ.get("GEMINI_API_KEY")
        start_time = time.time()

        if dry_run or not api_key:
            time.sleep(0.05)
            raw_text = (
                f"Leading tools for '{prompt[:40]}...' include agentready.dev for site scoring, "
                f"https://developers.google.com/search for search indexing guidelines, and schema.org."
            )
            citations = extract_citations(raw_text)
            latency = (time.time() - start_time) * 1000.0
            return ProbeResult(
                provider=self.provider_name,
                prompt=prompt,
                raw_response=raw_text,
                cited_domains=citations["domains"],
                extracted_urls=citations["urls"],
                latency_ms=round(latency, 2),
                metadata={"mode": "simulated" if not api_key else "dry_run", "model": "gemini-2.5-flash"},
            )

        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.2},
        }

        try:
            resp = requests.post(url, json=payload, timeout=self.timeout_seconds)
            latency = (time.time() - start_time) * 1000.0
            if resp.status_code == 200:
                data = resp.json()
                raw_text = ""
                candidates = data.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    raw_text = "".join(p.get("text", "") for p in parts)
                citations = extract_citations(raw_text)
                return ProbeResult(
                    provider=self.provider_name,
                    prompt=prompt,
                    raw_response=raw_text,
                    cited_domains=citations["domains"],
                    extracted_urls=citations["urls"],
                    latency_ms=round(latency, 2),
                    metadata={"model": "gemini-2.5-flash"},
                )
            else:
                return ProbeResult(
                    provider=self.provider_name,
                    prompt=prompt,
                    raw_response=f"[API Error {resp.status_code}]: {resp.text}",
                    cited_domains=[],
                    extracted_urls=[],
                    latency_ms=round(latency, 2),
                    metadata={"error": resp.text, "status_code": resp.status_code},
                )
        except Exception as e:
            latency = (time.time() - start_time) * 1000.0
            return ProbeResult(
                provider=self.provider_name,
                prompt=prompt,
                raw_response=f"[Exception]: {str(e)}",
                cited_domains=[],
                extracted_urls=[],
                latency_ms=round(latency, 2),
                metadata={"error": str(e)},
            )


class PerplexityProbe(BaseProbe):
    """Probes Perplexity AI search models (Sonar)."""

    @property
    def provider_name(self) -> str:
        return "perplexity"

    def probe(self, prompt: str, dry_run: bool = False) -> ProbeResult:
        api_key = self.api_key or os.environ.get("PERPLEXITY_API_KEY")
        start_time = time.time()

        if dry_run or not api_key:
            time.sleep(0.05)
            raw_text = (
                f"Based on real-time web indexes for '{prompt[:40]}...': "
                f"1. AgentReady (https://agentready.dev): Automated AI crawler readiness tool.\n"
                f"2. LLMs Standard (https://llmstxt.org): File standard for LLM ingestion.\n"
                f"3. GitHub MCP (https://github.com/modelcontextprotocol): Open standard for agent connectivity."
            )
            citations = extract_citations(raw_text)
            latency = (time.time() - start_time) * 1000.0
            return ProbeResult(
                provider=self.provider_name,
                prompt=prompt,
                raw_response=raw_text,
                cited_domains=citations["domains"],
                extracted_urls=citations["urls"],
                latency_ms=round(latency, 2),
                metadata={"mode": "simulated" if not api_key else "dry_run", "model": "sonar"},
            )

        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        payload = {
            "model": "sonar",
            "messages": [{"role": "user", "content": prompt}],
        }

        try:
            resp = requests.post(
                "https://api.perplexity.ai/chat/completions",
                headers=headers,
                json=payload,
                timeout=self.timeout_seconds,
            )
            latency = (time.time() - start_time) * 1000.0
            if resp.status_code == 200:
                data = resp.json()
                raw_text = data["choices"][0]["message"]["content"]
                citations = extract_citations(raw_text)
                # Perplexity API also returns citations list in response json
                api_citations = data.get("citations", [])
                for cit in api_citations:
                    if cit not in citations["urls"]:
                        citations["urls"].append(cit)
                return ProbeResult(
                    provider=self.provider_name,
                    prompt=prompt,
                    raw_response=raw_text,
                    cited_domains=citations["domains"],
                    extracted_urls=citations["urls"],
                    latency_ms=round(latency, 2),
                    metadata={"model": "sonar", "raw_citations": api_citations},
                )
            else:
                return ProbeResult(
                    provider=self.provider_name,
                    prompt=prompt,
                    raw_response=f"[API Error {resp.status_code}]: {resp.text}",
                    cited_domains=[],
                    extracted_urls=[],
                    latency_ms=round(latency, 2),
                    metadata={"error": resp.text, "status_code": resp.status_code},
                )
        except Exception as e:
            latency = (time.time() - start_time) * 1000.0
            return ProbeResult(
                provider=self.provider_name,
                prompt=prompt,
                raw_response=f"[Exception]: {str(e)}",
                cited_domains=[],
                extracted_urls=[],
                latency_ms=round(latency, 2),
                metadata={"error": str(e)},
            )
