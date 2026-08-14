const bundle = window.__FORECAST_BUNDLE__;
const select = document.getElementById("skuSelect");
const table = document.getElementById("skuTable");
const meaning = document.getElementById("chartMeaning");
const chatLog = document.getElementById("chatLog");
const suggestions = document.getElementById("suggestions");
const form = document.getElementById("chatForm");
const input = document.getElementById("chatInput");

let chart;

function skuMap() {
  const m = {};
  for (const f of bundle.forecasts) m[f.sku_id] = f;
  return m;
}

function fillSelect() {
  select.innerHTML = bundle.forecasts
    .map((f) => `<option value="${f.sku_id}">${f.sku_name}</option>`)
    .join("");
}

function fillTable() {
  table.innerHTML = bundle.forecasts
    .map(
      (f) => `
      <tr data-sku="${f.sku_id}">
        <td><strong>${f.sku_name}</strong><br/><span style="color:#5c6b63">${f.sku_id}</span></td>
        <td>${f.category}</td>
        <td>${f.forecast_total_units.toFixed(0)}</td>
        <td>$${f.forecast_revenue.toLocaleString(undefined, { maximumFractionDigits: 0 })}</td>
        <td>${f.mae}</td>
        <td>${f.insight}</td>
      </tr>`
    )
    .join("");

  table.querySelectorAll("tr").forEach((tr) => {
    tr.addEventListener("click", () => {
      select.value = tr.dataset.sku;
      renderSku(tr.dataset.sku);
      table.querySelectorAll("tr").forEach((r) => r.classList.remove("active"));
      tr.classList.add("active");
    });
  });
}

function renderSku(skuId) {
  const f = skuMap()[skuId];
  if (!f) return;

  const histLabels = f.history.map((h) => h.date);
  const histVals = f.history.map((h) => h.units);
  const futLabels = f.forecast.map((h) => h.date);
  const futVals = f.forecast.map((h) => h.units);

  // bridge: last actual point connects visually
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
        {
          label: "Actual",
          data: actual,
          borderColor: "#1f6f54",
          backgroundColor: "rgba(31,111,84,0.12)",
          tension: 0.25,
          pointRadius: 0,
          borderWidth: 2,
          spanGaps: false,
        },
        {
          label: "Forecast",
          data: forecast,
          borderColor: "#c45c26",
          backgroundColor: "rgba(196,92,38,0.10)",
          borderDash: [6, 4],
          tension: 0.25,
          pointRadius: 0,
          borderWidth: 2,
          spanGaps: false,
        },
      ],
    },
    options: {
      responsive: true,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: (c) => `${c.dataset.label}: ${Number(c.raw).toFixed(1)} units`,
          },
        },
      },
      scales: {
        x: {
          ticks: {
            maxTicksLimit: 8,
            color: "#5c6b63",
            callback(val, i) {
              const label = this.getLabelForValue(val);
              return label?.slice(5) || "";
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
  meaning.innerHTML = `<strong>${f.sku_name}</strong> — ${f.insight}
    Week-2 vs week-1 forecast is <strong>${dir}</strong> (${delta >= 0 ? "+" : ""}${delta.toFixed(1)}%).
    Typical miss ≈ <strong>${f.mae}</strong> units/day (MAE). Use this for reorder buffers, not exact cartons.`;

  table.querySelectorAll("tr").forEach((r) => {
    r.classList.toggle("active", r.dataset.sku === skuId);
  });
}

function avg(arr) {
  return arr.reduce((a, b) => a + b, 0) / Math.max(arr.length, 1);
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
  chatLog.appendChild(el);
  chatLog.scrollTop = chatLog.scrollHeight;
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
  suggestions.innerHTML = tips
    .map((t) => `<button type="button" data-q="${t.replaceAll('"', "&quot;")}">${t}</button>`)
    .join("");
  suggestions.querySelectorAll("button").forEach((b) => {
    b.addEventListener("click", () => {
      input.value = b.dataset.q;
      form.requestSubmit();
    });
  });
}

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const q = input.value.trim();
  if (!q) return;
  addBubble(q, "user");
  input.value = "";
  const thinking = document.createElement("div");
  thinking.className = "bubble bot";
  thinking.textContent = "Thinking with forecast context…";
  chatLog.appendChild(thinking);
  chatLog.scrollTop = chatLog.scrollHeight;

  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question: q }),
    });
    const data = await res.json();
    thinking.remove();
    addBubble(data.answer, "bot", data.backend);
  } catch (err) {
    thinking.textContent = "Could not reach the agent. Try again.";
  }
});

select.addEventListener("change", () => renderSku(select.value));

fillSelect();
fillTable();
seedChat();
renderSku(bundle.forecasts[0].sku_id);
