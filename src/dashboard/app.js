/* MarketTwin dashboard controller
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
  if (!overviewPanel || !ordersPanel || !distributionPanel) return;

  if (!payload || !Array.isArray(payload.impacts) || payload.impacts.length === 0) {
    const empty = '<p class="summary-empty">Run a simulation to populate this view.</p>';
    overviewPanel.innerHTML = empty;
    ordersPanel.innerHTML = empty;
    distributionPanel.innerHTML = empty;
    setSummaryTab("overview");
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
        <span>${topPositives.length ? topPositives.map((item) => `${escapeHtml(item.ticker)} ${formatScore(item.score)}`).join(", ") : "None"}</span>
      </li>
      <li>
        <span class="label">Laggards</span>
        <span>${topNegatives.length ? topNegatives.map((item) => `${escapeHtml(item.ticker)} ${formatScore(item.score)}`).join(", ") : "None"}</span>
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
        const sideClass = order.side === "BUY" ? "side-buy" : "side-sell";
        const stage = order.stage ? escapeHtml(order.stage) : order.condition ? escapeHtml(order.condition) : "-";
        const orderLabel = [order.order_type, order.time_in_force].filter(Boolean).join(" · ");
        return `<div class="summary-row">
          <div>${escapeHtml(order.ticker || "")}</div>
          <div>${escapeHtml(stage)}</div>
          <div class="qty ${sideClass}">${formatNumber(order.qty || 0, 0)}</div>
          <div>${escapeHtml(orderLabel || "-")}</div>
        </div>`;
      }),
    ].join("");
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
    : "--";
  const projectedRange = projectedValues.length
    ? `${formatPrice(Math.min(...projectedValues))} → ${formatPrice(Math.max(...projectedValues))}`
    : "--";
  const distributionRange = projectionCloses.length
    ? `${formatPrice(Math.min(...projectionCloses))} → ${formatPrice(Math.max(...projectionCloses))}`
    : "--";

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

  setSummaryTab(activeSummaryTab);
}


function summarizeEvent(event) {
  if (!event || typeof event !== "object") return String(event);
  const type = (event.type || "event").toString().toUpperCase();
  const symbol = event.symbol || "";
  if (event.type === "tick") {
    return `${type} ${symbol} @ ${formatNumber(event.price)}`;
  }
  if (event.type === "order") {
    return `${type} ${event.side || ""} ${symbol} qty ${formatNumber(event.qty)} limit ${formatNumber(
      event.limit ?? event.price_limit ?? event.price,
    )}`;
  }
  if (event.type === "trade") {
    return `${type} ${symbol} qty ${formatNumber(event.qty)} @ ${formatNumber(event.price)}`;
  }
  if (event.type === "position") {
    return `${type} ${symbol} qty ${formatNumber(event.qty)} pnl ${formatNumber(event.pnl)}`;
  }
  return `${type} ${JSON.stringify(event)}`;
}

/* ---------- Charts (Lightweight Charts) ---------- */
function makeCandleChart(container, data = [], extras = {}) {

  if (!container) return null;

  const rows = Array.isArray(data) ? data.filter(Boolean) : [];

  if (!rows.length) return null;



  const theme = {

    text: "rgba(245,247,251,0.88)",

    grid: "rgba(255,255,255,0.06)",

    up: "rgba(61,220,145,0.92)",

    down: "rgba(246,104,117,0.9)",

    volumeUp: "rgba(61,220,145,0.3)",

    volumeDown: "rgba(246,104,117,0.3)",

    accent: "rgba(91,168,247,0.65)",

  };



  const chart = LightweightCharts.createChart(container, {

    layout: {

      background: { color: "transparent" },

      textColor: theme.text,

      fontSize: 12,

      fontFamily: "Inter, 'Segoe UI', sans-serif",

    },

    rightPriceScale: { borderVisible: false, scaleMargins: { top: 0.08, bottom: 0.28 } },

    timeScale: {
      borderVisible: false,
      fixLeftEdge: true,
      timeVisible: true,
      secondsVisible: false,
    },

    grid: {

      vertLines: { color: theme.grid, style: LightweightCharts.LineStyle.Dotted },

      horzLines: { color: theme.grid, style: LightweightCharts.LineStyle.Dotted },

    },

    crosshair: {

      mode: LightweightCharts.CrosshairMode.Normal,

      vertLine: {

        color: "rgba(255,255,255,0.2)",

        labelBackgroundColor: "rgba(5,7,10,0.75)",

      },

      horzLine: {

        color: "rgba(255,255,255,0.2)",

        labelBackgroundColor: "rgba(5,7,10,0.75)",

      },

    },

  });



  const timeValue = rows.map((d) => ({

    time: isoToSec(d.timestamp),

    open: Number(d.open),

    high: Number(d.high),

    low: Number(d.low),

    close: Number(d.close),

    volume: Number(d.volume ?? 0),

  }));



  const closeSeries = timeValue.map((d) => ({ time: d.time, value: d.close }));



  const trajectory = chart.addAreaSeries({

    lineColor: theme.accent,

    topColor: "rgba(91,168,247,0.24)",

    bottomColor: "rgba(91,168,247,0.02)",

    lineWidth: 2,

    crosshairMarkerVisible: true,

  });

  trajectory.setData(closeSeries);



  const highSeries = chart.addLineSeries({

    color: "rgba(61,220,145,0.32)",

    lineWidth: 1,

    lineStyle: LightweightCharts.LineStyle.Dotted,

    priceLineVisible: false,

  });

  highSeries.setData(timeValue.map((d) => ({ time: d.time, value: d.high })));



  const lowSeries = chart.addLineSeries({

    color: "rgba(246,104,117,0.32)",

    lineWidth: 1,

    lineStyle: LightweightCharts.LineStyle.Dotted,

    priceLineVisible: false,

  });

  lowSeries.setData(timeValue.map((d) => ({ time: d.time, value: d.low })));



  const candle = chart.addCandlestickSeries({

    upColor: theme.up,

    downColor: theme.down,

    wickUpColor: theme.up,

    wickDownColor: theme.down,

    borderUpColor: theme.up,

    borderDownColor: theme.down,

    borderVisible: true,

    priceLineVisible: false,

  });

  candle.setData(timeValue.map(({ time, open, high, low, close }) => ({ time, open, high, low, close })));



  const volumeSeries = chart.addHistogramSeries({

    priceFormat: { type: "volume" },

    priceScaleId: "",

    scaleMargins: { top: 0.9, bottom: 0 },

  });

  const volumeScale = Number.isFinite(extras.volumeScale) ? extras.volumeScale : 0.28;
  volumeSeries.setData(
    timeValue.map(({ time, volume, open, close }) => ({
      time,
      value: Math.max(0, (Number(volume) || 0) * volumeScale),
      color: close >= open ? theme.volumeUp : theme.volumeDown,
    })),
  );


  const { baselinePrice, projectedPrice, currentPrice, terminalHigh, terminalLow } = extras;

  const addLine = (price, color, title) => {

    if (!Number.isFinite(price)) return;

    candle.createPriceLine({

      price,

      color,

      lineWidth: 2,

      lineStyle: LightweightCharts.LineStyle.Dashed,

      axisLabelVisible: true,

      title,

    });

  };

  addLine(currentPrice, "rgba(255,255,255,0.9)", "Spot");

  addLine(baselinePrice, "rgba(255,255,255,0.35)", "Baseline");

  addLine(projectedPrice, theme.up, "Projected");

  addLine(terminalHigh, "rgba(61,220,145,0.45)", "Ceiling");

  addLine(terminalLow, "rgba(246,104,117,0.45)", "Floor");



  const ro = new ResizeObserver(() => {

    chart.applyOptions({ width: container.clientWidth, height: container.clientHeight });

  });

  ro.observe(container);

  chart.applyOptions({ width: container.clientWidth, height: container.clientHeight });

  chart.timeScale().fitContent();

  return chart;

}



/* ---------- Renderers ---------- */
function renderImpacts(payload) {

  const impactsHost = q("#impacts");

  const generatedAt = q("#generatedAt");

  const empty = q("#impactsEmpty");

  if (!impactsHost || !generatedAt || !empty) return;



  impactsHost.innerHTML = "";

  if (!payload || !payload.impacts || payload.impacts.length === 0) {

    empty.classList.remove("is-hidden");

    generatedAt.textContent = "";

    return;

  }



  empty.classList.add("is-hidden");

  generatedAt.textContent = `Generated: ${payload.generated_at}`;



  payload.impacts.forEach((impact) => {

    const card = document.createElement("div");

    card.className = "impact-card";



    const baseline = Number(impact.baseline_price ?? impact.projection?.[0]?.close ?? 0);

    const projected = Number(impact.projected_price ?? baseline);

    const current = Number(impact.current_price ?? baseline);

    const projectionPoints = Array.isArray(impact.projection) ? impact.projection.filter(Boolean) : [];

    const lastPoint = projectionPoints.length ? projectionPoints[projectionPoints.length - 1] : null;



    const terminalHigh = Number(lastPoint?.high ?? projected);

    const terminalLow = Number(lastPoint?.low ?? projected);

    const terminalMid = Number(lastPoint?.close ?? projected);



    const projectedDelta = baseline ? ((projected - baseline) / baseline) * 100 : 0;

    const currentDelta = baseline ? ((current - baseline) / baseline) * 100 : 0;

    const terminalDelta = baseline ? ((terminalMid - baseline) / baseline) * 100 : 0;



    const hasBand = Number.isFinite(terminalLow) && Number.isFinite(terminalHigh);

    const bandLabel = hasBand ? `${formatPrice(terminalLow)} - ${formatPrice(terminalHigh)}` : "N/A";

    const bandDeltaClass = Number.isFinite(terminalDelta)

      ? terminalDelta >= 0

        ? "positive"

        : "negative"

      : "muted";

    const bandDeltaLabel = Number.isFinite(terminalDelta) ? `${formatNumber(terminalDelta)}% avg` : "N/A";



    const header = document.createElement("div");

    header.className = "impact-header";

    header.innerHTML = `
      <div class="impact-title">
        <div class="impact-heading">
          <span class="impact-ticker">${escapeHtml(impact.ticker)}</span>
          <span class="impact-name">${escapeHtml(resolveTickerName(impact.ticker))}</span>
        </div>
        <div class="impact-meta-block">
          <span class="impact-score ${impact.score >= 0 ? "positive" : "negative"}">${formatScore(impact.score)}</span>
          <span class="impact-pts">${projectionPoints.length} pts</span>
        </div>
        <div class="impact-sparkline" data-sparkline></div>
      </div>
      <div class="price-metrics">
        <div class="price-block spot">
          <label>Spot</label>
          <strong>${formatPrice(current)}</strong>
          <span class="${currentDelta >= 0 ? "positive" : "negative"}">${formatNumber(currentDelta)}%</span>
        </div>
        <div class="price-block baseline">
          <label>Baseline</label>
          <strong>${formatPrice(baseline)}</strong>
          <span class="muted">Ref</span>
        </div>
        <div class="price-block ${projectedDelta >= 0 ? "positive" : "negative"}">
          <label>Projected</label>
          <strong>${formatPrice(projected)}</strong>
          <span>${formatNumber(projectedDelta)}%</span>
        </div>
        <div class="price-block band">
          <label>Event band</label>
          <strong>${bandLabel}</strong>
          <span class="delta ${bandDeltaClass}">${bandDeltaLabel}</span>
        </div>
      </div>`;

const copyBtn = document.createElement("button");

    copyBtn.className = "bp5-button bp5-small bp5-minimal bp5-icon-clipboard";

    copyBtn.title = "Copy JSON";

    copyBtn.addEventListener("click", () => {

      navigator.clipboard.writeText(JSON.stringify(impact, null, 2));

      Toaster.push({ title: `Copied ${impact.ticker} payload`, level: "info" });

    });

    header.querySelector(".impact-meta-block")?.appendChild(copyBtn);

    const sparklineHost = header.querySelector("[data-sparkline]");
    if (sparklineHost) {
      sparklineHost.innerHTML = createSparklineSvg(projectionPoints, baseline);
    }

    card.appendChild(header);



    const chartWrap = document.createElement("div");

    chartWrap.className = "chart";

    card.appendChild(chartWrap);



    if (Array.isArray(impact.orders) && impact.orders.length) {

      const ordersWrap = document.createElement("div");

      ordersWrap.className = "orders";

      const rows = impact.orders

        .map((order) => {

          const sideClass = order.side === "BUY" ? "buy" : "sell";

          return `

          <tr>

            <td>${escapeHtml(order.agent_id)}</td>

            <td class="order-side ${sideClass}">${escapeHtml(order.side)}</td>

            <td>${Number(order.qty).toFixed(2)}</td>

            <td>${escapeHtml(order.order_type || "MKT")}</td>

            <td>${order.price_limit != null ? Number(order.price_limit).toFixed(2) : "-"}</td>

            <td>${escapeHtml(order.time_in_force || "-")}</td>

          </tr>`;

        })

        .join("");

      ordersWrap.innerHTML = `

        <h4 class="orders-title">Orders</h4>

        <table>

          <thead><tr><th>Agent</th><th>Side</th><th>Qty</th><th>Type</th><th>Limit</th><th>TIF</th></tr></thead>

          <tbody>${rows}</tbody>

        </table>`;

      card.appendChild(ordersWrap);

    }



    const preview = document.createElement("div");

    preview.className = "projection-preview";

    const previewSlice = projectionPoints.slice(0, 6);

    const suffix = projectionPoints.length > previewSlice.length ? "\n..." : "";

    preview.textContent = JSON.stringify(previewSlice, null, 2) + suffix;

    card.appendChild(preview);



    impactsHost.appendChild(card);



    if (projectionPoints.length) {

      makeCandleChart(chartWrap, projectionPoints, {
        baselinePrice: baseline,
        projectedPrice: projected,
        currentPrice: current,
        terminalHigh,
        terminalLow,
        volumeScale: 0.24,
      });

    }

  });

}



function makeFeedItem(event) {
  const el = document.createElement("div");
  el.className = "feed-item";
  const timestamp = event.timestamp || event.ts || new Date().toISOString();
  const summary = summarizeEvent(event);
  el.innerHTML = `<span class="ts">${escapeHtml(timestamp)}</span><code>${escapeHtml(summary)}</code>`;
  el.title = JSON.stringify(event, null, 2);
  return el;
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
  if (status) status.textContent = "Runningâ€¦";
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
    summaryNarrative.textContent = parts.join(" · ") || "Balanced response across agents.";
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

















