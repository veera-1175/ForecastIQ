let bundle = window.__FORECAST_BUNDLE__;
let chart;

function apiBase() {
  return (window.FORECASTIQ_API || "").replace(/\/$/, "");
}

function apiUrl(path) {
  const base = apiBase();
  return base ? `${base}${path}` : path;
}

function boot() {
  const template = document.getElementById("templateLink");
  if (template) template.href = apiUrl("/api/template.csv");

  renderAll();
  document.getElementById("skuSelect").addEventListener("change", (e) => renderSku(e.target.value));
  document.getElementById("chatForm").addEventListener("submit", onChat);
  document.getElementById("uploadBtn")?.addEventListener("click", onUpload);
  document.getElementById("resetBtn")?.addEventListener("click", onReset);
  seedChat();
}

function renderAll() {
  renderPipeline();
  renderKpis();
  fillSelect();
  fillTable();
  if (bundle.forecasts?.length) renderSku(bundle.forecasts[0].sku_id);
}

function renderPipeline() {
  const el = document.querySelector(".pipeline") || document.getElementById("pipeline");
  if (!el || !bundle.pipeline) return;
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
  const root = document.querySelector(".kpis") || document.getElementById("kpis");
  if (!root) return;
  root.innerHTML = bundle.kpis
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
        x: {
          ticks: {
            maxTicksLimit: 8,
            color: "#5c6b63",
            callback(val) {
              return this.getLabelForValue(val)?.slice(5) || "";
            },
          },
          grid: { color: "rgba(20,32,27,0.05)" },
        },
        y: {
          ticks: { color: "#5c6b63" },
          grid: { color: "rgba(20,32,27,0.06)" },
          title: { display: true, text: "Units / day", color: "#5c6b63" },
        },
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

function setStatus(msg, kind = "") {
  const el = document.getElementById("uploadStatus");
  if (!el) return;
  el.textContent = msg;
  el.className = `upload-status ${kind}`.trim();
}

async function onUpload() {
  const input = document.getElementById("csvFile");
  const btn = document.getElementById("uploadBtn");
  if (!input?.files?.length) {
    setStatus("Choose a CSV file first.", "err");
    return;
  }
  const fd = new FormData();
  fd.append("file", input.files[0]);
  btn.disabled = true;
  setStatus("Uploading and running Spark ETL → TensorFlow… this can take ~1 minute.");
  try {
    const res = await fetch(apiUrl("/api/upload"), { method: "POST", body: fd, headers: { "ngrok-skip-browser-warning": "1" } });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Upload failed");
    bundle = data.bundle;
    window.__FORECAST_BUNDLE__ = bundle;
    renderAll();
    setStatus(
      `Done — ${data.ingest.rows} rows, ${data.ingest.skus} SKUs (${data.ingest.date_min} → ${data.ingest.date_max}). Forecast refreshed.`,
      "ok"
    );
    addBubble("Your CSV was ingested. Ask me anything about the new forecast.", "bot", "upload");
  } catch (err) {
    setStatus(String(err.message || err), "err");
  } finally {
    btn.disabled = false;
  }
}

async function onReset() {
  const btn = document.getElementById("resetBtn");
  btn.disabled = true;
  setStatus("Restoring sample dataset and re-running pipeline…");
  try {
    const res = await fetch(apiUrl("/api/reset-sample"), { method: "POST", headers: { "ngrok-skip-browser-warning": "1" } });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Reset failed");
    bundle = data.bundle;
    window.__FORECAST_BUNDLE__ = bundle;
    renderAll();
    setStatus("Sample dataset restored.", "ok");
  } catch (err) {
    setStatus(String(err.message || err), "err");
  } finally {
    btn.disabled = false;
  }
}

function answerQuestionLocal(question) {
  const q = question.toLowerCase();
  const forecasts = bundle.forecasts;
  if (["restock", "stock", "inventory", "reorder"].some((k) => q.includes(k))) {
    const ranked = [...forecasts].sort((a, b) => b.forecast_total_units - a.forecast_total_units).slice(0, 3);
    return (
      "Based on the 14-day TensorFlow forecast, prioritize restock for:\n\n" +
      ranked.map((r) => `• ${r.sku_name} — ~${r.forecast_total_units.toFixed(0)} units (${r.insight})`).join("\n") +
      `\n\nModel average error (MAE) is ${bundle.summary.overall_mae} units/day.`
    );
  }
  if (["revenue", "money", "rupee", "inr", "top sku", "highest"].some((k) => q.includes(k))) {
    const top = forecasts[0];
    const total = forecasts.reduce((s, f) => s + f.forecast_revenue, 0);
    return `${top.sku_name} leads 14-day revenue (~₹${top.forecast_revenue.toLocaleString("en-IN", { maximumFractionDigits: 0 })}). All-SKU ~₹${total.toLocaleString("en-IN", { maximumFractionDigits: 0 })}.\n\n${top.insight}`;
  }
  if (["mae", "rmse", "accuracy", "error"].some((k) => q.includes(k))) {
    return `Holdout evaluation: MAE ${bundle.summary.overall_mae}, RMSE ${bundle.summary.overall_rmse} (units/day).`;
  }
  return (
    "Planning brief:\n\n" +
    forecasts
      .slice(0, 3)
      .map((f) => `• ${f.sku_name}: ${f.forecast_total_units.toFixed(0)} units · ₹${f.forecast_revenue.toLocaleString("en-IN", { maximumFractionDigits: 0 })}`)
      .join("\n")
  );
}

async function askAgent(question) {
  try {
    const res = await fetch(apiUrl("/api/chat"), {
      method: "POST",
      headers: { "Content-Type": "application/json", "ngrok-skip-browser-warning": "1" },
      body: JSON.stringify({ question }),
    });
    if (!res.ok) throw new Error(`API ${res.status}`);
    const data = await res.json();
    return { answer: data.answer, meta: data.backend || "langchain-groq" };
  } catch {
    return { answer: answerQuestionLocal(question), meta: "local-fallback" };
  }
}

function seedChat() {
  const log = document.getElementById("chatLog");
  if (log) log.innerHTML = "";
  addBubble(
    "Hi — I’m your demand insight agent. Upload your own sales CSV above, or explore the sample. Ask any planning question in plain English.",
    "bot",
    "ready"
  );
  const tips = [
    "Which SKUs should we restock first?",
    "What is the 14-day revenue outlook in rupees?",
    "How accurate is the model (MAE/RMSE)?",
    "If Dairy softens, what should we do?",
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

async function onChat(e) {
  e.preventDefault();
  const input = document.getElementById("chatInput");
  const q = input.value.trim();
  if (!q) return;
  addBubble(q, "user");
  input.value = "";
  const thinking = document.createElement("div");
  thinking.className = "bubble bot";
  thinking.textContent = "Thinking with forecast context…";
  document.getElementById("chatLog").appendChild(thinking);
  const { answer, meta } = await askAgent(q);
  thinking.remove();
  addBubble(answer, "bot", meta);
}

if (bundle) {
  boot();
} else {
  fetch("./forecast_bundle.json")
    .then((r) => r.json())
    .then((b) => {
      bundle = b;
      window.__FORECAST_BUNDLE__ = b;
      boot();
    })
    .catch((err) => {
      document.body.insertAdjacentHTML("afterbegin", `<p style="color:crimson;padding:12px">Failed to load forecast: ${err}</p>`);
    });
}
