ï»¿/* MarketTwin dashboard controller
 * Works against FastAPI endpoints exposed in src/api/main.py.
 */

const q = (sel, root = document) => root.querySelector(sel);
const qa = (sel, root = document) => Array.from(root.querySelectorAll(sel));

const summaryHeadline = q("#scenarioHeadline");
const summaryNarrative = q("#summaryNarrative");
const summaryGenerated = q("#summaryGenerated");
const summaryPositive = q("#summaryPositive");
const summaryNegative = q("#summaryNegative");
const summaryBias = q("#summaryBias");
const positiveList = q("#positiveList");
const negativeList = q("#negativeList");

const RECENT_MAX = 200;
const recentBuffer = [];
const biasGaugeFill = q("#biasGaugeFill");
const biasGaugePointer = q("#biasGaugePointer");
const biasGaugeLabel = q("#biasGaugeLabel");
let summaryTabButtons = [];
let summaryTabPanels = [];
let activeSummaryTab = "overview";

const TICKER_NAMES = new Map([
  ["SPY", "SPDR S&P 500 ETF"],
  ["QQQ", "Invesco QQQ Trust"],
  ["DIA", "SPDR Dow Jones Industrial Average ETF"],
  ["NVDA", "NVIDIA Corporation"],
  ["AAPL", "Apple Inc."],
  ["TSLA", "Tesla, Inc."],
  ["MSFT", "Microsoft Corporation"],
  ["GOOG", "Alphabet Inc. Class C"],
  ["META", "Meta Platforms, Inc."],
  ["AMZN", "Amazon.com, Inc."],
  ["XLF", "Financial Select Sector SPDR Fund"],
]);

function resolveTickerName(ticker) {
  if (!ticker) return "";
  const upper = ticker.toUpperCase();
  if (TICKER_NAMES.has(upper)) return TICKER_NAMES.get(upper);
  const cache = window.__tickerNameCache || (window.__tickerNameCache = {});
  if (cache[upper]) return cache[upper];
  const cleaned = upper.replace(/[^A-Z0-9 ]/g, " ").replace(/\s+/g, " " ).trim();
  if (!cleaned) return upper;
  const label = cleaned
    .split(" ")
    .map((part) => part.charAt(0) + part.slice(1).toLowerCase())
    .join(" ");
  cache[upper] = label;
  return label;
}

const API = {
  async scenario(text, steps) {
    const res = await fetch("/scenario", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, steps }),
    });
    if (!res.ok) throw new Error(await parseError(res));
    return res.json();
  },
  async recent(n = 100) {
    const res = await fetch(`/recent?n=${n}`);
    if (res.status === 204 || res.status === 404) return [];
    if (!res.ok) throw new Error(await parseError(res));
    return res.json();
  },
  async metrics() {
    const res = await fetch("/metrics", { headers: { "Cache-Control": "no-cache" } });
    if (res.status === 304) return null;
    if (res.status === 404) return null;
    if (!res.ok) throw new Error(await parseError(res));
    return res.json();
  },
};

async function parseError(res) {
  try {
    const data = await res.json();
    if (data && data.detail) return Array.isArray(data.detail) ? data.detail.join("; ") : data.detail;
  } catch (_) {
    // ignore
  }
  return res.statusText || `HTTP ${res.status}`;
}

const Toaster = (() => {
  const host = q("#toaster");
  function push({ title, message = "", level = "info", timeout = 3500 }) {
    if (!host) return;
    const el = document.createElement("div");
    el.className = `toast ${level}`;
    el.innerHTML = `
      <span class="bp5-icon ${icon(level)}"></span>
      <span><span class="title">${escapeHtml(title)}</span>${message ? " &ndash; " + escapeHtml(message) : ""}</span>
    `;
    host.appendChild(el);
    setTimeout(() => el.remove(), timeout);
  }
  function icon(level) {
    return {
      info: "bp5-icon-info-sign",
      success: "bp5-icon-tick-circle",
      warn: "bp5-icon-warning-sign",
      error: "bp5-icon-error",
    }[level] || "bp5-icon-notification";
  }
  return { push };
})();

function escapeHtml(s) {
  return (s || "")
    .toString()
    .replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;" }[c]));
}

function isoToSec(ts) {
  const d = new Date(ts);
  return Number.isNaN(d.getTime()) ? Date.now() / 1000 : Math.floor(d.getTime() / 1000);
}

function formatNumber(value, digits = 2) {
  const num = Number(value);
  if (!Number.isFinite(num)) return String(value ?? "");
  return num.toFixed(digits);
}

function formatScore(value) {
  const num = Number(value);
  if (!Number.isFinite(num)) return "--";
  return `${num >= 0 ? "+" : ""}${num.toFixed(2)}`;
}
function formatPrice(value) {
  const num = Number(value);
  if (!Number.isFinite(num)) return "--";
  return `$${num.toFixed(2)}`;
}

function formatPercent(value, digits = 1) {
  const num = Number(value);
  if (!Number.isFinite(num)) return "--";
  const sign = num >= 0 ? "+" : "";
  return `${sign}${(num * 100).toFixed(digits)}%`;
}

function formatDate(value) {
  if (!value) return "--";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

function setBiasGauge(value) {
  const numeric = Number.isFinite(value) ? value : 0;
  const clamped = Math.max(-1, Math.min(1, numeric));
  const normalized = (clamped + 1) / 2;
  if (biasGaugeFill) {
    biasGaugeFill.style.transform = `scaleX(${normalized.toFixed(3)})`;
  }
  if (biasGaugePointer) {
    biasGaugePointer.style.left = `${(normalized * 100).toFixed(1)}%`;
  }
  if (biasGaugeLabel) {
    let label = "Neutral";
    if (clamped >= 0.05) label = "Bullish";
    else if (clamped <= -0.05) label = "Bearish";
    const magnitude = Math.abs(clamped) >= 0.01 ? ` ${formatScore(clamped)}` : "";
    biasGaugeLabel.textContent = `${label}${magnitude}`;
  }
}

function resetBiasGauge() {
  setBiasGauge(0);
}

function setSummaryTab(name = "overview") {
  activeSummaryTab = name;
  if (!summaryTabButtons.length || !summaryTabPanels.length) return;
  summaryTabButtons.forEach((btn) => {
    const isActive = btn.dataset.summaryTab === name;
    btn.classList.toggle("is-active", isActive);
    btn.setAttribute("aria-selected", String(isActive));
    btn.setAttribute("tabindex", isActive ? "0" : "-1");
  });
  summaryTabPanels.forEach((panel) => {
    const isActive = panel.dataset.summaryPanel === name;
    panel.classList.toggle("is-active", isActive);
    panel.setAttribute("aria-hidden", String(!isActive));
    panel.setAttribute("tabindex", isActive ? "0" : "-1");
  });
}

function createSparklineSvg(points, baselinePrice) {
  const width = 150;
  const height = 44;
  const padding = 4;
  const closes = (Array.isArray(points) ? points : [])
    .map((p) => Number(p.close))
    .filter((v) => Number.isFinite(v));
  if (!closes.length) {
    return `<svg viewBox="0 0 ${width} ${height}" preserveAspectRatio="none"></svg>`;
  }
  const min = Math.min(...closes);
  const max = Math.max(...closes);
  const range = max - min || 1;
  const first = closes[0];
  const last = closes[closes.length - 1];
  const stroke = last >= first ? "var(--accent-green)" : "var(--accent-red)";

  const stepX = closes.length > 1 ? (width - padding * 2) / (closes.length - 1) : 0;
  const coords = closes.map((value, idx) => {
    const x = padding + idx * stepX;
    const y = height - padding - ((value - min) / range) * (height - padding * 2);
    return { x, y };
  });

  const pointsPath = coords
    .map((point, idx) => `${idx === 0 ? "M" : "L"}${point.x.toFixed(2)} ${point.y.toFixed(2)}`)
    .join(" ");

  let baselineLine = "";
  const baseline = Number(baselinePrice);
  if (Number.isFinite(baseline)) {
    let y = height - padding - ((baseline - min) / range) * (height - padding * 2);
    if (Number.isFinite(y)) {
      y = Math.max(padding, Math.min(height - padding, y));
      baselineLine = `<line x1="${padding}" y1="${y.toFixed(2)}" x2="${(width - padding).toFixed(
        2,
      )}" y2="${y.toFixed(2)}" stroke="rgba(255,255,255,0.25)" stroke-dasharray="2 3" stroke-width="1"/>`;
    }
  }

  const lastCoord = coords[coords.length - 1];

  return `<svg viewBox="0 0 ${width} ${height}" preserveAspectRatio="none">
    ${baselineLine}
    <path class="sparkline-path" d="${pointsPath}" stroke="${stroke}" />
    <circle cx="${lastCoord.x.toFixed(2)}" cy="${lastCoord.y.toFixed(2)}" r="2.5" fill="${stroke}" />
  </svg>`;
}


function renderSummaryPanels(payload) {
  const overviewPanel = q('[data-summary-panel="overview"]');
  const ordersPanel = q('[data-summary-panel="orders"]');
  const distributionPanel = q('[data-summary-panel="distribution"]');
  const analogPanel = q('[data-summary-panel="analogs"]');
  if (!overviewPanel || !ordersPanel || !distributionPanel || !analogPanel) return;

  if (!payload || !Array.isArray(payload.impacts) || payload.impacts.length === 0) {
    const empty = '<p class="summary-empty">Run a simulation to populate this view.</p>';
    overviewPanel.innerHTML = empty;
    ordersPanel.innerHTML = empty;
    distributionPanel.innerHTML = empty;
    analogPanel.innerHTML = empty;
    setSummaryTab('overview');
    return;
  }

  const impacts = payload.impacts;
  const positives = impacts.filter((item) => Number(item.score || 0) >= 0).sort((a, b) => Number(b.score) - Number(a.score));
  const negatives = impacts.filter((item) => Number(item.score || 0) < 0).sort((a, b) => Number(a.score) - Number(b.score));
  const total = impacts.length;

  const deltas = impacts.map((impact) => {
    const baseline = Number(impact.baseline_price ?? 0);
    const projected = Number(impact.projected_price ?? baseline);
    if (!Number.isFinite(baseline) || baseline === 0) return 0;
    return (projected - baseline) / baseline;
  });
  const avgDelta = deltas.reduce((acc, val) => acc + val, 0) / (total || 1);
  const maxUpside = Math.max(...deltas);
  const maxDownside = Math.min(...deltas);

  const topPositives = positives.slice(0, 3);
  const topNegatives = negatives.slice(0, 3);

  overviewPanel.innerHTML = `
    <div class="summary-grid">
      <div class="summary-grid-item">
        <strong>Total impacts</strong>
        <span>${total}</span>
      </div>
      <div class="summary-grid-item">
        <strong>Average move</strong>
        <span>${formatPercent(avgDelta)}</span>
      </div>
      <div class="summary-grid-item">
        <strong>Top upside</strong>
        <span>${formatPercent(maxUpside)}</span>
      </div>
      <div class="summary-grid-item">
        <strong>Top downside</strong>
        <span>${formatPercent(maxDownside)}</span>
      </div>
    </div>
    <ul class="summary-list">
      <li>
        <span class="label">Leaders</span>
        <span>${topPositives.length ? topPositives.map((item) => `${escapeHtml(item.ticker)} ${formatScore(item.score)}`).join(', ') : 'None'}</span>
      </li>
      <li>
        <span class="label">Laggards</span>
        <span>${topNegatives.length ? topNegatives.map((item) => `${escapeHtml(item.ticker)} ${formatScore(item.score)}`).join(', ') : 'None'}</span>
      </li>
    </ul>
  `;

  const aggregatedOrders = [];
  impacts.forEach((impact) => {
    if (!Array.isArray(impact.orders)) return;
    impact.orders.forEach((order) => {
      aggregatedOrders.push({
        ticker: impact.ticker,
        ...order,
        qty: Number(order.qty) || 0,
        stage: order.stage,
      });
    });
  });
  aggregatedOrders.sort((a, b) => Math.abs(b.qty || 0) - Math.abs(a.qty || 0));
  const topOrders = aggregatedOrders.slice(0, 6);

  if (topOrders.length) {
    const rows = [
      `<div class="summary-row header"><div>Ticker</div><div>Leg</div><div>Qty</div><div>Order</div></div>`,
      ...topOrders.map((order) => {
        const sideClass = order.side === 'BUY' ? 'side-buy' : 'side-sell';
        const stage = order.stage ? escapeHtml(order.stage) : order.condition ? escapeHtml(order.condition) : '-';
        const orderLabel = [order.order_type, order.time_in_force].filter(Boolean).join(' · ');
        return `<div class="summary-row">
          <div>${escapeHtml(order.ticker || '')}</div>
          <div>${escapeHtml(stage)}</div>
          <div class="qty ${sideClass}">${formatNumber(order.qty || 0, 0)}</div>
          <div>${escapeHtml(orderLabel || '-')}</div>
        </div>`;
      }),
    ].join('');
    ordersPanel.innerHTML = `<div class="summary-table">${rows}</div>`;
  } else {
    ordersPanel.innerHTML = '<p class="summary-empty">No order detail available.</p>';
  }

  const baselineValues = impacts.map((impact) => Number(impact.baseline_price ?? 0)).filter((v) => Number.isFinite(v) && v > 0);
  const projectedValues = impacts.map((impact) => Number(impact.projected_price ?? 0)).filter((v) => Number.isFinite(v) && v > 0);
  const projectionCloses = impacts.flatMap((impact) =>
    Array.isArray(impact.projection) ? impact.projection.map((p) => Number(p.close)).filter((v) => Number.isFinite(v)) : [],
  );

  const baselineRange = baselineValues.length
    ? `${formatPrice(Math.min(...baselineValues))} → ${formatPrice(Math.max(...baselineValues))}`
    : '--';
  const projectedRange = projectedValues.length
    ? `${formatPrice(Math.min(...projectedValues))} → ${formatPrice(Math.max(...projectedValues))}`
    : '--';
  const distributionRange = projectionCloses.length
    ? `${formatPrice(Math.min(...projectionCloses))} → ${formatPrice(Math.max(...projectionCloses))}`
    : '--';

  distributionPanel.innerHTML = `
    <div class="summary-grid">
      <div class="summary-grid-item">
        <strong>Baseline range</strong>
        <span>${baselineRange}</span>
      </div>
      <div class="summary-grid-item">
        <strong>Projected range</strong>
        <span>${projectedRange}</span>
      </div>
      <div class="summary-grid-item">
        <strong>Simulation range</strong>
        <span>${distributionRange}</span>
      </div>
    </div>
  `;

  const analogPool = [];
  const analogMetricList = [];
  const newsMap = new Map();
  const analogSeen = new Set();

  impacts.forEach((impact) => {
    const tickerUpper = (impact.ticker || '').toUpperCase();
    const analogs = Array.isArray(impact.analogs) ? impact.analogs : [];
    analogs.forEach((analog) => {
      const key = `${tickerUpper}:${analog.id || analog.title || analog.date || analog.category || analog.summary || analog.similarity}`;
      if (analogSeen.has(key)) return;
      analogSeen.add(key);
      analogPool.push({
        ticker: tickerUpper,
        ...analog,
        similarity: Number(analog.similarity ?? 0),
      });
    });
    if (impact.analog_metrics) {
      analogMetricList.push({ ticker: tickerUpper, metrics: impact.analog_metrics });
    }
    const newsItems = Array.isArray(impact.news) ? impact.news : [];
    newsItems.forEach((item) => {
      const url = item?.url || item?.article_url || item?.link;
      if (!url || newsMap.has(url)) return;
      newsMap.set(url, {
        title: item.title || url,
        url,
        source: item.source,
        published: item.published || item.published_utc,
      });
    });
  });

  analogPool.sort((a, b) => (b.similarity ?? 0) - (a.similarity ?? 0));

  const aggregate = { drift: 0, vol: 0, skew: 0, kurtosis: 0, weight: 0 };

  analogMetricList.forEach(({ metrics }) => {
    if (!metrics) return;
    const weight = Math.max(1, Number(metrics.sample_size) || 1);
    aggregate.drift += Number(metrics.drift_avg || 0) * weight;
    aggregate.vol += Number(metrics.vol_avg || 0) * weight;
    aggregate.skew += Number(metrics.skew_avg || 0) * weight;
    aggregate.kurtosis += Number(metrics.kurtosis_avg || 0) * weight;
    aggregate.weight += weight;
  });

  if (aggregate.weight === 0 && analogPool.length) {
    analogPool.forEach((analog) => {
      aggregate.drift += Number(analog.drift || 0);
      aggregate.vol += Number(analog.vol || 0);
      aggregate.skew += Number(analog.skew || 0);
      aggregate.kurtosis += Number(analog.kurtosis || 3);
    });
    aggregate.weight = analogPool.length;
  }

  const avgDrift = aggregate.weight ? aggregate.drift / aggregate.weight : 0;
  const avgVol = aggregate.weight ? aggregate.vol / aggregate.weight : 0;
  const avgSkew = aggregate.weight ? aggregate.skew / aggregate.weight : 0;
  const avgKurt = aggregate.weight ? aggregate.kurtosis / aggregate.weight : 3;
  const sampleSize = Math.round(aggregate.weight) || 0;

  const analogHeader = `<div class="summary-row header analog-row"><div>Ticker</div><div>Event</div><div>Drift</div><div>Similarity</div><div>Source</div></div>`;
  const analogRows = analogPool.slice(0, 6).map((analog) => {
    const tagHtml = Array.isArray(analog.tags) && analog.tags.length
      ? `<div class="analog-tags">${analog.tags.slice(0, 4).map((tag) => `<span>${escapeHtml(tag)}</span>`).join('')}</div>`
      : '';
    const newsUrl = Array.isArray(analog.news) && analog.news.length ? analog.news[0] : null;
    const newsLink = newsUrl
      ? `<a class="analog-link" href="${escapeHtml(newsUrl)}" target="_blank" rel="noopener">Link</a>`
      : '—';
    const similarity = Number.isFinite(analog.similarity) ? formatNumber(analog.similarity, 2) : formatNumber(0, 2);
    return `<div class="summary-row analog-row">
      <div>${escapeHtml(analog.ticker || '')}</div>
      <div>
        <div class="analog-meta">
          <strong>${escapeHtml(analog.title || analog.id || analog.category || 'Analog event')}</strong>
          <span>${formatDate(analog.date)}</span>
        </div>
        ${tagHtml}
      </div>
      <div>${formatPercent(analog.drift ?? 0)}</div>
      <div>${similarity}</div>
      <div>${newsLink}</div>
    </div>`;
  });

  const newsItems = Array.from(newsMap.values()).slice(0, 4);
  const newsHtml = newsItems.length
    ? `<div class="analog-news"><h5>Recent headlines</h5><ul class="analog-news-list">${newsItems
        .map((item) => {
          const source = item.source ? `${escapeHtml(item.source)} · ` : '';
          return `<li>${source}<a class="analog-link" href="${escapeHtml(item.url)}" target="_blank" rel="noopener">${escapeHtml(item.title)}</a> (${formatDate(item.published)})</li>`;
        })
        .join('')}</ul></div>`
    : '';

  const analogRowsHtml = analogPool.length
    ? `<div class="summary-analog-list">${[analogHeader, ...analogRows].join('')}</div>`
    : '<p class="summary-empty">No analog events matched yet.</p>';

  analogPanel.innerHTML = `
    <div class="summary-grid">
      <div class="summary-grid-item">
        <strong>Avg drift</strong>
        <span>${formatPercent(avgDrift)}</span>
      </div>
      <div class="summary-grid-item">
        <strong>Avg vol</strong>
        <span>${formatPercent(avgVol)}</span>
      </div>
      <div class="summary-grid-item">
        <strong>Avg skew</strong>
        <span>${formatNumber(avgSkew, 2)}</span>
      </div>
      <div class="summary-grid-item">
        <strong>Avg kurtosis</strong>
        <span>${formatNumber(avgKurt, 2)}</span>
      </div>
    </div>
    <p class="summary-meta">Sample size: ${sampleSize}</p>
    ${analogRowsHtml}
    ${newsHtml}
  `;

  setSummaryTab(activeSummaryTab);
}
function renderRecent(items) {
  const host = q("#recent");
  const empty = q("#recentEmpty");
  if (!host || !empty) return;

  recentBuffer.length = 0;
  if (Array.isArray(items)) {
    items.slice(-RECENT_MAX).forEach((item) => recentBuffer.push(item));
  }

  host.innerHTML = "";

  if (recentBuffer.length === 0) {
    empty.classList.remove("is-hidden");
    return;
  }

  empty.classList.add("is-hidden");
  recentBuffer.forEach((event) => host.appendChild(makeFeedItem(event)));
  if (q("#autoScrollLive")?.checked) host.scrollTop = host.scrollHeight;
}

function appendRecentEvent(event) {
  const host = q("#recent");
  const empty = q("#recentEmpty");
  if (!host || !empty) return;

  const normalized = { ...event };
  normalized.timestamp = normalized.timestamp || normalized.ts || new Date().toISOString();
  recentBuffer.push(normalized);
  if (recentBuffer.length > RECENT_MAX) {
    recentBuffer.splice(0, recentBuffer.length - RECENT_MAX);
    if (host.childElementCount > RECENT_MAX - 1) {
      host.removeChild(host.firstChild);
    }
  }

  empty.classList.add("is-hidden");
  host.appendChild(makeFeedItem(normalized));
  if (q("#autoScrollLive")?.checked) host.scrollTop = host.scrollHeight;
}

function renderMetrics(json) {
  const pre = q("#metrics");
  const empty = q("#metricsEmpty");
  if (!pre || !empty) return;

  if (!json) {
    pre.textContent = "";
    empty.classList.remove("is-hidden");
    return;
  }
  empty.classList.add("is-hidden");
  pre.textContent = JSON.stringify(json, null, 2);
}

/* ---------- Actions ---------- */
async function onRunScenario() {
  const text = q("#scenarioText")?.value.trim();
  const steps = Math.max(5, Math.min(120, parseInt(q("#scenarioSteps")?.value || "20", 10)));
  if (!text) {
    Toaster.push({ title: "Scenario text is required", level: "warn" });
    return;
  }
  const runBtn = q("#runBtn");
  const status = q("#runStatus");
  if (runBtn) runBtn.disabled = true;
  if (status) status.textContent = "RunningÃ¢â‚¬Â¦";
  try {
    const res = await API.scenario(text, steps);
    renderImpacts(res);
    updateScenarioSummary(res);
    Toaster.push({ title: "Scenario generated", level: "success" });
  } catch (err) {
    Toaster.push({ title: "Scenario failed", message: String(err), level: "error", timeout: 6000 });
  } finally {
    if (runBtn) runBtn.disabled = false;
    if (status) status.textContent = "";
  }
}

async function refreshRecent() {
  try {
    const data = await API.recent(100);
    renderRecent(data);
    refreshRecent.warned = false;
  } catch (err) {
    if (!refreshRecent.warned) {
      Toaster.push({ title: "Recent feed unavailable", message: String(err), level: "warn", timeout: 4000 });
      refreshRecent.warned = true;
    }
  }
}
refreshRecent.warned = false;

async function refreshMetrics() {
  try {
    const data = await API.metrics();
    renderMetrics(data);
    if (data) Toaster.push({ title: "Metrics updated", level: "info" });
  } catch (err) {
    renderMetrics(null);
    Toaster.push({ title: "Metrics fetch failed", message: String(err), level: "warn" });
  }
}

function updateScenarioSummary(payload) {
  if (!summaryHeadline) return;
  if (!payload || !payload.impacts || payload.impacts.length === 0) {
    summaryHeadline.textContent = "Awaiting scenario input";
    if (summaryNarrative) {
      summaryNarrative.textContent = "Describe a macro event and run a simulation to see responses.";
    }
    if (summaryGenerated) summaryGenerated.textContent = "--";
    if (summaryPositive) summaryPositive.textContent = "--";
    if (summaryNegative) summaryNegative.textContent = "--";
    if (summaryBias) summaryBias.textContent = "--";
    if (positiveList) positiveList.innerHTML = '<li class="empty">No scenario yet.</li>';
    if (negativeList) negativeList.innerHTML = '<li class="empty">No scenario yet.</li>';
    resetBiasGauge();
    renderSummaryPanels(null);
    return;
  }

  const impacts = Array.isArray(payload.impacts) ? payload.impacts.slice() : [];
  const positives = impacts.filter((item) => item.score >= 0).sort((a, b) => b.score - a.score);
  const negatives = impacts.filter((item) => item.score < 0).sort((a, b) => a.score - b.score);

  summaryHeadline.textContent = payload.scenario || "Scenario";
  if (summaryGenerated) {
    summaryGenerated.textContent = payload.generated_at
      ? new Date(payload.generated_at).toLocaleString()
      : "Just now";
  }
  if (summaryPositive) summaryPositive.textContent = positives.length ? `${positives.length} tickers` : "None";
  if (summaryNegative) summaryNegative.textContent = negatives.length ? `${negatives.length} tickers` : "None";

  const net = impacts.reduce((acc, item) => acc + Number(item.score || 0), 0);
  if (summaryBias) {
    const biasLabel = net > 0.05 ? "Bullish" : net < -0.05 ? "Bearish" : "Neutral";
    summaryBias.textContent = `${biasLabel} (${formatScore(net)})`;
  }
  setBiasGauge(net);

  const topPositive = positives[0];
  const topNegative = negatives[0];
  if (summaryNarrative) {
    const parts = [];
    if (topPositive) parts.push(`Top positive: ${topPositive.ticker} ${formatScore(topPositive.score)}`);
    if (topNegative) parts.push(`Top negative: ${topNegative.ticker} ${formatScore(topNegative.score)}`);
    summaryNarrative.textContent = parts.join(" Â· ") || "Balanced response across agents.";
  }

  if (positiveList) {
    positiveList.innerHTML = positives.length
      ? positives
          .map(
            (impact) =>
              `<li><span class="signal-name">${impact.ticker}</span><span class="shock-value">${formatScore(
                impact.score,
              )}</span></li>`,
          )
          .join("")
      : '<li class="empty">No positive shocks</li>';
  }

  if (negativeList) {
    negativeList.innerHTML = negatives.length
      ? negatives
          .map(
            (impact) =>
              `<li><span class="signal-name">${impact.ticker}</span><span class="shock-value">${formatScore(
                impact.score,
              )}</span></li>`,
          )
          .join("")
      : '<li class="empty">No negative shocks</li>';
  }

  renderSummaryPanels(payload);
}

function startLiveStreamWithFallback() {
  const supportsSSE = typeof EventSource !== "undefined";
  let es = null;
  let reconnectTimer = null;
  let usingSSE = false;

  function cleanup() {
    if (es) es.close();
    es = null;
    if (reconnectTimer) clearTimeout(reconnectTimer);
    reconnectTimer = null;
  }

  function connect(runId = "demo") {
    if (!supportsSSE) return;
    cleanup();
    es = new EventSource(`/events?run_id=${encodeURIComponent(runId)}`);
    es.onopen = () => {
      usingSSE = true;
    };
    es.onmessage = (evt) => {
      if (!evt.data) return;
      usingSSE = true;
      try {
        const data = JSON.parse(evt.data);
        appendRecentEvent(data);
      } catch {
        // ignore malformed payloads
      }
    };
    es.onerror = () => {
      usingSSE = false;
      cleanup();
      reconnectTimer = setTimeout(() => connect(runId), 3000);
    };
  }

  if (supportsSSE) {
    connect();
  }

  const pollTimer = setInterval(() => {
    if (!usingSSE) refreshRecent();
  }, 5000);

  window.addEventListener("beforeunload", () => {
    cleanup();
    clearInterval(pollTimer);
  });
}

/* ---------- Wire up ---------- */
function main() {
  summaryTabButtons = qa(".summary-tab");
  summaryTabPanels = qa(".summary-panel");
  summaryTabButtons.forEach((btn) => {
    btn.addEventListener("click", () => {
      const target = btn.dataset.summaryTab || "overview";
      setSummaryTab(target);
    });
  });
  setSummaryTab(activeSummaryTab);
  resetBiasGauge();
  renderSummaryPanels(null);

  q("#runBtn")?.addEventListener("click", onRunScenario);
  q("#clearBtn")?.addEventListener("click", () => {
    if (q("#scenarioText")) q("#scenarioText").value = "";
    if (q("#scenarioSteps")) q("#scenarioSteps").value = 20;
    renderImpacts({ impacts: [] });
    updateScenarioSummary(null);
  });
  q("#refreshRecentBtn")?.addEventListener("click", refreshRecent);
  q("#refreshMetricsBtn")?.addEventListener("click", refreshMetrics);
  q("#downloadMetricsBtn")?.addEventListener("click", async () => {
    const metrics = await API.metrics();
    if (!metrics) {
      Toaster.push({ title: "No metrics to download", level: "warn" });
      return;
    }
    const blob = new Blob([JSON.stringify(metrics, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "metrics.json";
    a.click();
    URL.revokeObjectURL(url);
  });
  q("#darkMode")?.addEventListener("change", (e) => {
    document.documentElement.classList.toggle("bp5-dark", e.target.checked);
  });

  renderImpacts({ impacts: [] });
  updateScenarioSummary(null);
  renderRecent([]);
  refreshRecent();
  refreshMetrics();
  startLiveStreamWithFallback();
}

document.addEventListener("DOMContentLoaded", main);

















