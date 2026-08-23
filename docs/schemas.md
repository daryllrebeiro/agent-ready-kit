# Data Contracts & Schemas Documentation

The scoring engine, probing pipeline, and API layers communicate strictly via versioned Pydantic models defined in `packages/core/schemas.py`.

## Core Schemas

### 1. `ScoreComponent`
Represents an individual signal inspection result.

| Field | Type | Description |
|---|---|---|
| `name` | `str` | Machine-readable identifier (e.g. `llms_txt`, `structured_data`) |
| `display_name` | `str` | Human-readable title |
| `score` | `float` | Normalized component score from `0.0` to `100.0` |
| `weight` | `float` | Component weighting in overall composite score (`0.0` to `1.0`) |
| `status` | `ComponentStatus` | `PASS` (score >= 80), `WARN` (score >= 50), or `FAIL` (score < 50) |
| `evidence` | `Dict[str, Any]` | Detailed machine-readable findings |
| `details` | `str` | Human-readable diagnosis summary |
| `recommendations` | `List[str]` | Actionable remediation guidance |

### 2. `Score`
The top-level agent-readiness evaluation report.

| Field | Type | Description |
|---|---|---|
| `url` | `str` | Target URL analyzed |
| `version` | `str` | Algorithm version (e.g. `score_v0.1`) |
| `timestamp` | `datetime` | Analysis timestamp in UTC |
| `overall_score` | `float` | Weighted overall score (`0.0` to `100.0`) |
| `grade` | `str` | Letter grade (`A+`, `A`, `B`, `C`, `D`, `F`) |
| `components` | `List[ScoreComponent]` | List of individual check evaluations |
| `summary` | `str` | Executive summary of agent readiness |
| `recommendations` | `List[str]` | Prioritized remediation checklist |
| `metadata` | `Dict[str, Any]` | HTTP response codes and execution diagnostics |

### 3. `ProbeResult`
Stores results from LLM citation queries.

| Field | Type | Description |
|---|---|---|
| `provider` | `str` | LLM provider (`openai`, `anthropic`, `gemini`, `perplexity`) |
| `prompt` | `str` | Probe query prompt |
| `raw_response` | `str` | Verbatim text response from the model |
| `cited_domains` | `List[str]` | Domains cited by the model |
| `extracted_urls` | `List[str]` | Explicit URLs cited |
| `latency_ms` | `float?` | Provider latency in milliseconds |
| `timestamp` | `datetime` | Probe timestamp in UTC |
| `metadata` | `Dict[str, Any]` | Model name, token count, and parameters |
