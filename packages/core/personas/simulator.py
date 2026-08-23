"""Autonomous AI agent persona simulations evaluating archetype-specific website readiness."""

from typing import Any, Dict, List, Optional
from bs4 import BeautifulSoup
from packages.core.checks.structured_data import extract_json_ld
from packages.core.schemas import Score
from packages.core.scorer import Scorer


class AgentPersonaSimulator:
    """Simulates specialized AI agent archetypes interacting with website content."""

    def __init__(self):
        self.scorer = Scorer()

    def simulate_all_personas(self, url: str, html: Optional[str] = None) -> Dict[str, Any]:
        """Evaluate site against all 4 specialized AI agent personas."""
        if not html:
            fetch_res = self.scorer.fetch_resource(url)
            html = fetch_res["content"] if fetch_res["success"] else ""

        soup = BeautifulSoup(html, "html.parser")
        json_ld = extract_json_ld(soup)

        research = self._simulate_research_agent(soup, json_ld)
        commerce = self._simulate_commerce_agent(soup, json_ld)
        coding = self._simulate_coding_agent(soup, json_ld)
        local = self._simulate_local_discovery_agent(soup, json_ld)

        personas = [research, commerce, coding, local]
        overall_compatibility = round(sum(p["compatibility_score"] for p in personas) / len(personas), 1)

        return {
            "url": url,
            "overall_compatibility": overall_compatibility,
            "personas": {
                "research_agent": research,
                "commerce_agent": commerce,
                "coding_agent": coding,
                "local_discovery_agent": local,
            },
        }

    def _simulate_research_agent(self, soup: BeautifulSoup, json_ld: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Research / Synthesis Agent: Factual depth, entity authority, tables, citations."""
        score = 0.0
        details = []

        # 1. Structured entities
        types = [str(b.get("@type", "")) for b in json_ld]
        if any(t in ["Article", "ScholarlyArticle", "TechArticle", "Report", "Organization"] for t in types):
            score += 35.0
            details.append("[OK] Authoritative article/organization schema detected")

        # 2. Semantic text & tables
        if soup.find("table"):
            score += 25.0
            details.append("[OK] Tabular data structures present for direct extraction")
        if soup.find("h2") and soup.find("main"):
            score += 25.0
            details.append("[OK] Clear hierarchical sectioning for topic synthesis")

        # 3. Citation links & references
        links = soup.find_all("a", href=True)
        external_links = [l for l in links if l["href"].startswith("http")]
        if len(external_links) >= 3:
            score += 15.0
            details.append("[OK] External references and citations available")

        return {
            "name": "Research & Synthesis Agent",
            "archetype": "deep_research",
            "compatibility_score": min(100.0, score),
            "status": "EXCELLENT" if score >= 75 else "MODERATE" if score >= 40 else "POOR",
            "key_strengths": details,
        }

    def _simulate_commerce_agent(self, soup: BeautifulSoup, json_ld: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Commerce / Shopping Agent: Product, price, currency, availability, reviews."""
        score = 0.0
        details = []

        types = [str(b.get("@type", "")) for b in json_ld]
        has_product = any("Product" in t for t in types)

        if has_product:
            score += 40.0
            details.append("[OK] Schema.org Product entity present")
            for b in json_ld:
                if "offers" in b or "price" in b:
                    score += 30.0
                    details.append("[OK] Structured pricing and offer terms found")
                if "aggregateRating" in b or "review" in b:
                    score += 30.0
                    details.append("[OK] Verified customer ratings and reviews present")
        else:
            # Fallback text check
            if any(term in soup.get_text().lower() for term in ["price", "buy", "cart", "pricing", "$"]):
                score += 25.0
                details.append("[WARN] Price mentions found in unstructured text only")

        return {
            "name": "Commerce & Purchasing Agent",
            "archetype": "commerce",
            "compatibility_score": min(100.0, score),
            "status": "EXCELLENT" if score >= 75 else "MODERATE" if score >= 40 else "POOR",
            "key_strengths": details,
        }

    def _simulate_coding_agent(self, soup: BeautifulSoup, json_ld: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Coding & Technical Assistant: Code blocks, API schema, /llms.txt context."""
        score = 0.0
        details = []

        code_tags = soup.find_all(["code", "pre"])
        if len(code_tags) >= 2:
            score += 40.0
            details.append(f"[OK] {len(code_tags)} formatted code blocks available for synthesis")

        types = [str(b.get("@type", "")) for b in json_ld]
        if any(t in ["SoftwareApplication", "APIReference", "SoftwareSourceCode"] for t in types):
            score += 35.0
            details.append("[OK] SoftwareApplication / APIReference schema present")

        # Headings / docs structure
        if soup.find("nav") or soup.find("aside"):
            score += 25.0
            details.append("[OK] Structured documentation navigation detected")

        return {
            "name": "Coding & Technical Agent",
            "archetype": "technical_coding",
            "compatibility_score": min(100.0, score),
            "status": "EXCELLENT" if score >= 75 else "MODERATE" if score >= 40 else "POOR",
            "key_strengths": details,
        }

    def _simulate_local_discovery_agent(self, soup: BeautifulSoup, json_ld: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Local Discovery / Trip Agent: LocalBusiness, coordinates, address, opening hours."""
        score = 0.0
        details = []

        types = [str(b.get("@type", "")) for b in json_ld]
        if any(t in ["LocalBusiness", "Restaurant", "Store", "Place", "PostalAddress"] for t in types):
            score += 50.0
            details.append("[OK] Schema.org LocalBusiness entity declared")
            for b in json_ld:
                if "geo" in b or "address" in b:
                    score += 25.0
                    details.append("[OK] Precise geo-coordinates and postal address defined")
                if "openingHours" in b or "openingHoursSpecification" in b:
                    score += 25.0
                    details.append("[OK] Structured operating hours available")

        return {
            "name": "Local Discovery & Trip Agent",
            "archetype": "local_discovery",
            "compatibility_score": min(100.0, score),
            "status": "EXCELLENT" if score >= 75 else "MODERATE" if score >= 40 else "POOR",
            "key_strengths": details,
        }
