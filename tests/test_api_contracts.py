"""Unit tests for API Contracts and SDK Signature Consistency."""

import json
from pathlib import Path
from packages.sdk_python.agentready.client import AgentReadyClient


def test_openapi_contract_endpoint_coverage():
    openapi_path = Path("apps/web/openapi.json")
    assert openapi_path.exists()

    with open(openapi_path, "r", encoding="utf-8") as f:
        spec = json.load(f)

    assert "openapi" in spec
    assert "AgentReady" in spec["info"]["title"]
    paths = spec["paths"]

    # Verify critical core endpoints exist in contract specification
    expected_endpoints = [
        "/api/scan",
        "/api/probe",
        "/api/scores",
        "/api/domains",
        "/api/generate",
        "/api/badge",
        "/api/simulate",
        "/api/compare",
        "/api/report",
    ]

    for ep in expected_endpoints:
        assert ep in paths, f"Endpoint {ep} missing from OpenAPI 3.1 specification"


def test_python_sdk_contract_method_signatures():
    client = AgentReadyClient(api_key="test_key", base_url="http://localhost:8000")
    
    # Check that public methods match client contract
    assert hasattr(client, "scan")
    assert hasattr(client, "probe")
    assert hasattr(client, "compare")
    assert hasattr(client, "fix")
    assert hasattr(client, "get_badge_svg")
