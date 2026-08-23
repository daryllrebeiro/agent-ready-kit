/**
 * Official TypeScript / Node.js Client SDK for AgentReady
 */

export interface ScoreComponent {
  name: string;
  display_name: string;
  score: number;
  weight: number;
  status: "PASS" | "WARN" | "FAIL";
  evidence: Record<string, any>;
  details: string;
  recommendations: string[];
}

export interface Score {
  url: string;
  version: string;
  timestamp: string;
  overall_score: number;
  grade: "A+" | "A" | "B" | "C" | "D" | "F";
  components: ScoreComponent[];
  summary: string;
  recommendations: string[];
}

export interface ClientOptions {
  apiKey?: string;
  baseUrl?: string;
}

export class AgentReadyClient {
  private apiKey?: string;
  private baseUrl: string;

  constructor(options: ClientOptions = {}) {
    this.apiKey = options.apiKey || (typeof process !== "undefined" ? process.env.AGENTREADY_API_KEY : undefined);
    this.baseUrl = (options.baseUrl || "http://localhost:3000").replace(/\/$/, "");
  }

  private async request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      ...(options.headers as Record<string, string>),
    };

    if (this.apiKey) {
      headers["Authorization"] = `Bearer ${this.apiKey}`;
    }

    const response = await fetch(`${this.baseUrl}${endpoint}`, {
      ...options,
      headers,
    });

    if (!response.ok) {
      const errText = await response.text();
      throw new Error(`AgentReady API error (${response.status}): ${errText}`);
    }

    return response.json() as Promise<T>;
  }

  /**
   * Scan a website URL for AI agent readiness and structured data compliance.
   */
  public async scan(url: string): Promise<Score> {
    return this.request<Score>("/api/scan", {
      method: "POST",
      body: JSON.stringify({ url }),
    });
  }

  /**
   * Run live or simulated citation probes across LLM providers.
   */
  public async probe(url: string, dryRun: boolean = true): Promise<any> {
    return this.request<any>("/api/probe", {
      method: "POST",
      body: JSON.stringify({ url, dry_run: dryRun }),
    });
  }

  /**
   * Retrieve the URL for an embeddable SVG verification badge.
   */
  public getBadgeUrl(domain: string, label: string = "agent-ready"): string {
    return `${this.baseUrl}/api/badge?domain=${encodeURIComponent(domain)}&label=${encodeURIComponent(label)}`;
  }
}
