"""Unit tests for OpenAPI 3.1 schema specification."""

import json
import os


def test_openapi_schema_valid():
    openapi_path = os.path.join(os.path.dirname(__file__), "..", "apps", "web", "openapi.json")
    assert os.path.exists(openapi_path)

    with open(openapi_path, "r", encoding="utf-8") as f:
        schema = json.load(f)

    assert schema["openapi"] == "3.1.0"
    assert "paths" in schema
    assert "/api/scan" in schema["paths"]
    assert "/api/probe" in schema["paths"]
    assert "/api/badge" in schema["paths"]
    assert "components" in schema
    assert "Score" in schema["components"]["schemas"]
