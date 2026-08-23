/**
 * AgentReady Web Dashboard v2.0 Client Application
 */

let currentScore = null;
let currentProbes = [];
let currentPersonas = null;

document.addEventListener("DOMContentLoaded", () => {
  initEventListeners();
  initTabNavigation();
  loadTrackedDomains();
});

function initTabNavigation() {
  const tabBtns = document.querySelectorAll(".tab-btn");
  const tabPanes = document.querySelectorAll(".tab-pane");

  tabBtns.forEach((btn) => {
    btn.addEventListener("click", () => {
      const targetId = btn.getAttribute("data-tab");

      tabBtns.forEach((b) => b.classList.remove("active"));
      tabPanes.forEach((p) => p.classList.remove("active"));

      btn.classList.add("active");
      const targetPane = document.getElementById(targetId);
      if (targetPane) targetPane.classList.add("active");
    });
  });
}

function initEventListeners() {
  const scanBtn = document.getElementById("scanBtn");
  const simulateBtn = document.getElementById("simulateBtn");
  const probeBtn = document.getElementById("probeBtn");
  const urlInput = document.getElementById("urlInput");
  const domainSelect = document.getElementById("domainSelect");
  const copyFixesBtn = document.getElementById("copyFixesBtn");
  const runCompareBtn = document.getElementById("runCompareBtn");
  const downloadReportBtn = document.getElementById("downloadReportBtn");

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

  simulateBtn.addEventListener("click", () => {
    const url = urlInput.value.trim();
    if (url) runSimulate(url);
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

  if (copyFixesBtn) copyFixesBtn.addEventListener("click", copyRemediations);
  if (runCompareBtn) runCompareBtn.addEventListener("click", runCompetitorComparison);
  if (downloadReportBtn) downloadReportBtn.addEventListener("click", downloadExecutiveReport);
}

async function loadTrackedDomains() {
  try {
    const resp = await fetch("/api/domains");
    if (!resp.ok) return;
    const domains = await resp.json();
    const select = document.getElementById("domainSelect");
    select.innerHTML = '<option value="">Tracked Domains...</option>';

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
  scanBtn.disabled = true;
  scanBtn.innerHTML = '<span class="btn-text">Scanning...</span>';

  try {
    const resp = await fetch("/api/scan", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
    });
    if (!resp.ok) throw new Error(`Scan failed with status ${resp.status}`);
    const score = await resp.json();
    renderScoreDashboard(score);
    loadTrackedDomains();
    runSimulate(url);
  } catch (err) {
    alert(`Scan error: ${err.message}`);
  } finally {
    scanBtn.disabled = false;
    scanBtn.innerHTML = '<span class="btn-text">Run Full Scan</span>';
  }
}

async function runSimulate(url) {
  const simulateBtn = document.getElementById("simulateBtn");
  simulateBtn.disabled = true;
  simulateBtn.innerHTML = '<span>Simulating...</span>';

  try {
    const resp = await fetch("/api/simulate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
    });
    if (!resp.ok) throw new Error("Simulation failed");
    const data = await resp.json();
    currentPersonas = data;
    renderPersonas(data);
  } catch (err) {
    console.warn("Persona simulation error:", err);
  } finally {
    simulateBtn.disabled = false;
    simulateBtn.innerHTML = '<span>Simulate Personas</span>';
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
    if (!resp.ok) throw new Error("Probe failed");
    loadDomainProbes(url);
  } catch (err) {
    alert(`Probe error: ${err.message}`);
  } finally {
    probeBtn.disabled = false;
    probeBtn.textContent = "Probe LLMs";
  }
}

async function runCompetitorComparison() {
  const targetUrl = document.getElementById("compTargetInput").value.trim() || document.getElementById("urlInput").value.trim();
  const rawComps = document.getElementById("compUrlsInput").value.trim();
  const resultsDiv = document.getElementById("battlegroundResults");

  if (!targetUrl || !rawComps) {
    alert("Please provide both target site and competitor URLs.");
    return;
  }

  const compUrls = rawComps.split(",").map((u) => u.trim()).filter(Boolean);
  resultsDiv.innerHTML = '<p class="empty-state">Running competitor benchmark battles across models...</p>';

  try {
    const resp = await fetch("/api/compare", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ target_url: targetUrl, competitor_urls: compUrls, dry_run: true }),
    });
    if (!resp.ok) throw new Error("Comparison failed");
    const data = await resp.json();
    renderCompetitorResults(data);
  } catch (err) {
    resultsDiv.innerHTML = `<p class="empty-state" style="color: var(--accent-red)">Error: ${err.message}</p>`;
  }
}

function renderCompetitorResults(data) {
  const container = document.getElementById("battlegroundResults");
  let tableHtml = `
    <table class="compare-table">
      <thead>
        <tr>
          <th>Domain</th>
          <th>Readiness Score</th>
          <th>Grade</th>
          <th>Citation Rate</th>
        </tr>
      </thead>
      <tbody>
  `;

  for (const [domain, stats] of Object.entries(data.competitor_scores || {})) {
    const isTarget = domain === data.target_domain;
    const highlight = isTarget ? 'style="font-weight: bold; color: var(--accent-cyan);"' : "";
    tableHtml += `
      <tr ${highlight}>
        <td>${domain} ${isTarget ? "(Target)" : ""}</td>
        <td>${stats.overall_score || "--"}/100</td>
        <td><span class="badge badge-info">${stats.grade || "--"}</span></td>
        <td>${stats.citation_rate_pct || 0}%</td>
      </tr>
    `;
  }

  tableHtml += `
      </tbody>
    </table>
    <div style="margin-top: 16px;">
      <p><strong>Calculated Citation Win Rate:</strong> <span style="color: var(--accent-green); font-weight: bold;">${data.citation_win_rate_pct || 0}%</span></p>
    </div>
  `;
  container.innerHTML = tableHtml;
}

function renderScoreDashboard(score) {
  currentScore = score;

  document.getElementById("overallScore").textContent = score.overall_score.toFixed(0);
  document.getElementById("gradeBadge").textContent = score.grade;
  document.getElementById("targetUrlDisplay").textContent = score.url;
  document.getElementById("scoreSummary").textContent = score.summary || "Complete readiness evaluation calculated.";

  // Update circular gauge
  const gaugeFill = document.getElementById("gaugeFill");
  const circumference = 2 * Math.PI * 50;
  const offset = circumference - (score.overall_score / 100) * circumference;
  gaugeFill.style.strokeDashoffset = offset;

  // Render Grade Color
  const gradeBadge = document.getElementById("gradeBadge");
  gradeBadge.className = `grade-badge grade-${score.grade.toLowerCase()}`;

  renderSignalsGrid(score.components);
  renderBotTable(score.components);
  renderRemediations(score.recommendations);
  renderMultimodalAndI18n(score);
}

function renderSignalsGrid(components) {
  const container = document.getElementById("signalsGrid");
  container.innerHTML = "";

  (components || []).forEach((c) => {
    const card = document.createElement("div");
    card.className = "signal-card card";
    const statusClass = c.status === "PASS" ? "status-pass" : c.status === "WARN" ? "status-warn" : "status-fail";

    card.innerHTML = `
      <div class="signal-header">
        <span class="signal-title">${c.display_name}</span>
        <span class="status-pill ${statusClass}">${c.status}</span>
      </div>
      <div class="signal-score-row">
        <span class="signal-score">${c.score.toFixed(0)}</span>
        <span class="signal-weight">Weight: ${(c.weight * 100).toFixed(0)}%</span>
      </div>
      <p class="signal-details">${c.details || ""}</p>
    `;
    container.appendChild(card);
  });
}

function renderBotTable(components) {
  const botComp = (components || []).find((c) => c.name === "bot_permissions");
  const tbody = document.getElementById("botTableBody");
  tbody.innerHTML = "";

  if (!botComp || !botComp.evidence || !botComp.evidence.bots) {
    tbody.innerHTML = '<tr><td colspan="3" class="text-center">No bot permissions available.</td></tr>';
    return;
  }

  const bots = botComp.evidence.bots;
  document.getElementById("botCountBadge").textContent = `${Object.keys(bots).length} AI Crawlers`;

  const engineMap = {
    GPTBot: "OpenAI ChatGPT Search",
    ClaudeBot: "Anthropic Claude Search",
    PerplexityBot: "Perplexity AI",
    "Google-Extended": "Gemini AI Search",
    Bytespider: "ByteDance / TikTok AI",
    CCBot: "Common Crawl Dataset",
  };

  for (const [bot, allowed] of Object.entries(bots)) {
    const tr = document.createElement("tr");
    const statusPill = allowed
      ? '<span class="status-pill status-pass">ALLOWED</span>'
      : '<span class="status-pill status-fail">BLOCKED</span>';

    tr.innerHTML = `
      <td><strong>${bot}</strong></td>
      <td>${engineMap[bot] || "Autonomous LLM"}</td>
      <td>${statusPill}</td>
    `;
    tbody.appendChild(tr);
  }
}

function renderRemediations(recommendations) {
  const list = document.getElementById("remediationList");
  list.innerHTML = "";

  if (!recommendations || recommendations.length === 0) {
    list.innerHTML = '<p class="empty-state" style="color: var(--accent-green);">All signals optimized! No urgent actions.</p>';
    return;
  }

  recommendations.forEach((rec, idx) => {
    const item = document.createElement("div");
    item.className = "remediation-item";
    item.innerHTML = `
      <span class="rem-num">${idx + 1}</span>
      <span class="rem-text">${rec}</span>
    `;
    list.appendChild(item);
  });
}

function renderPersonas(data) {
  const container = document.getElementById("personasGrid");
  const badge = document.getElementById("personaOverallBadge");
  badge.textContent = `Compatibility: ${data.overall_compatibility || 0}/100`;
  container.innerHTML = "";

  for (const [key, p] of Object.entries(data.personas || {})) {
    const card = document.createElement("div");
    card.className = "persona-card";
    const statusColor = p.status === "EXCELLENT" ? "var(--accent-green)" : p.status === "MODERATE" ? "var(--accent-yellow)" : "var(--accent-red)";

    let listItems = "";
    (p.key_strengths || []).forEach((str) => {
      listItems += `<li>${str}</li>`;
    });

    card.innerHTML = `
      <div class="persona-header">
        <span class="persona-title">${p.name}</span>
        <span class="persona-score" style="color: ${statusColor};">${p.compatibility_score.toFixed(0)}%</span>
      </div>
      <span class="badge badge-info">${p.status}</span>
      <ul class="persona-list">
        ${listItems || "<li>Baseline archetype evaluation.</li>"}
      </ul>
    `;
    container.appendChild(card);
  }
}

function renderMultimodalAndI18n(score) {
  const multiComp = (score.components || []).find((c) => c.name === "multimodal_readiness");
  const i18nComp = (score.components || []).find((c) => c.name === "multilingual_readiness");

  const multiDiv = document.getElementById("multimodalDetails");
  if (multiDiv) {
    if (multiComp) {
      multiDiv.innerHTML = `
        <p><strong>Score:</strong> ${multiComp.score.toFixed(0)}/100</p>
        <p>${multiComp.details}</p>
      `;
    } else {
      multiDiv.innerHTML = '<p class="empty-state">Visuals ready for multimodal models.</p>';
    }
  }

  const i18nDiv = document.getElementById("i18nDetails");
  if (i18nDiv) {
    if (i18nComp) {
      i18nDiv.innerHTML = `
        <p><strong>Score:</strong> ${i18nComp.score.toFixed(0)}/100</p>
        <p>${i18nComp.details}</p>
      `;
    } else {
      i18nDiv.innerHTML = '<p class="empty-state">Default language index configured.</p>';
    }
  }
}

function renderProbes(probes) {
  currentProbes = probes;
  const list = document.getElementById("probeList");
  const countBadge = document.getElementById("probeCountBadge");
  countBadge.textContent = `${probes.length} probes`;

  if (!probes || probes.length === 0) {
    list.innerHTML = '<p class="empty-state">Click "Probe LLMs" above to test real citation behavior across models.</p>';
    return;
  }

  list.innerHTML = "";
  probes.slice(0, 10).forEach((p) => {
    const card = document.createElement("div");
    card.className = "probe-card";
    const statusPill = p.is_cited
      ? '<span class="status-pill status-pass">CITED</span>'
      : '<span class="status-pill status-fail">NOT CITED</span>';

    card.innerHTML = `
      <div class="probe-meta">
        <span><strong>${p.provider}</strong> (${p.model_name || "LLM"})</span>
        ${statusPill}
      </div>
      <div class="probe-prompt">"${p.prompt}"</div>
      <div class="probe-response">${(p.raw_response || "").substring(0, 200)}...</div>
    `;
    list.appendChild(card);
  });
}

function copyRemediations() {
  if (!currentScore || !currentScore.recommendations) return;
  const text = currentScore.recommendations.map((r, i) => `${i + 1}. ${r}`).join("\n");
  navigator.clipboard.writeText(text).then(() => {
    alert("Optimization plan copied to clipboard!");
  });
}

function downloadExecutiveReport() {
  const url = document.getElementById("urlInput").value.trim();
  if (!url) return;
  window.open(`/api/report?url=${encodeURIComponent(url)}`, "_blank");
}
