const session = JSON.parse(sessionStorage.getItem("agentflow_demo_session") || "{}");
const agentId = Number(session.agentId || 1);
const state = { providers: [], positions: [], alerts: [], transactions: [], reserve: null, agent: null };

const $ = (selector) => document.querySelector(selector);
const money = (value) => `৳ ${Number(value || 0).toLocaleString("en-BD", { maximumFractionDigits: 0 })}`;
const providerLabel = (code) => ({ bkash_sim: "bKash", nagad_sim: "Nagad", rocket_sim: "Rocket", shared_cash_sim: "Shared Cash Reserve" }[code] || code);
const providerColor = (code) => ({ bkash_sim: "#d6336c", nagad_sim: "#7048a5", rocket_sim: "#d97706" }[code] || "#246bce");
const minutes = (value) => value === null || value === undefined ? "No depletion estimate" : `${Math.max(0, Math.round(value))} min`;

async function api(path, options = {}) {
  const response = await fetch(`${API_BASE_URL}${path}`, { headers: { "Content-Type": "application/json" }, ...options });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || `API request failed (${response.status})`);
  }
  return response.json();
}

function selectedProvider() { return $("#providerFilter").value; }
function displayPositions() { return state.positions.filter((p) => selectedProvider() === "all" || p.provider_code === selectedProvider()); }

function setApiStatus(kind, text) {
  const node = $("#apiStatus"); node.className = `api-status ${kind}`; node.innerHTML = `<i></i> ${text}`;
}
function showError(message) { $("#errorBanner").textContent = message; $("#errorBanner").hidden = false; }
function clearError() { $("#errorBanner").hidden = true; }
function toast(message) { const node = $("#toast"); node.textContent = message; node.hidden = false; window.setTimeout(() => { node.hidden = true; }, 3600); }

function renderHeader() {
  $("#agentName").textContent = state.agent.name;
  $("#agentMeta").textContent = `Agent ${state.agent.id} · ${state.agent.area} · Live data from the deployed API`;
}

function renderSummary() {
  const positions = displayPositions();
  const reserve = state.reserve;
  const physical = reserve?.physical_cash;
  const total = positions.reduce((sum, position) => sum + position.balance, 0);
  const active = state.alerts.filter((alert) => alert.status !== "resolved").length;
  const lowConfidence = positions.filter((p) => p.forecast.confidence === "low");
  $("#sharedCash").textContent = physical ? money(physical.current_balance) : "—";
  $("#sharedCashHint").textContent = physical ? `Safety threshold: ${money(physical.safety_threshold)} · ${minutes(physical.minutes_to_safety_threshold)}` : "No reserve data";
  $("#totalEmoney").textContent = money(total);
  $("#emoneyHint").textContent = `${positions.length} separate provider wallet${positions.length === 1 ? "" : "s"}`;
  $("#activeAlerts").textContent = active;
  $("#alertsHint").textContent = active ? "Open or acknowledged alerts" : "No active alerts";
  $("#confidenceSummary").textContent = lowConfidence.length ? "Low" : "High";
  $("#confidenceHint").textContent = lowConfidence.length ? `${lowConfidence.length} provider feed needs verification` : "All displayed provider feeds are fresh";
}

function renderPositions() {
  const positions = displayPositions();
  $("#providerGrid").innerHTML = positions.length ? positions.map((p) => {
    const forecast = p.forecast;
    return `<article class="provider-card ${p.quality_status !== "fresh" ? "stale" : ""}" style="border-top-color:${providerColor(p.provider_code)}">
      <div class="provider-top"><div><div class="provider-name" style="color:${providerColor(p.provider_code)}">${p.display_name}</div><span class="small-copy">${providerLabel(p.provider_code)} e-money</span></div><span class="status-chip ${p.quality_status}">${p.quality_status}</span></div>
      <div class="provider-value">${money(p.balance)}</div><span class="small-copy">Safety threshold ${money(p.safety_threshold)}</span>
      <div class="forecast-row"><span>Time to safety threshold</span><strong>${minutes(forecast.minutes_to_threshold)}</strong></div>
      <div class="forecast-row"><span>Confidence</span><span class="confidence-chip ${forecast.confidence}">${forecast.confidence}</span></div>
      <p class="provider-reason">${forecast.reason}</p>
    </article>`;
  }).join("") : `<div class="empty-state">No provider matches the selected filter.</div>`;
}

function reserveItem(label, data, color) {
  return `<article class="reserve-item" style="border-left:4px solid ${color}"><div class="reserve-title"><span>${label}</span><span>${data.transaction_count ?? state.reserve.completed_transaction_count ?? 0} transactions</span></div><div class="reserve-stats"><div class="reserve-stat"><span>Net burn / min</span><strong>${money(data.net_burn_per_minute)}</strong></div><div class="reserve-stat"><span>To safety threshold</span><strong>${minutes(data.minutes_to_safety_threshold)}</strong></div><div class="reserve-stat"><span>To exhaustion</span><strong>${minutes(data.minutes_to_exhaustion)}</strong></div></div></article>`;
}
function renderReserve() {
  const reserve = state.reserve;
  if (!reserve) return;
  const provider = selectedProvider();
  let items = provider === "all" ? Object.entries(reserve.provider_e_money) : [[provider, reserve.provider_e_money[provider]]];
  items = items.filter(([, data]) => data);
  $("#velocityCaption").textContent = `${reserve.window_minutes}-minute window · ${reserve.completed_transaction_count} completed transactions`;
  $("#reserveAnalysis").innerHTML = [reserveItem("Shared physical cash", reserve.physical_cash, "#087f5b"), ...items.map(([code, data]) => reserveItem(`${providerLabel(code)} e-money`, data, providerColor(code)))].join("");
}

function renderQuality() {
  const positions = displayPositions();
  $("#qualityPanel").innerHTML = positions.map((p) => {
    const low = p.forecast.confidence === "low";
    return `<article class="quality-item ${low ? "low" : ""}"><h3>${providerLabel(p.provider_code)}: ${low ? "verification required" : "fresh data"}</h3><p>${p.forecast.reason}</p></article>`;
  }).join("") || `<div class="empty-state">No provider data for this filter.</div>`;
}

function renderAlerts() {
  const status = $("#alertFilter").value;
  const provider = selectedProvider();
  const alerts = state.alerts.filter((a) => (status === "all" || a.status === status) && (provider === "all" || a.provider_code === provider));
  $("#alertTotal").textContent = alerts.length;
  $("#alertList").innerHTML = alerts.length ? alerts.map((a) => `<article class="alert-card ${a.status}">
    <div class="alert-top"><span class="type-chip">${a.type.replaceAll("_", " ")}</span><span class="alert-status ${a.status}">${a.status}</span><span class="small-copy">${providerLabel(a.provider_code)}</span></div>
    <h3 class="alert-title">${a.title}</h3><div class="alert-meta"><span>Receives: <strong>${a.recipient}</strong></span><span>Owner: <strong>${a.owner}</strong></span><span>Confidence: <strong>${a.confidence}</strong></span></div>
    <div class="alert-evidence"><strong>Evidence</strong>${a.evidence}</div><p class="alert-recommendation"><strong>Safe next step:</strong> ${a.recommended_action}</p>${a.note ? `<p class="small-copy"><strong>Review note:</strong> ${a.note}</p>` : ""}
    <div class="alert-actions">${a.status === "open" ? `<button class="primary" data-ack="${a.id}">Acknowledge</button>` : ""}${a.status !== "resolved" ? `<button data-resolve="${a.id}" data-title="${a.title.replaceAll('"', '&quot;')}">Resolve with note</button>` : ""}</div>
  </article>`).join("") : `<div class="empty-state">No alerts match this filter.</div>`;
}

function renderPattern(payload) {
  const findings = payload.unusual_activity || [];
  $("#patternPanel").innerHTML = findings.length ? findings.map((f) => `<article class="finding-card"><h3>Requires review: ${providerLabel(f.provider_code)}</h3><p>${f.transaction_count} transactions and ${f.cash_out_count} cash-outs in one ten-minute window · anomaly score ${f.anomaly_score}</p><ul>${f.reasons.map((reason) => `<li>${reason}</li>`).join("")}</ul><p><strong>Safe next step:</strong> ${f.recommended_action}</p><div class="bn-alert">গত ১০ মিনিটে ${f.cash_out_count}টি ক্যাশ-আউট হয়েছে এবং পরিমাণগুলোর ${Math.round(f.cash_out_similarity_ratio * 100)}% প্রায় একই। এটি স্বাভাবিক চাহিদাও হতে পারে, তবে পরবর্তী পদক্ষেপের আগে লেনদেনগুলো পর্যালোচনা করুন।</div></article>`).join("") : `<div class="empty-state">${payload.message}</div>`;
}
function renderMonthly(payload) {
  const findings = payload.unusual_activity || [];
  $("#monthlyPanel").innerHTML = findings.length ? findings.map((f) => `<article class="finding-card"><h3>Monthly volume requires review</h3><p>${providerLabel(f.provider_code)} at ${f.location}: ${money(f.actual_monthly_volume)} actual vs ${money(f.expected_monthly_volume)} expected (${f.volume_ratio}×).</p><ul>${f.reasons.map((reason) => `<li>${reason}</li>`).join("")}</ul><p><strong>Safe next step:</strong> ${f.recommended_action}</p></article>`).join("") : `<div class="empty-state">${payload.message}</div>`;
}
function renderMetrics(payload) {
  $("#metricsGrid").innerHTML = payload.metrics.map((metric) => `<article class="metric-card"><span class="small-copy">${metric.name}</span><strong>${metric.unit === "BDT" ? money(metric.value) : `${(metric.value * 100).toFixed(metric.value === 1 ? 0 : 2)}%`}</strong><p>${metric.explanation}</p></article>`).join("");
  $("#metricsCaveat").textContent = payload.caveat;
}
function renderTransactions() {
  const provider = selectedProvider();
  const rows = state.transactions.filter((transaction) => provider === "all" || transaction.provider_code === provider);
  $("#transactionRows").innerHTML = rows.length ? rows.map((t) => `<tr><td>${new Date(t.event_at).toLocaleString()}</td><td>${providerLabel(t.provider_code)}</td><td class="${t.type}">${t.type.replaceAll("_", " ")}</td><td>${money(t.amount)}</td><td>${t.location}</td><td>${t.status}</td></tr>`).join("") : `<tr><td colspan="6">No transactions match the selected filter.</td></tr>`;
}

async function runInference() {
  const [pattern, monthly] = await Promise.all([
    api(`/inference/transaction-pattern/database?agent_id=${agentId}&w=30`),
    api(`/inference/monthly-volume/database?agent_id=${agentId}&year=${new Date().getFullYear()}&month=${new Date().getMonth() + 1}&event_context=${$("#eventContext").value}`),
  ]);
  renderPattern(pattern); renderMonthly(monthly);
}
async function refreshDashboard() {
  clearError(); setApiStatus("", "Refreshing live data…");
  const windowMinutes = $("#windowFilter").value;
  try {
    const [agent, providers, positions, reserve, alerts, transactions, metrics] = await Promise.all([
      api(`/agents/${agentId}`), api("/providers"), api(`/positions?agent_id=${agentId}`), api(`/cash_reserve_analysis?agent_id=${agentId}&w=${windowMinutes}`), api(`/alerts?agent_id=${agentId}&include_resolved=true`), api(`/transactions?agent_id=${agentId}&limit=20`), api("/metrics"),
    ]);
    Object.assign(state, { agent, providers, positions, reserve, alerts, transactions });
    const selector = $("#providerFilter");
    const previous = selector.value; selector.innerHTML = `<option value="all">All providers</option>${providers.map((p) => `<option value="${p.code}">${p.display_name}</option>`).join("")}`; selector.value = [...selector.options].some((o) => o.value === previous) ? previous : "all";
    renderHeader(); renderSummary(); renderPositions(); renderReserve(); renderQuality(); renderAlerts(); renderTransactions(); renderMetrics(metrics);
    await runInference();
    $("#updatedAt").textContent = `Last refreshed ${new Date().toLocaleTimeString()}`;
    setApiStatus("ready", "Live API connected");
  } catch (error) { setApiStatus("error", "API connection failed"); showError(`${error.message} Refresh after the deployed API is available.`); }
}
async function patchAlert(alertId, payload) { await api(`/alerts/${alertId}`, { method: "PATCH", body: JSON.stringify(payload) }); await refreshDashboard(); }

$("#providerFilter").addEventListener("change", () => { renderSummary(); renderPositions(); renderReserve(); renderQuality(); renderAlerts(); renderTransactions(); });
$("#alertFilter").addEventListener("change", renderAlerts);
$("#windowFilter").addEventListener("change", refreshDashboard);
$("#refreshButton").addEventListener("click", refreshDashboard);
$("#rerunPatternButton").addEventListener("click", async () => { try { const data = await api(`/inference/transaction-pattern/database?agent_id=${agentId}&w=30`); renderPattern(data); toast("Short-term pattern analysis refreshed."); } catch (error) { showError(error.message); } });
$("#rerunMonthlyButton").addEventListener("click", async () => { try { const now = new Date(); const data = await api(`/inference/monthly-volume/database?agent_id=${agentId}&year=${now.getFullYear()}&month=${now.getMonth() + 1}&event_context=${$("#eventContext").value}`); renderMonthly(data); toast("Monthly-volume analysis refreshed."); } catch (error) { showError(error.message); } });
$("#alertList").addEventListener("click", async (event) => { const ack = event.target.dataset.ack; const resolve = event.target.dataset.resolve; try { if (ack) { await patchAlert(ack, { status: "acknowledged" }); toast("Alert acknowledged and retained for human review."); } if (resolve) { $("#dialogTitle").textContent = event.target.dataset.title; $("#resolutionNote").value = ""; $("#actionDialog").dataset.alertId = resolve; $("#actionDialog").showModal(); } } catch (error) { showError(error.message); } });
$("#confirmResolveButton").addEventListener("click", async (event) => { event.preventDefault(); const note = $("#resolutionNote").value.trim(); if (!note) { $("#dialogText").textContent = "A short human-review note is required before resolution."; return; } try { await patchAlert($("#actionDialog").dataset.alertId, { status: "resolved", note }); $("#actionDialog").close(); toast("Alert resolved with a recorded human review note."); } catch (error) { showError(error.message); } });
$("#resetDemoButton").addEventListener("click", async () => { if (!window.confirm("Reset all synthetic demo data? This permanently clears completed support cases and their history records.")) return; try { const result = await api("/demo/reset", { method: "POST" }); toast(`${result.message} Refreshing dashboard…`); await refreshDashboard(); } catch (error) { showError(error.message); } });
$("#signOutButton").addEventListener("click", () => { sessionStorage.removeItem("agentflow_demo_session"); window.location.assign("login.html"); });

if (session.role && session.role !== "agent") window.location.replace("provider_dashboard.html");
refreshDashboard();
