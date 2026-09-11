/**
 * AgentReady Edge Proxy — Cloudflare Worker
 *
 * Implements Bot-detection Reverse Proxy with strict Fail-Open guarantees.
 * Architecture Tenet: Customer production traffic must NEVER fail due to edge proxy issues.
 */

// Major AI crawlers & user agents
const AI_BOT_REGEX = /(GPTBot|ClaudeBot|PerplexityBot|Claude-Web|ChatGPT-User|Google-Extended|Applebot-Extended|Amazonbot|cohere-ai|CCBot)/i;

export default {
  async fetch(request, env, ctx) {
    // 1. FAIL-OPEN SAFETY ENVELOPE
    // Any uncaught error, timeout, or exception passes through to origin unmodified.
    try {
      return await handleRequest(request, env, ctx);
    } catch (err) {
      console.error("[AgentReady Proxy FAIL-OPEN Triggered]:", err);
      // Fallback: Passthrough to origin unmodified
      return fetch(request);
    }
  },
};

async function handleRequest(request, env, ctx) {
  const url = new URL(request.url);
  const userAgent = request.headers.get("User-Agent") || "";
  const acceptHeader = request.headers.get("Accept") || "";

  // 2. PER-TENANT KILL SWITCH
  const isBypassed = request.headers.get("X-AgentReady-Bypass") === "true" || (env && env.KILL_SWITCH === "true");
  if (isBypassed) {
    return fetch(request);
  }

  // 3. BOT DETECTION & CONTENT NEGOTIATION
  const isAIBot = AI_BOT_REGEX.test(userAgent);
  const requestsMarkdown = acceptHeader.includes("text/markdown") || acceptHeader.includes("text/x-markdown");

  // 4. SHADOW MODE CHECK (Default to true for safety)
  const isShadowMode = !env || env.SHADOW_MODE !== "false";

  if (isShadowMode) {
    // Log shadow analytics without intercepting traffic
    console.log(`[AgentReady Shadow Mode] UA: "${userAgent}" | IsAIBot: ${isAIBot} | MarkdownRequested: ${requestsMarkdown}`);
    return fetch(request);
  }

  // 5. LIVE INTERCEPTION (Only for verified AI bots or explicit Markdown requests)
  if (isAIBot || requestsMarkdown) {
    // Check if path is root or docs
    if (url.pathname === "/llms.txt") {
      const originResp = await fetch(request);
      if (originResp.status === 200) {
        return originResp;
      }
      // If origin does not have llms.txt, serve edge fallback if configured
      if (env && env.FALLBACK_LLMS_TXT) {
        return new Response(env.FALLBACK_LLMS_TXT, {
          headers: {
            "Content-Type": "text/markdown; charset=utf-8",
            "Cache-Control": "public, max-age=3600",
            "X-Served-By": "AgentReady-Edge-Proxy",
          },
        });
      }
    }
  }

  // Pass through to origin
  return fetch(request);
}
