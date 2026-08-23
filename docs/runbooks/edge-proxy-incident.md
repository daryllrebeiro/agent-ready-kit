# Incident Runbook: Edge Proxy & Provider Outages

## Runbook 1: Edge Proxy Anomaly or Fail-Open Incident

### Severity: SEV-1 (Critical)
**Trigger**: Alert on elevated proxy fail-open rate (> 1%) or origin error rate increase.

### Immediate Actions (< 5 minutes)
1. **Engage Kill Switch Immediately**:
   - Set environment variable `KILL_SWITCH=true` in Cloudflare Worker dashboard or send header `X-AgentReady-Bypass: true`.
   - All traffic will instantly bypass edge interception and pass directly to customer origin untouched.
2. **Verify Origin Health**:
   - Run synthetic health checks directly against customer origin URL.
   - Confirm origin HTTP status is 200.
3. **Inspect Cloudflare Worker Logs**:
   - Search for unhandled exceptions or timeout spikes in Worker Tail logs.
4. **Post-Mortem**:
   - File incident report with root cause analysis (RCA) and add regression test.

---

## Runbook 2: LLM Provider Outage or Rate Limit Spike

### Severity: SEV-2 (Major)
**Trigger**: Dead-Letter Queue (DLQ) growth alert (> 20 failed jobs in 5 min) or provider circuit breaker tripped to `OPEN`.

### Immediate Actions (< 15 minutes)
1. **Confirm Circuit Breaker Status**:
   - Check which provider is in `OPEN` state (e.g. OpenAI returning 500/429).
   - Ensure the other 3 providers (Anthropic, Gemini, Perplexity) continue operating without throughput degradation.
2. **Drain / Re-process DLQ**:
   - Inspect DLQ failed jobs in the admin dashboard.
   - Once the provider recovers (circuit breaker enters `HALF_OPEN` and resets to `CLOSED`), trigger batch replay from DLQ.
