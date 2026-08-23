"""Model Context Protocol (MCP) hosted gateway for AgentReady."""

from packages.mcp.security import detect_prompt_injection, sanitize_mcp_content
from packages.mcp.server import MCPServer

__all__ = ["MCPServer", "detect_prompt_injection", "sanitize_mcp_content"]
