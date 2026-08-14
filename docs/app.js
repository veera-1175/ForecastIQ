let bundle;
let chart;

async function boot() {
  const res = await fetch("./forecast_bundle.json");
  bundle = await res.json();
  renderPipeline();
  renderKpis();
  fillSelect();
  fillTable();
  seedChat();
  renderSku(bundle.forecasts[0].sku_id);
  document.getElementById("skuSelect").addEventListener("change", (e) => renderSku(e.target.value));
  document.getElementById("chatForm").addEventListener("submit", onChat);
}

function renderPipeline() {
  const el = document.getElementById("pipeline");
  const steps = bundle.pipeline.steps;
  el.innerHTML = steps
    .map(
      (step, i) => `
      <div class="pipe-step ${step.status}">
        <div class="pipe-dot"></div>
        <div><strong>${step.label}</strong><p>${step.detail}</p></div>
      </div>
      ${i < steps.length - 1 ? '<div class="pipe-line"></div>' : ""}`
    )
    .join("");
}

function renderKpis() {
  document.getElementById("kpis").innerHTML = bundle.kpis
    .map(
      (k) => `
    <article class="kpi" title="${k.hint}">
      <p class="kpi-label">${k.label}</p>
      <p class="kpi-value">${k.value}</p>
      <p class="kpi-hint">${k.hint}</p>
    </article>`
    )
    .join("");
}

function skuMap() {
  const m = {};
  for (const f of bundle.forecasts) m[f.sku_id] = f;
  return m;
}

function fillSelect() {
  document.getElementById("skuSelect").innerHTML = bundle.forecasts
    .map((f) => `<option value="${f.sku_id}">${f.sku_name}</option>`)
    .join("");
}

function fillTable() {
  const table = document.getElementById("skuTable");
  table.innerHTML = bundle.forecasts
    .map(
      (f) => `
      <tr data-sku="${f.sku_id}">
        <td><strong>${f.sku_name}</strong><br/><span style="color:#5c6b63">${f.sku_id}</span></td>
        <td>${f.category}</td>
        <td>${f.forecast_total_units.toFixed(0)}</td>
        <td>₹${f.forecast_revenue.toLocaleString("en-IN", { maximumFractionDigits: 0 })}</td>
        <td>${f.mae}</td>
        <td>${f.insight}</td>
      </tr>`
    )
    .join("");
  table.querySelectorAll("tr").forEach((tr) => {
    tr.addEventListener("click", () => {
      document.getElementById("skuSelect").value = tr.dataset.sku;
      renderSku(tr.dataset.sku);
    });
  });
}

function avg(arr) {
  return arr.reduce((a, b) => a + b, 0) / Math.max(arr.length, 1);
}

function renderSku(skuId) {
  const f = skuMap()[skuId];
  if (!f) return;
  const histLabels = f.history.map((h) => h.date);
  const histVals = f.history.map((h) => h.units);
  const futLabels = f.forecast.map((h) => h.date);
  const futVals = f.forecast.map((h) => h.units);
  const labels = [...histLabels, ...futLabels];
  const actual = [...histVals, ...Array(futVals.length).fill(null)];
  const forecast = [...Array(histVals.length - 1).fill(null), histVals[histVals.length - 1], ...futVals];

  const ctx = document.getElementById("demandChart");
  if (chart) chart.destroy();
  chart = new Chart(ctx, {
    type: "line",
    data: {
      labels,
      datasets: [
        { label: "Actual", data: actual, borderColor: "#1f6f54", backgroundColor: "rgba(31,111,84,0.12)", tension: 0.25, pointRadius: 0, borderWidth: 2 },
        { label: "Forecast", data: forecast, borderColor: "#c45c26", backgroundColor: "rgba(196,92,38,0.10)", borderDash: [6, 4], tension: 0.25, pointRadius: 0, borderWidth: 2 },
      ],
    },
    options: {
      responsive: true,
      plugins: { legend: { display: false } },
      scales: {
        x: { ticks: { maxTicksLimit: 8, color: "#5c6b63", callback(val) { return this.getLabelForValue(val)?.slice(5) || ""; } }, grid: { color: "rgba(20,32,27,0.05)" } },
        y: { ticks: { color: "#5c6b63" }, grid: { color: "rgba(20,32,27,0.06)" }, title: { display: true, text: "Units / day", color: "#5c6b63" } },
      },
    },
  });

  const first = avg(futVals.slice(0, 7));
  const second = avg(futVals.slice(7));
  const delta = ((second - first) / Math.max(first, 1)) * 100;
  const dir = delta > 5 ? "up" : delta < -5 ? "down" : "flat";
  document.getElementById("chartMeaning").innerHTML = `<strong>${f.sku_name}</strong> — ${f.insight}
    Week-2 vs week-1 forecast is <strong>${dir}</strong> (${delta >= 0 ? "+" : ""}${delta.toFixed(1)}%).
    Typical miss ≈ <strong>${f.mae}</strong> units/day (MAE).`;
  document.querySelectorAll("#skuTable tr").forEach((r) => r.classList.toggle("active", r.dataset.sku === skuId));
}

function addBubble(text, who, meta = "") {
  const el = document.createElement("div");
  el.className = `bubble ${who}`;
  el.textContent = text;
  if (meta) {
    const m = document.createElement("span");
    m.className = "meta";
    m.textContent = meta;
    el.appendChild(m);
  }
  const chatLog = document.getElementById("chatLog");
  chatLog.appendChild(el);
  chatLog.scrollTop = chatLog.scrollHeight;
}

function answerQuestion(question) {
  const q = question.toLowerCase();
  const forecasts = bundle.forecasts;
  if (["restock", "stock", "inventory", "reorder"].some((k) => q.includes(k))) {
    const ranked = [...forecasts].sort((a, b) => b.forecast_total_units - a.forecast_total_units).slice(0, 3);
    return (
      "Based on the 14-day TensorFlow forecast, prioritize restock for:\n\n" +
      ranked.map((r) => `• ${r.sku_name} — ~${r.forecast_total_units.toFixed(0)} units (${r.insight})`).join("\n") +
      `\n\nModel average error (MAE) is ${bundle.summary.overall_mae} units/day — use that as a safety buffer.`
    );
  }
  if (["revenue", "money", "top sku", "highest"].some((k) => q.includes(k))) {
    const top = forecasts[0];
    const total = forecasts.reduce((s, f) => s + f.forecast_revenue, 0);
    return `${top.sku_name} leads 14-day revenue (~₹${top.forecast_revenue.toLocaleString("en-IN", { maximumFractionDigits: 0 })}). All-SKU forecast revenue ~₹${total.toLocaleString("en-IN", { maximumFractionDigits: 0 })}.\n\n${top.insight}`;
  }
  if (["mae", "rmse", "accuracy", "error", "reliable"].some((k) => q.includes(k))) {
    return `Holdout evaluation: MAE ${bundle.summary.overall_mae}, RMSE ${bundle.summary.overall_rmse} (units/day). Lower is better. Treat forecasts as planning signals, not guarantees.`;
  }
  for (const cat of ["Dairy", "Beverages", "Bakery", "Grocery", "Snacks"]) {
    if (q.includes(cat.toLowerCase())) {
      const subset = forecasts.filter((f) => f.category === cat);
      const totalU = subset.reduce((s, f) => s + f.forecast_total_units, 0);
      return `${cat} outlook: ~${totalU.toFixed(0)} units across ${subset.length} SKUs (${subset.map((f) => f.sku_name).join(", ")}) in the next 14 days.`;
    }
  }
  return (
    "Planning brief from Spark → TensorFlow → LangChain context:\n\n" +
    forecasts
      .slice(0, 3)
      .map((f) => `• ${f.sku_name}: ${f.forecast_total_units.toFixed(0)} units · ₹${f.forecast_revenue.toLocaleString("en-IN", { maximumFractionDigits: 0 })} · ${f.insight}`)
      .join("\n")
  );
}

function seedChat() {
  addBubble(
    "Hi — I’m your demand insight agent. Ask about restock, revenue, categories, or model accuracy. Answers are grounded in the Spark → TensorFlow forecast.",
    "bot",
    "ready"
  );
  const tips = [
    "Which SKUs should we restock first?",
    "What is the 14-day revenue outlook?",
    "How accurate is the model (MAE/RMSE)?",
    "How is Dairy category demand looking?",
  ];
  const suggestions = document.getElementById("suggestions");
  suggestions.innerHTML = tips.map((t) => `<button type="button">${t}</button>`).join("");
  suggestions.querySelectorAll("button").forEach((b) => {
    b.addEventListener("click", () => {
      document.getElementById("chatInput").value = b.textContent;
      document.getElementById("chatForm").requestSubmit();
    });
  });
}

function onChat(e) {
  e.preventDefault();
  const input = document.getElementById("chatInput");
  const q = input.value.trim();
  if (!q) return;
  addBubble(q, "user");
  input.value = "";
  addBubble(answerQuestion(q), "bot", "forecast-grounded");
}

boot().catch((err) => {
  document.body.insertAdjacentHTML("afterbegin", `<p style="color:crimson;padding:12px">Failed to load forecast bundle: ${err}</p>`);
});
