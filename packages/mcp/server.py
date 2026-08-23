"""Hosted Model Context Protocol (MCP) Server for AgentReady."""

import json
import sys
from typing import Any, Dict, List, Optional

from packages.core.probes.extractor import extract_domain_from_url
from packages.core.scorer import Scorer
from packages.mcp.security import detect_prompt_injection, sanitize_mcp_content

MCP_PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "agentready-mcp-gateway"
SERVER_VERSION = "0.1.0"


class MCPServer:
    """JSON-RPC 2.0 compliant Model Context Protocol server exposing AgentReady capabilities."""

    def __init__(self):
        self.scorer = Scorer()
        self.tools = [
            {
                "name": "get_site_readiness",
                "description": "Evaluate any website or URL for AI agent readiness, LLM crawlability, and semantic structured data.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "url": {
                            "type": "string",
                            "description": "Target website URL (e.g. https://example.com)",
                        }
                    },
                    "required": ["url"],
                },
            },
            {
                "name": "get_llms_txt",
                "description": "Fetch and validate /llms.txt content from target website.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "url": {
                            "type": "string",
                            "description": "Root URL of the website",
                        }
                    },
                    "required": ["url"],
                },
            },
            {
                "name": "check_bot_permission",
                "description": "Check if a specific AI crawler (GPTBot, ClaudeBot, PerplexityBot) is permitted in robots.txt.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "description": "Target website URL"},
                        "bot_name": {
                            "type": "string",
                            "description": "Bot name (e.g. GPTBot, ClaudeBot, PerplexityBot)",
                        },
                    },
                    "required": ["url", "bot_name"],
                },
            },
        ]

    def handle_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Process an MCP JSON-RPC 2.0 request."""
        req_id = request.get("id")
        method = request.get("method")
        params = request.get("params", {})

        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": MCP_PROTOCOL_VERSION,
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
                },
            }

        elif method == "tools/list":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"tools": self.tools},
            }

        elif method == "tools/call":
            tool_name = params.get("name")
            arguments = params.get("arguments", {})
            return self._execute_tool(req_id, tool_name, arguments)

        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32601, "message": f"Method '{method}' not found"},
        }

    def _execute_tool(self, req_id: Any, name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        url = args.get("url", "")

        # Security check on inputs
        has_injection, matches = detect_prompt_injection(url)
        if has_injection:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "isError": True,
                    "content": [{"type": "text", "text": f"[Security Violation]: Suspicious prompt injection pattern detected: {matches}"}],
                },
            }

        if name == "get_site_readiness":
            try:
                score = self.scorer.score_url(url)
                sanitized_summary = sanitize_mcp_content(score.summary)
                result_payload = {
                    "url": score.url,
                    "overall_score": score.overall_score,
                    "grade": score.grade,
                    "summary": sanitized_summary,
                    "components": [
                        {
                            "name": c.name,
                            "display_name": c.display_name,
                            "score": c.score,
                            "status": c.status.value,
                            "details": sanitize_mcp_content(c.details),
                        }
                        for c in score.components
                    ],
                    "recommendations": [sanitize_mcp_content(r) for r in score.recommendations],
                }
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [{"type": "text", "text": json.dumps(result_payload, indent=2)}],
                    },
                }
            except Exception as e:
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {"isError": True, "content": [{"type": "text", "text": f"Error scoring URL: {str(e)}"}]},
                }

        elif name == "get_llms_txt":
            base = url.rstrip("/")
            llms_url = f"{base}/llms.txt"
            res = self.scorer.fetch_resource(llms_url)
            if res["success"]:
                content = sanitize_mcp_content(res["content"])
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {"content": [{"type": "text", "text": content}]},
                }
            else:
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {"content": [{"type": "text", "text": "No /llms.txt found on target site."}]},
                }

        elif name == "check_bot_permission":
            bot_name = args.get("bot_name", "GPTBot")
            base = url.rstrip("/")
            robots_url = f"{base}/robots.txt"
            res = self.scorer.fetch_resource(robots_url)
            from packages.core.checks.bot_permissions import evaluate_bot_permission, parse_robots_txt

            if res["success"]:
                parsed = parse_robots_txt(res["content"])
                perm = evaluate_bot_permission(bot_name, parsed)
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {"content": [{"type": "text", "text": json.dumps(perm, indent=2)}]},
                }
            else:
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {"content": [{"type": "text", "text": f"No robots.txt found. {bot_name} is ALLOWED by default."}]},
                }

        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32602, "message": f"Unknown tool name '{name}'"},
        }


def run_stdio_server():
    """Runs MCP stdio server listening to line-delimited JSON-RPC messages."""
    server = MCPServer()
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
            resp = server.handle_request(req)
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()
        except Exception as e:
            err_resp = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": f"Parse error: {str(e)}"}}
            sys.stdout.write(json.dumps(err_resp) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    run_stdio_server()
