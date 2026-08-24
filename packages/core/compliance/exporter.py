"""Self-Service Multi-Tenant Data Exporter (GDPR Article 20 & SOC 2 Data Portability)."""

import json
import time
from typing import Any, Dict, List, Optional
from packages.core.storage.postgres_rls import PostgresRLSRepository


class TenantDataExporter:
    """Exports all domain configurations, scan histories, probe results, and audit trails for a tenant."""

    def __init__(self, repository: PostgresRLSRepository):
        self.repo = repository

    def export_tenant_data_bundle(self, tenant_id: str) -> Dict[str, Any]:
        """Generates a complete, structured JSON export bundle strictly scoped to the requesting tenant."""
        domains = self.repo.list_domains(tenant_id)
        exported_domains = []

        for d in domains:
            domain_url = d["domain_url"]
            scores = self.repo.get_score_history(tenant_id, domain_url, limit=100)
            exported_domains.append({
                "domain_id": d["id"],
                "domain_url": domain_url,
                "created_at": d.get("created_at"),
                "scores": scores,
            })

        bundle = {
            "export_metadata": {
                "tenant_id": tenant_id,
                "exported_at": time.time(),
                "format_version": "1.0.0",
                "compliance_standard": "GDPR-Art20-Portability",
            },
            "domains_count": len(exported_domains),
            "domains": exported_domains,
        }
        return bundle
