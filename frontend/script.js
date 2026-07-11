/* ===== MOCK DATA ========================================================== */

const PROVIDER_COLORS = {
  bKash: '#E2136E', Nagad: '#6C2C7A', Rocket: '#F58220'
};
const PROVIDER_BGS = {
  bKash: '#fce4ec', Nagad: '#f3e5f5', Rocket: '#fff3e0'
};

function rnd(min, max) { return Math.round(min + Math.random() * (max - min)); }

function buildMockData() {
  const now = new Date();
  const t = (h, m) => new Date(now.getFullYear(), now.getMonth(), now.getDate(), h, m);

  // Shared cash: started with 120k, now ~35k
  const sharedCash = 35000;
  const sharedCashInit = 120000;

  // Provider states
  const providers = {
    bKash: {
      name: 'bKash', balance: 12500, limit: 50000,
      trend: 'down', status: 'active', color: PROVIDER_COLORS.bKash,
      lastUpdated: now,
      shortageEstimate: addMin(now, 25),
      confidence: 85, dailyVolume: 142000
    },
    Nagad: {
      name: 'Nagad', balance: 45000, limit: 60000,
      trend: 'stable', status: 'active', color: PROVIDER_COLORS.Nagad,
      lastUpdated: now,
      shortageEstimate: addMin(now, 130),
      confidence: 90, dailyVolume: 89000
    },
    Rocket: {
      name: 'Rocket', balance: 22000, limit: 40000,
      trend: 'unknown', status: 'delayed', color: PROVIDER_COLORS.Rocket,
      lastUpdated: addMin(now, -45),
      shortageEstimate: addMin(now, 85),
      confidence: 40, dailyVolume: 56000
    }
  };

  // Alerts — covering Scenarios A, B, D
  const alerts = [
    {
      id: 'ALT-001', provider: 'bKash', type: 'liquidity', severity: 'high',
      title: 'bKash e-money shortage imminent',
      titleBn: 'বিকাশ ই-মানি শীঘ্রই শেষ হবে',
      description: 'At current transaction rate, bKash e-money will be exhausted by approximately 3:15 PM. Physical cash will last until ~3:45 PM.',
      descriptionBn: 'বর্তমান লেনদেনের ধারা অনুযায়ী বিকাশ ই-মানি বিকেল ৩:১৫ এর মধ্যে শেষ হবে। নগদ টাকা চলবে বিকেল ৩:৪৫ পর্যন্ত।',
      evidence: 'Last 30 min: 18 cash-out transactions, avg Tk 4,200 per txn. bKash share: 72% of all cash-outs. Balance dropped from Tk 28,500 to Tk 12,500.',
      confidence: 85,
      owner: 'Field Officer — Kamal Hossain',
      ownerId: 'FO-042',
      status: 'acknowledged',
      nextStep: 'Arrange additional Tk 30,000 e-money top-up or guide customers to use Nagad/Rocket.',
      nextStepBn: 'অতিরিক্ত ৩০,০০০ টাকা ই-মানি টপ-আপের ব্যবস্থা করুন অথবা গ্রাহকদের নগদ/রকেট ব্যবহারে নির্দেশনা দিন।',
      createdAt: addMin(now, -20),
      acknowledgedAt: addMin(now, -15),
      resolvedAt: null
    },
    {
      id: 'ALT-002', provider: 'bKash', type: 'anomaly', severity: 'medium',
      title: 'Unusual transaction velocity detected',
      titleBn: 'অস্বাভাবিক লেনদেনের গতি সনাক্ত হয়েছে',
      description: '12 cash-out transactions in the last 10 minutes from only 2 accounts, all between Tk 4,450–4,550.',
      descriptionBn: 'গত ১০ মিনিটে মাত্র ২টি অ্যাকাউন্ট থেকে ১২টি ক্যাশ-আউট লেনদেন হয়েছে, সবগুলোর পরিমাণ ৪,৪৫০-৪,৫৫০ টাকার মধ্যে।',
      evidence: 'Accounts: ****4521 (7 txns, Tk 31,570 total), ****7893 (5 txns, Tk 22,450 total). Amounts: [4520, 4480, 4550, 4510, 4490, 4530, 4470, 4540, 4500, 4520, 4490, 4510]. Pattern: near-identical amounts in rapid succession.',
      confidence: 65,
      owner: 'Risk Reviewer — Pending Assignment',
      ownerId: null,
      status: 'new',
      nextStep: 'Review flagged transactions before authorizing large cash restock. May be normal Eid demand or pattern requiring further review.',
      nextStepBn: 'বড় নগদ পুনরায় সরবরাহের আগে চিহ্নিত লেনদেনগুলো পর্যালোচনা করুন। এটি ঈদ-পূর্ব স্বাভাবিক চাহিদা বা পর্যালোচনার প্রয়োজন এমন প্যাটার্ন হতে পারে।',
      createdAt: addMin(now, -8),
      acknowledgedAt: null,
      resolvedAt: null
    },
    {
      id: 'ALT-003', provider: 'Rocket', type: 'data_quality', severity: 'low',
      title: 'Rocket data feed delayed',
      titleBn: 'রকেট ডেটা ফিড বিলম্বিত',
      description: 'Rocket balance and transaction data is 45 minutes old. Forecast confidence is reduced.',
      descriptionBn: 'রকেট ব্যালেন্স এবং লেনদেনের তথ্য ৪৫ মিনিট পুরনো। পূর্বাভাসের নির্ভরযোগ্যতা কম।',
      evidence: 'Last Rocket update received at 1:45 PM. Current time: 2:30 PM. No new data in 3 consecutive polling cycles.',
      confidence: 40,
      owner: 'System — Auto-detected',
      ownerId: null,
      status: 'new',
      nextStep: 'Check Rocket connectivity. Displaying last known balance with reduced confidence. No action required from agent.',
      nextStepBn: 'রকেট সংযোগ পরীক্ষা করুন। সর্বশেষ জানা ব্যালেন্স কম নির্ভরযোগ্যতার সাথে দেখানো হচ্ছে। এজেন্টের কোনো পদক্ষেপ প্রয়োজন নেই।',
      createdAt: addMin(now, -10),
      acknowledgedAt: null,
      resolvedAt: null
    }
  ];

  // Cases — Scenario D coordinated response
  const cases = [
    {
      id: 'CASE-001', alertId: 'ALT-001', provider: 'bKash',
      priority: 'high', status: 'in_progress',
      owner: 'Field Officer — Kamal Hossain',
      nextStep: 'Arrange Tk 30,000 e-money top-up or redirect customers',
      timeline: [
        { action: 'Alert created by system', by: 'System', at: addMin(now, -20), done: true },
        { action: 'Auto-routed to Field Officer (Shahbagh zone)', by: 'Routing Engine', at: addMin(now, -19), done: true },
        { action: 'Acknowledged by Kamal Hossain', by: 'Kamal Hossain', at: addMin(now, -15), done: true },
        { action: 'Contacted agent — confirmed high demand', by: 'Kamal Hossain', at: addMin(now, -10), done: true },
        { action: 'Arranging Tk 20,000 from nearby agent (AGT-042)', by: 'Kamal Hossain', at: addMin(now, -3), done: false, active: true },
        { action: 'Resolved — liquidity restored', by: '', at: null, done: false }
      ],
      notes: 'Agent Rahim Store confirmed pre-Eid cash-out surge. Nearby agent AGT-042 (Motijheel) has agreed to share Tk 20,000 cash. Awaiting transfer confirmation.'
    },
    {
      id: 'CASE-002', alertId: 'ALT-002', provider: 'bKash',
      priority: 'medium', status: 'escalated',
      owner: 'Risk Reviewer — Pending Assignment',
      nextStep: 'Review flagged transactions',
      timeline: [
        { action: 'Alert created by system', by: 'System', at: addMin(now, -8), done: true },
        { action: 'Flagged as unusual velocity pattern', by: 'Anomaly Engine', at: addMin(now, -7), done: true },
        { action: 'Pending risk reviewer assignment', by: '', at: null, done: false, active: true },
        { action: 'Under review', by: '', at: null, done: false }
      ],
      notes: 'Anomaly engine flagged repeated amounts from 2 accounts. Pattern matches transaction splitting heuristic. Escalated to risk team for review before cash restock approval.'
    }
  ];

  // Generate recent transactions
  const txns = [];
  const accounts = ['****4521','****7893','****2345','****6789','****0123','****4567','****8901','****2345'];
  const types = ['cash-out','cash-out','cash-out','cash-in','cash-out','cash-out'];
  const txnTimes = [];
  for (let i = 0; i < 30; i++) {
    txnTimes.push(addMin(now, -rnd(1, 35)));
  }
  txnTimes.sort((a,b)=>b-a);
  for (let i = 0; i < 30; i++) {
    const prov = i < 18 ? 'bKash' : (i < 24 ? 'Nagad' : 'Rocket');
    const isFlagged = prov === 'bKash' && i < 12;
    const amt = isFlagged ? rnd(4450, 4550) : rnd(500, 15000);
    txns.push({
      time: txnTimes[i],
      provider: prov,
      type: isFlagged ? 'cash-out' : types[rnd(0,5)],
      amount: amt,
      account: isFlagged ? (i < 7 ? '****4521' : '****7893') : accounts[rnd(0,7)],
      flagged: isFlagged,
      flagReason: isFlagged ? 'Repeated amount / velocity' : ''
    });
  }

  return { sharedCash, sharedCashInit, providers, alerts, cases, txns };
}

function addMin(date, mins) {
  const d = new Date(date); d.setMinutes(d.getMinutes() + mins); return d;
}

function fmtTime(d) {
  return d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false });
}
function fmtDate(d) {
  return d.toLocaleDateString('en-US', { weekday: 'short', year: 'numeric', month: 'short', day: 'numeric' });
}
function fmtCurrency(n) {
  return '৳ ' + n.toLocaleString('en-IN');
}
function fmtSince(d) {
  const diff = Math.round((new Date() - d) / 60000);
  if (diff < 1) return 'Just now';
  if (diff < 60) return diff + 'm ago';
  return Math.round(diff / 60) + 'h ago';
}

/* ===== APP STATE ========================================================= */

let data = buildMockData();
let currentFilter = 'all';
let simInterval = null;
let simRunning = false;

/* ===== RENDER FUNCTIONS ================================================== */

function renderClock() {
  const now = new Date();
  document.getElementById('headerClock').textContent = now.toLocaleTimeString('en-US', { hour12: false });
  document.getElementById('headerDate').textContent = fmtDate(now);
}

function renderKPI() {
  const { sharedCash, providers } = data;
  const totalEmoney = providers.bKash.balance + providers.Nagad.balance + providers.Rocket.balance;
  const totalLiquidity = sharedCash + totalEmoney;
  const cashPct = Math.round((sharedCash / 120000) * 100);
  const highAlerts = data.alerts.filter(a => a.severity === 'high').length;
  const medAlerts = data.alerts.filter(a => a.severity === 'medium').length;
  const totalLiquidityPct = Math.round((totalLiquidity / (120000 + 150000)) * 100);

  document.getElementById('kpiCash').textContent = fmtCurrency(sharedCash);
  document.getElementById('kpiCashSub').textContent = cashPct + '% of initial remaining';
  document.getElementById('kpiEmoney').textContent = fmtCurrency(totalEmoney);
  document.getElementById('kpiEmoneySub').textContent = 'bKash ৳' + providers.bKash.balance.toLocaleString('en-IN') + ' | Nagad ৳' + providers.Nagad.balance.toLocaleString('en-IN') + ' | Rocket ৳' + providers.Rocket.balance.toLocaleString('en-IN');
  document.getElementById('kpiHealth').textContent = totalLiquidityPct + '%';
  document.getElementById('kpiHealthSub').textContent = 'bKash shortage in ~25 min';
  document.getElementById('kpiAlerts').textContent = data.alerts.filter(a => a.status !== 'resolved').length;
  document.getElementById('kpiAlertsSub').textContent = highAlerts + ' high, ' + medAlerts + ' medium';
}

function renderProviderBalances() {
  const grid = document.getElementById('providerGrid');
  grid.innerHTML = '';
  Object.values(data.providers).forEach(p => {
    if (currentFilter !== 'all' && p.name !== currentFilter) return;
    const pct = Math.round((p.balance / p.limit) * 100);
    const trendIcon = p.trend === 'down' ? '↓' : p.trend === 'up' ? '↑' : p.trend === 'unknown' ? '—' : '→';
    const trendClass = p.trend;
    const confClass = p.confidence >= 80 ? 'high' : p.confidence >= 50 ? 'medium' : 'low';
    const statusClass = p.status === 'delayed' ? 'delayed' : 'active';
    const statusLabel = p.status === 'delayed' ? '⚠ Delayed' : '● Active';
    const barColor = p.color;

    const card = document.createElement('div');
    card.className = 'provider-card';
    card.style.borderTop = '3px solid ' + p.color;
    card.innerHTML = `
      <div class="provider-card-top">
        <span class="provider-name" style="color:${p.color}">${p.name}</span>
        <span class="provider-status ${statusClass}">${statusLabel}</span>
      </div>
      <div class="provider-balance" style="color:${p.color}">${fmtCurrency(p.balance)}</div>
      <div class="provider-bar">
        <div class="progress-bar-container">
          <div class="progress-bar" style="width:${pct}%;background:${barColor}"></div>
        </div>
      </div>
      <div class="provider-meta">
        <span>${pct}% of ৳${(p.limit/1000).toFixed(0)}K limit</span>
        <span class="provider-trend ${trendClass}">${trendIcon} ${p.trend}</span>
      </div>
      <div class="provider-confidence ${confClass}">
        ${p.status === 'delayed' ? '⚠' : '✓'} Confidence: ${p.confidence}%
        ${p.status === 'delayed' ? '<span style="margin-left:4px;font-weight:400;color:#b45309">(data delayed)</span>' : ''}
      </div>
      <div style="font-size:11px;color:var(--text2);margin-top:6px">
        Last updated: ${fmtSince(p.lastUpdated)} ${p.status === 'delayed' ? '— data may be stale' : ''}
      </div>
    `;
    grid.appendChild(card);
  });

  // Update shared cash
  const cashPct = Math.round((data.sharedCash / 120000) * 100);
  document.getElementById('sharedCashAmount').textContent = fmtCurrency(data.sharedCash);
  document.getElementById('sharedCashBar').style.width = cashPct + '%';
  document.getElementById('sharedCashPct').textContent = cashPct + '% remaining';
}

function renderForecast() {
  const container = document.getElementById('forecastTimeline');
  container.innerHTML = '';

  const now = new Date();
  const items = [
    {
      label: 'bKash e-money', provider: 'bKash',
      until: data.providers.bKash.shortageEstimate,
      confidence: data.providers.bKash.confidence,
      color: PROVIDER_COLORS.bKash,
      urgent: true
    },
    {
      label: 'Physical Cash', provider: null,
      until: addMin(now, 45),
      confidence: 80,
      color: '#059669',
      urgent: true
    },
    {
      label: 'Rocket e-money', provider: 'Rocket',
      until: data.providers.Rocket.shortageEstimate,
      confidence: data.providers.Rocket.confidence,
      color: PROVIDER_COLORS.Rocket,
      urgent: false
    },
    {
      label: 'Nagad e-money', provider: 'Nagad',
      until: data.providers.Nagad.shortageEstimate,
      confidence: data.providers.Nagad.confidence,
      color: PROVIDER_COLORS.Nagad,
      urgent: false
    }
  ];

  // Sort by urgency (soonest first)
  items.sort((a, b) => a.until - b.until);

  let maxDiff = 0;
  items.forEach(item => {
    const diff = (item.until - now) / 60000;
    if (diff > maxDiff) maxDiff = diff;
  });
  if (maxDiff < 60) maxDiff = 60;

  items.forEach(item => {
    const diffMin = Math.max(0, (item.until - now) / 60000);
    const pct = Math.min(100, (diffMin / maxDiff) * 100);
    const confClass = item.confidence >= 80 ? 'high' : item.confidence >= 50 ? 'medium' : 'low';
    const timeStr = diffMin < 1 ? '<1 min' : diffMin < 60 ? Math.round(diffMin) + ' min' : (diffMin / 60).toFixed(1) + ' hrs';

    const el = document.createElement('div');
    el.className = 'forecast-item';
    el.innerHTML = `
      <div class="forecast-icon" style="background:${item.color}">
        ${item.provider ? item.provider[0] : '💰'}
      </div>
      <div class="forecast-body">
        <div class="forecast-label">
          ${item.label}
          ${item.urgent ? '<span style="color:var(--high);font-size:11px">⚠ Shortage risk</span>' : ''}
        </div>
        <div class="forecast-bar-wrap">
          <div class="forecast-bar-outer">
            <div class="forecast-bar-inner" style="width:${pct}%;background:${item.color}"></div>
          </div>
          <span class="forecast-time" style="color:${item.urgent ? 'var(--high)' : 'var(--text)'}">~${timeStr}</span>
        </div>
        <div class="forecast-confidence">Confidence: ${item.confidence}% <span class="provider-confidence ${confClass}" style="display:inline-flex;padding:0 6px">${item.confidence >= 80 ? 'High' : item.confidence >= 50 ? 'Medium' : 'Low'}</span></div>
      </div>
    `;
    container.appendChild(el);
  });
}

function renderAlerts() {
  const container = document.getElementById('alertList');
  container.innerHTML = '';

  const visible = data.alerts.filter(a => {
    if (currentFilter !== 'all' && a.provider !== currentFilter) return false;
    return a.status !== 'resolved';
  });

  document.getElementById('alertCount').textContent = visible.length;

  visible.forEach(a => {
    const card = document.createElement('div');
    card.className = `alert-card ${a.severity}`;
    card.dataset.alertId = a.id;
    const statusClass = a.status;
    const statusLabel = a.status.charAt(0).toUpperCase() + a.status.slice(1);
    const confClass = a.confidence >= 80 ? 'high' : a.confidence >= 50 ? 'medium' : 'low';

    card.innerHTML = `
      <div class="alert-top">
        <span class="alert-severity ${a.severity}">${a.severity}</span>
        <span class="alert-provider" style="background:${PROVIDER_BGS[a.provider]};color:${PROVIDER_COLORS[a.provider]}">${a.provider}</span>
        <span style="font-size:11px;color:var(--text2)">${fmtSince(a.createdAt)}</span>
      </div>
      <div class="alert-title">${a.title}</div>
      <div class="alert-desc">${a.description}</div>
      <div class="alert-desc-bn">${a.descriptionBn}</div>
      <div class="alert-evidence" id="ev-${a.id}">
        <strong>Evidence:</strong> ${a.evidence}
        <div style="margin-top:4px;font-size:11px;color:var(--text2)">Confidence: ${a.confidence}% — <span class="provider-confidence ${confClass}" style="display:inline-flex;padding:0 6px">${a.confidence >= 80 ? 'High' : a.confidence >= 50 ? 'Medium' : 'Low'}</span></div>
      </div>
      <button class="alert-evidence-toggle" data-evid="${a.id}">Show evidence →</button>
      <div class="alert-bottom">
        <span class="alert-owner">👤 Owner: <strong>${a.owner}</strong></span>
        <span class="alert-status ${statusClass}">${statusLabel}</span>
      </div>
      <div style="font-size:12px;color:var(--text2);margin-top:4px">
        <strong>Recommended next step:</strong> ${a.nextStep}
        <div style="font-family:var(--font-bn);font-size:12px;color:var(--text2);margin-top:2px">${a.nextStepBn}</div>
      </div>
      <div class="alert-actions">
        ${a.status === 'new' ? `<button class="alert-action-btn primary" data-action="acknowledge" data-alert="${a.id}">✓ Acknowledge</button>` : ''}
        ${a.status === 'acknowledged' ? `<button class="alert-action-btn escalate" data-action="escalate" data-alert="${a.id}">▲ Escalate</button>` : ''}
        ${a.status === 'acknowledged' || a.status === 'new' ? `<button class="alert-action-btn resolve" data-action="resolve" data-alert="${a.id}">✓ Resolve</button>` : ''}
      </div>
    `;
    container.appendChild(card);
  });
}

function renderAnomalies() {
  const container = document.getElementById('anomalyContent');
  container.innerHTML = '';

  // Find flagged txns
  const flagged = data.txns.filter(t => t.flagged);
  if (flagged.length === 0) {
    container.innerHTML = '<div style="padding:20px;text-align:center;color:var(--text2)">No unusual activity detected in current time range.</div>';
    return;
  }

  // Group by pattern
  const anomalyCards = [
    {
      type: 'velocity',
      title: 'Rapid cash-out velocity detected',
      titleBn: 'দ্রুত ক্যাশ-আউটের গতি সনাক্ত করা হয়েছে',
      desc: `${flagged.length} cash-out transactions in the last 15 minutes — significantly above normal rate.`,
      descBn: `গত ১৫ মিনিটে ${flagged.length} টি ক্যাশ-আউট লেনদেন — স্বাভাবিক হারের তুলনায় উল্লেখযোগ্যভাবে বেশি।`,
      txns: flagged.slice(0, 8),
      confidence: 65,
      detail: `Normal rate for this time: 3-5 txns/15min. Current: ${flagged.length} txns/15min.`
    },
    {
      type: 'repeated',
      title: 'Near-identical transaction amounts',
      titleBn: 'প্রায় একই পরিমাণের লেনদেন',
      desc: 'Multiple transactions within Tk 4,450–4,550 range from a small set of accounts.',
      descBn: 'সীমিত সংখ্যক অ্যাকাউন্ট থেকে একাধিক লেনদেন ৪,৪৫০-৪,৫৫০ টাকার মধ্যে।',
      txns: flagged.slice(0, 6),
      confidence: 60,
      detail: 'Amounts cluster around Tk 4,500. Possible legitimate Eid demand or transaction splitting pattern.'
    }
  ];

  anomalyCards.forEach(ac => {
    const card = document.createElement('div');
    card.className = 'anomaly-card';
    card.innerHTML = `
      <div class="anomaly-header">
        <span class="anomaly-badge ${ac.type}">${ac.type}</span>
        <span style="font-size:11px;color:var(--text2)">Advisory — not a fraud determination</span>
      </div>
      <div class="anomaly-title">${ac.title}</div>
      <div class="anomaly-title" style="font-family:var(--font-bn);font-size:13px;color:var(--text2)">${ac.titleBn}</div>
      <div class="anomaly-detail">${ac.desc}</div>
      <div class="anomaly-detail" style="font-family:var(--font-bn)">${ac.descBn}</div>
      <div class="anomaly-txns">
        ${ac.txns.map(t => `<span class="anomaly-txn">${fmtCurrency(t.amount)}</span>`).join('')}
      </div>
      <div class="anomaly-detail" style="margin-top:4px">${ac.detail}</div>
      <div class="anomaly-confidence">
        Confidence: ${ac.confidence}%
        <span style="margin-left:8px;font-size:11px;color:var(--text2)">
          This may be normal pre-Eid demand. Human review recommended before any action.
        </span>
      </div>
      <div style="font-family:var(--font-bn);font-size:12px;color:var(--text2);margin-top:4px">
        এটি ঈদ-পূর্ব স্বাভাবিক চাহিদাও হতে পারে। কোনো পদক্ষেপের আগে মানব পর্যালোচনা প্রয়োজন।
      </div>
    `;
    container.appendChild(card);
  });

  // Explanation note
  const note = document.createElement('div');
  note.style.cssText = 'padding:10px 14px;background:#f8fafc;border-radius:8px;font-size:12px;color:var(--text2);margin-top:10px;border:1px dashed var(--border)';
  note.innerHTML = `<strong>⚠ Important:</strong> These flags are <strong>not</strong> fraud determinations. They highlight patterns that may be legitimate (pre-Eid demand surge) or may require review. Always conduct human review before taking action.`;
  container.appendChild(note);
}

function renderCases() {
  const container = document.getElementById('caseList');
  container.innerHTML = '';

  data.cases.forEach(c => {
    const card = document.createElement('div');
    card.className = 'case-card';

    const tlHtml = c.timeline.map(t => {
      let cls = 'case-tl-item';
      if (t.done) cls += ' done';
      if (t.active) cls += ' active';
      const timeStr = t.at ? fmtTime(t.at) : '—';
      return `<div class="${cls}">
        <span class="tl-action">${t.action}</span>
        <span class="tl-meta"> — ${t.by} at ${timeStr}</span>
      </div>`;
    }).join('');

    card.innerHTML = `
      <div class="case-top">
        <span class="case-id">${c.id}</span>
        <div style="display:flex;gap:6px">
          <span class="case-priority ${c.priority}">${c.priority.toUpperCase()}</span>
          <span class="case-status ${c.status}">${c.status.replace('_',' ').toUpperCase()}</span>
        </div>
      </div>
      <div style="font-size:12px;color:var(--text2);margin-bottom:6px">
        Provider: <strong style="color:${PROVIDER_COLORS[c.provider]}">${c.provider}</strong>
      </div>
      <div class="case-owner">👤 Owner: <strong>${c.owner}</strong></div>
      <div class="case-timeline">${tlHtml}</div>
      <div class="case-notes">
        <span class="case-notes-label">📝 Case Notes</span>
        ${c.notes}
      </div>
      <div style="font-size:12px;color:var(--text2);margin-top:6px">
        <strong>Next step:</strong> ${c.nextStep}
      </div>
    `;
    container.appendChild(card);
  });
}

function renderTransactions() {
  const container = document.getElementById('txnTable');
  container.innerHTML = '';

  let txns = data.txns;
  if (currentFilter !== 'all') {
    txns = txns.filter(t => t.provider === currentFilter);
  }

  if (txns.length === 0) {
    container.innerHTML = '<div style="padding:20px;text-align:center;color:var(--text2)">No transactions found.</div>';
    return;
  }

  const table = document.createElement('table');
  table.innerHTML = `
    <thead>
      <tr>
        <th>Time</th>
        <th>Provider</th>
        <th>Type</th>
        <th>Amount</th>
        <th>Account</th>
        <th>Flag</th>
      </tr>
    </thead>
    <tbody>
      ${txns.slice(0, 20).map(t => `
        <tr>
          <td>${fmtTime(t.time)}</td>
          <td><span class="txn-provider" style="color:${PROVIDER_COLORS[t.provider]}">${t.provider}</span></td>
          <td>${t.type}</td>
          <td class="txn-amount">${fmtCurrency(t.amount)}</td>
          <td style="font-family:monospace">${t.account}</td>
          <td><span class="txn-flag ${t.flagged ? 'flagged' : 'normal'}">${t.flagged ? '⚠ Flagged' : 'Normal'}</span></td>
        </tr>
      `).join('')}
    </tbody>
  `;
  container.appendChild(table);

  if (txns.length > 20) {
    const note = document.createElement('div');
    note.style.cssText = 'font-size:12px;color:var(--text2);margin-top:8px;text-align:center';
    note.textContent = `Showing 20 of ${txns.length} transactions`;
    container.appendChild(note);
  }
}

function renderDataQualityNotice() {
  const rocket = data.providers.Rocket;
  if (rocket.status === 'delayed') {
    const section = document.getElementById('dataQualitySection');
    const existing = section.querySelector('.dq-card.rocket-delay');
    if (!existing) {
      const card = document.createElement('div');
      card.className = 'dq-card rocket-delay';
      card.style.cssText = 'display:flex;align-items:start;gap:14px;padding:14px 18px;background:#fffbeb;border-radius:var(--radius);box-shadow:var(--shadow);border:1px solid #fde68a;margin-top:0';
      card.innerHTML = `
        <div style="font-size:24px;flex-shrink:0">⏳</div>
        <div>
          <span style="display:block;font-weight:700;font-size:14px;color:#b45309">Rocket data delayed — reduced confidence</span>
          <span style="font-size:12px;color:var(--text2)">Last Rocket data received ${fmtSince(rocket.lastUpdated)}. Showing last known balance with ${rocket.confidence}% confidence. Forecast and alerts for Rocket are based on stale data. No action needed — system will resume normal operation when data feed recovers.</span>
          <div style="font-family:var(--font-bn);font-size:12px;color:var(--text2);margin-top:4px">রকেটের তথ্য বিলম্বিত — নির্ভরযোগ্যতা হ্রাস পেয়েছে। সর্বশেষ তথ্য ${fmtSince(rocket.lastUpdated)} আগে গৃহীত হয়েছে।</div>
        </div>
      `;
      section.prepend(card);
    }
  }
}

/* ===== INTERACTIONS ====================================================== */

// Provider filter pills
document.getElementById('providerFilter').addEventListener('click', e => {
  const pill = e.target.closest('.pill');
  if (!pill) return;
  document.querySelectorAll('#providerFilter .pill').forEach(p => p.classList.remove('active'));
  pill.classList.add('active');
  currentFilter = pill.dataset.provider;
  refreshDashboard();
});

// Evidence toggle (delegated)
document.addEventListener('click', e => {
  const btn = e.target.closest('.alert-evidence-toggle');
  if (!btn) return;
  const ev = document.getElementById('ev-' + btn.dataset.evid);
  if (ev) {
    ev.classList.toggle('open');
    btn.textContent = ev.classList.contains('open') ? 'Hide evidence ↑' : 'Show evidence →';
  }
});

// Alert actions (delegated)
document.addEventListener('click', e => {
  const btn = e.target.closest('.alert-action-btn');
  if (!btn) return;
  const action = btn.dataset.action;
  const alertId = btn.dataset.alert;

  const alert = data.alerts.find(a => a.id === alertId);
  if (!alert) return;

  if (action === 'acknowledge') {
    alert.status = 'acknowledged';
    alert.acknowledgedAt = new Date();
    alert.owner = 'Field Officer — Kamal Hossain';
    // Update related case
    const c = data.cases.find(c => c.alertId === alertId);
    if (c) {
      c.status = 'in_progress';
      c.timeline.push({ action: 'Acknowledged by Kamal Hossain', by: 'Kamal Hossain', at: new Date(), done: true });
    }
  } else if (action === 'escalate') {
    alert.status = 'acknowledged'; // stays owned but escalated
    alert.owner = 'Risk Team — Escalated';
    const c = data.cases.find(c => c.alertId === alertId);
    if (c) {
      c.status = 'escalated';
      c.timeline.push({ action: 'Escalated to Risk Review Team', by: 'Kamal Hossain', at: new Date(), done: true });
      c.timeline.push({ action: 'Pending risk analyst review', by: '', at: null, done: false, active: true });
    }
  } else if (action === 'resolve') {
    alert.status = 'resolved';
    alert.resolvedAt = new Date();
    const c = data.cases.find(c => c.alertId === alertId);
    if (c) {
      c.status = 'resolved';
      c.timeline.push({ action: 'Resolved', by: 'System', at: new Date(), done: true });
    }
  }

  refreshDashboard();
});

// Modal: click alert card to see details
document.addEventListener('click', e => {
  const card = e.target.closest('.alert-card');
  if (!card) return;
  if (e.target.closest('.alert-action-btn') || e.target.closest('.alert-evidence-toggle')) return;
  const alertId = card.dataset.alertId;
  const alert = data.alerts.find(a => a.id === alertId);
  if (!alert) return;
  showAlertModal(alert);
});

// Modal close
document.getElementById('modalClose').addEventListener('click', closeModal);
document.getElementById('modalOverlay').addEventListener('click', e => {
  if (e.target === e.currentTarget) closeModal();
});

function showAlertModal(alert) {
  const body = document.getElementById('modalBody');
  const confClass = alert.confidence >= 80 ? 'high' : alert.confidence >= 50 ? 'medium' : 'low';
  body.innerHTML = `
    <div style="margin-bottom:16px">
      <span class="alert-severity ${alert.severity}" style="display:inline-block">${alert.severity.toUpperCase()}</span>
      <span class="alert-provider" style="background:${PROVIDER_BGS[alert.provider]};color:${PROVIDER_COLORS[alert.provider]};display:inline-block;margin-left:8px">${alert.provider}</span>
    </div>
    <h2 style="font-size:20px;margin-bottom:4px">${alert.title}</h2>
    <div style="font-family:var(--font-bn);font-size:15px;color:var(--text2);margin-bottom:12px">${alert.titleBn}</div>
    <div style="margin-bottom:12px">${alert.description}</div>
    <div style="font-family:var(--font-bn);font-size:14px;color:var(--text2);margin-bottom:12px;padding:8px 12px;background:#f8fafc;border-radius:8px">${alert.descriptionBn}</div>

    <div style="margin-bottom:12px">
      <strong style="display:block;margin-bottom:4px">📋 Evidence</strong>
      <div style="padding:10px;background:#f8fafc;border-radius:8px;font-size:13px;color:var(--text2);border-left:3px solid var(--medium)">${alert.evidence}</div>
    </div>

    <div style="margin-bottom:12px">
      <strong>Confidence:</strong> ${alert.confidence}% <span class="provider-confidence ${confClass}" style="display:inline-flex;padding:2px 8px">${alert.confidence >= 80 ? 'High' : alert.confidence >= 50 ? 'Medium' : 'Low'}</span>
    </div>

    <div style="margin-bottom:12px">
      <strong>👤 Owner:</strong> ${alert.owner}<br>
      <strong>Status:</strong> ${alert.status.charAt(0).toUpperCase() + alert.status.slice(1)}<br>
      <strong>Created:</strong> ${alert.createdAt.toLocaleString()}<br>
      ${alert.acknowledgedAt ? `<strong>Acknowledged:</strong> ${alert.acknowledgedAt.toLocaleString()}<br>` : ''}
      ${alert.resolvedAt ? `<strong>Resolved:</strong> ${alert.resolvedAt.toLocaleString()}<br>` : ''}
    </div>

    <div style="margin-bottom:12px">
      <strong>Recommended next step:</strong>
      <div style="margin-top:4px">${alert.nextStep}</div>
      <div style="font-family:var(--font-bn);font-size:13px;color:var(--text2);margin-top:4px">${alert.nextStepBn}</div>
    </div>

    <div style="padding:10px;background:#fef3c7;border-radius:8px;font-size:12px;color:#b45309">
      <strong>⚠ Advisory:</strong> This alert is a decision-support signal. It does not constitute a fraud determination or financial instruction. Human review is required before any operational action.
    </div>
  `;
  document.getElementById('modalOverlay').classList.remove('hidden');
}

function closeModal() {
  document.getElementById('modalOverlay').classList.add('hidden');
}

// Simulation: run scenario
document.getElementById('simScenarioBtn').addEventListener('click', () => {
  if (simRunning) return;
  simRunning = true;

  // Simulate balance decreasing over time
  simInterval = setInterval(() => {
    const bKash = data.providers.bKash;
    const drop = rnd(300, 800);
    bKash.balance = Math.max(1000, bKash.balance - drop);
    data.sharedCash = Math.max(5000, data.sharedCash - rnd(200, 500));

    // Simulate new transactions
    if (Math.random() > 0.4) {
      const amt = rnd(4450, 4550);
      data.txns.unshift({
        time: new Date(),
        provider: 'bKash',
        type: 'cash-out',
        amount: amt,
        account: Math.random() > 0.5 ? '****4521' : '****7893',
        flagged: true,
        flagReason: 'Repeated amount / velocity'
      });
    } else {
      data.txns.unshift({
        time: new Date(),
        provider: ['bKash','Nagad','Rocket'][rnd(0,2)],
        type: Math.random() > 0.3 ? 'cash-out' : 'cash-in',
        amount: rnd(500, 12000),
        account: '****' + rnd(1000, 9999),
        flagged: false,
        flagReason: ''
      });
    }
    if (data.txns.length > 100) data.txns.length = 100;

    refreshDashboard();
  }, 3000);
});

/* ===== REFRESH =========================================================== */

function refreshDashboard() {
  renderKPI();
  renderProviderBalances();
  renderForecast();
  renderAlerts();
  renderAnomalies();
  renderCases();
  renderTransactions();
  renderDataQualityNotice();
}

/* ===== INIT ============================================================== */

renderClock();
setInterval(renderClock, 1000);
refreshDashboard();

console.log('SUST Agent Dashboard loaded. Data:', data);
console.log('Features demonstrated:');
console.log('  - Unified shared cash + multi-provider e-money view');
console.log('  - Liquidity forecast with shortage timeline');
console.log('  - Anomaly detection (velocity, repeated amounts)');
console.log('  - Alert workflow (acknowledge, escalate, resolve)');
console.log('  - Case coordination with timeline & notes');
console.log('  - Provider data boundaries & confidence indicators');
console.log('  - Bengali/Banglish explanations');
console.log('  - Graceful degradation for delayed data (Rocket)');
console.log('  - Advisory language — no fraud claims');
