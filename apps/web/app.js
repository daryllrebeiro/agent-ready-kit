/**
 * AgentReady Web Dashboard Client Application
 */

let currentScore = null;
let currentProbes = [];

document.addEventListener("DOMContentLoaded", () => {
  initEventListeners();
  loadTrackedDomains();
});

function initEventListeners() {
  const scanBtn = document.getElementById("scanBtn");
  const probeBtn = document.getElementById("probeBtn");
  const urlInput = document.getElementById("urlInput");
  const domainSelect = document.getElementById("domainSelect");
  const exportJsonBtn = document.getElementById("exportJsonBtn");
  const copyFixesBtn = document.getElementById("copyFixesBtn");

  scanBtn.addEventListener("click", () => {
    const url = urlInput.value.trim();
    if (url) runScan(url);
  });

  urlInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      const url = urlInput.value.trim();
      if (url) runScan(url);
    }
  });

  probeBtn.addEventListener("click", () => {
    const url = urlInput.value.trim();
    if (url) runProbe(url);
  });

  domainSelect.addEventListener("change", (e) => {
    const selectedUrl = e.target.value;
    if (selectedUrl) {
      urlInput.value = selectedUrl;
      loadDomainData(selectedUrl);
    }
  });

  exportJsonBtn.addEventListener("click", exportCurrentJson);
  copyFixesBtn.addEventListener("click", copyRemediations);
}

async function loadTrackedDomains() {
  try {
    const resp = await fetch("/api/domains");
    if (!resp.ok) return;
    const domains = await resp.json();
    const select = document.getElementById("domainSelect");
    select.innerHTML = '<option value="">Tracked Sites...</option>';

    domains.forEach((d) => {
      const opt = document.createElement("option");
      opt.value = d.domain_url;
      const scoreTag = d.overall_score !== null ? `(${d.overall_score.toFixed(1)})` : "";
      opt.textContent = `${d.domain_url} ${scoreTag}`;
      select.appendChild(opt);
    });

    if (domains.length > 0) {
      const first = domains[0].domain_url;
      document.getElementById("urlInput").value = first;
      loadDomainData(first);
    }
  } catch (err) {
    console.warn("Could not load tracked domains:", err);
  }
}

async function loadDomainData(url) {
  try {
    const resp = await fetch(`/api/scores?domain=${encodeURIComponent(url)}`);
    if (resp.ok) {
      const score = await resp.json();
      if (score && score.overall_score !== undefined) {
        renderScoreDashboard(score);
      }
    }
    loadDomainProbes(url);
  } catch (err) {
    console.warn("Error loading domain score:", err);
  }
}

async function loadDomainProbes(url) {
  try {
    const resp = await fetch(`/api/probes?domain=${encodeURIComponent(url)}`);
    if (resp.ok) {
      const probes = await resp.json();
      renderProbes(probes);
    }
  } catch (err) {
    console.warn("Error loading probes:", err);
  }
}

async function runScan(url) {
  const scanBtn = document.getElementById("scanBtn");
  const btnText = scanBtn.querySelector(".btn-text");
  const btnLoader = scanBtn.querySelector(".btn-loader");

  scanBtn.disabled = true;
  btnText.textContent = "Scanning...";

  try {
    const resp = await fetch("/api/scan", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
    });

    if (!resp.ok) {
      const errData = await resp.json().catch(() => ({}));
      alert(`Scan failed: ${errData.error || resp.statusText}`);
      return;
    }

    const score = await resp.json();
    renderScoreDashboard(score);
    loadTrackedDomains();
  } catch (err) {
    alert(`Scan network error: ${err.message}`);
  } finally {
    scanBtn.disabled = false;
    btnText.textContent = "Run Scan";
  }
}

async function runProbe(url) {
  const probeBtn = document.getElementById("probeBtn");
  probeBtn.disabled = true;
  probeBtn.textContent = "Probing Models...";

  try {
    const resp = await fetch("/api/probe", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url, dry_run: true }),
    });

    if (resp.ok) {
      const result = await resp.json();
      loadDomainProbes(url);
    }
  } catch (err) {
    console.error("Probe error:", err);
  } finally {
    probeBtn.disabled = false;
    probeBtn.textContent = "Probe LLMs";
  }
}

function renderScoreDashboard(score) {
  currentScore = score;

  // Overall Score & Gauge
  const overallScoreEl = document.getElementById("overallScore");
  const gradeBadgeEl = document.getElementById("gradeBadge");
  const targetUrlEl = document.getElementById("targetUrlDisplay");
  const summaryEl = document.getElementById("scoreSummary");
  const versionEl = document.getElementById("scoreVersion");
  const gaugeFill = document.getElementById("gaugeFill");

  overallScoreEl.textContent = score.overall_score.toFixed(1);
  gradeBadgeEl.textContent = score.grade;
  targetUrlEl.textContent = score.url;
  summaryEl.textContent = score.summary;
  versionEl.textContent = score.version || "score_v0.1";

  // SVG circular gauge calculation (circumference is 2 * PI * 50 ~= 314.15)
  const maxDash = 314.15;
  const offset = maxDash - (score.overall_score / 100.0) * maxDash;
  gaugeFill.style.strokeDashoffset = offset;

  // Color adjustments based on score
  if (score.overall_score >= 80) {
    gaugeFill.style.stroke = "var(--accent-green)";
    gradeBadgeEl.style.borderColor = "var(--accent-green)";
    gradeBadgeEl.style.color = "var(--accent-green)";
  } else if (score.overall_score >= 50) {
    gaugeFill.style.stroke = "var(--accent-yellow)";
    gradeBadgeEl.style.borderColor = "var(--accent-yellow)";
    gradeBadgeEl.style.color = "var(--accent-yellow)";
  } else {
    gaugeFill.style.stroke = "var(--accent-red)";
    gradeBadgeEl.style.borderColor = "var(--accent-red)";
    gradeBadgeEl.style.color = "var(--accent-red)";
  }

  // Render 4 Signals
  renderSignals(score.components || []);

  // Render Bot Permissions Matrix
  renderBotMatrix(score.components || []);

  // Render Remediation Checklist
  renderRemediations(score.recommendations || []);
}

function renderSignals(components) {
  const grid = document.getElementById("signalsGrid");
  grid.innerHTML = "";

  components.forEach((comp) => {
    const card = document.createElement("div");
    card.className = "signal-card";

    let badgeClass = "badge-fail";
    if (comp.status === "PASS") badgeClass = "badge-pass";
    else if (comp.status === "WARN") badgeClass = "badge-warn";

    card.innerHTML = `
      <div class="signal-header">
        <span class="signal-title">${escapeHtml(comp.display_name)}</span>
        <span class="badge ${badgeClass}">${comp.status}</span>
      </div>
      <div class="mini-bar-bg">
        <div class="mini-bar-fill" style="width: ${comp.score}%; background: ${
      comp.score >= 80 ? "var(--accent-green)" : comp.score >= 50 ? "var(--accent-yellow)" : "var(--accent-red)"
    }"></div>
      </div>
      <div style="display: flex; justify-content: space-between; font-size: 0.8rem; color: var(--text-muted);">
        <span>Score: <strong>${comp.score.toFixed(1)}/100</strong></span>
        <span>Weight: <strong>${Math.round(comp.weight * 100)}%</strong></span>
      </div>
      <p class="signal-details">${escapeHtml(comp.details)}</p>
    `;
    grid.appendChild(card);
  });
}

function renderBotMatrix(components) {
  const botComp = components.find((c) => c.name === "bot_permissions");
  const tbody = document.getElementById("botTableBody");
  const countBadge = document.getElementById("botCountBadge");

  if (!botComp || !botComp.evidence || !botComp.evidence.bot_status) {
    tbody.innerHTML = '<tr><td colspan="3" class="text-center">No bot rules found.</td></tr>';
    countBadge.textContent = "0 Bots";
    return;
  }

  const bots = botComp.evidence.bot_status;
  const botNames = Object.keys(bots);
  countBadge.textContent = `${botComp.evidence.allowed_count || 0}/${botNames.length} Allowed`;

  tbody.innerHTML = "";
  botNames.forEach((name) => {
    const info = bots[name];
    const tr = document.createElement("tr");

    let statusBadge = `<span class="badge badge-blocked">BLOCKED</span>`;
    if (info.status === "ALLOWED") {
      statusBadge = `<span class="badge badge-allowed">ALLOWED</span>`;
    } else if (info.status === "PARTIAL") {
      statusBadge = `<span class="badge badge-partial">PARTIAL</span>`;
    }

    tr.innerHTML = `
      <td><strong>${escapeHtml(name)}</strong></td>
      <td style="color: var(--text-secondary); font-size: 0.8rem;">${escapeHtml(info.matched_by || "Direct Rule")}</td>
      <td>${statusBadge}</td>
    `;
    tbody.appendChild(tr);
  });
}

function renderRemediations(recommendations) {
  const container = document.getElementById("remediationList");
  if (!recommendations || recommendations.length === 0) {
    container.innerHTML = '<p class="empty-state">No immediate recommendations — site is well optimized!</p>';
    return;
  }

  container.innerHTML = "";
  recommendations.forEach((rec, idx) => {
    const item = document.createElement("div");
    item.className = "remediation-item";
    item.innerHTML = `
      <span class="rec-number">${idx + 1}.</span>
      <span style="flex: 1;">${escapeHtml(rec)}</span>
    `;
    container.appendChild(item);
  });
}

function renderProbes(probes) {
  currentProbes = probes;
  const list = document.getElementById("probeList");
  const countBadge = document.getElementById("probeCountBadge");
  countBadge.textContent = `${probes.length} probe(s)`;

  if (!probes || probes.length === 0) {
    list.innerHTML = '<p class="empty-state">No probe runs recorded yet. Click "Probe LLMs" to test live model citations.</p>';
    return;
  }

  // Update citation share meters
  updateCitationBars(probes);

  list.innerHTML = "";
  probes.slice(0, 10).forEach((probe) => {
    const card = document.createElement("div");
    card.className = "probe-card";

    const citedCount = probe.cited_domains ? probe.cited_domains.length : 0;
    const latency = probe.latency_ms ? `${Math.round(probe.latency_ms)}ms` : "";

    card.innerHTML = `
      <div class="probe-meta">
        <span>Provider: <strong>${escapeHtml(probe.provider.toUpperCase())}</strong></span>
        <span>Citations: <strong style="color: var(--accent-cyan);">${citedCount} domains</strong> &bull; ${latency}</span>
      </div>
      <div class="probe-prompt">"${escapeHtml(probe.prompt)}"</div>
      <div class="probe-response">${escapeHtml(probe.raw_response.slice(0, 300))}${probe.raw_response.length > 300 ? "..." : ""}</div>
    `;
    list.appendChild(card);
  });
}

function updateCitationBars(probes) {
  const providerStats = {
    openai: { total: 0, cited: 0 },
    anthropic: { total: 0, cited: 0 },
    gemini: { total: 0, cited: 0 },
    perplexity: { total: 0, cited: 0 },
  };

  probes.forEach((p) => {
    const prov = p.provider.toLowerCase();
    if (providerStats[prov]) {
      providerStats[prov].total += 1;
      if (p.cited_domains && p.cited_domains.length > 0) {
        providerStats[prov].cited += 1;
      }
    }
  });

  setProviderBar("OpenAI", providerStats.openai);
  setProviderBar("Claude", providerStats.anthropic);
  setProviderBar("Gemini", providerStats.gemini);
  setProviderBar("Perplexity", providerStats.perplexity);
}

function setProviderBar(idSuffix, stat) {
  const bar = document.getElementById(`bar${idSuffix}`);
  const status = document.getElementById(`status${idSuffix}`);
  if (!bar || !status) return;

  if (stat.total === 0) {
    bar.style.width = "0%";
    status.textContent = "Untested";
    status.style.color = "var(--text-muted)";
  } else {
    const pct = Math.round((stat.cited / stat.total) * 100);
    bar.style.width = `${pct}%`;
    status.textContent = `${pct}% Cited (${stat.cited}/${stat.total})`;
    status.style.color = pct > 50 ? "var(--accent-green)" : "var(--accent-cyan)";
  }
}

function exportCurrentJson() {
  if (!currentScore) {
    alert("No score data to export.");
    return;
  }
  const blob = new Blob([JSON.stringify(currentScore, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `agentready-report-${new Date().toISOString().slice(0, 10)}.json`;
  a.click();
}

function copyRemediations() {
  if (!currentScore || !currentScore.recommendations || currentScore.recommendations.length === 0) {
    alert("No recommendations to copy.");
    return;
  }
  const text = currentScore.recommendations.map((r, i) => `${i + 1}. ${r}`).join("\n");
  navigator.clipboard.writeText(text).then(() => {
    alert("Remediation checklist copied to clipboard!");
  });
}

function escapeHtml(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}
