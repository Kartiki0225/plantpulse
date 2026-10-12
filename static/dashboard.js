// Loads the dashboard numbers from the REST API and draws them.

const kpis = document.getElementById("kpis");
const query = `?from=${kpis.dataset.from}&to=${kpis.dataset.to}`;

const percent = (value) => (value * 100).toFixed(1) + "%";
const number = (value) => Number(value || 0).toLocaleString("en-IN");

// Green from 85%, amber from 60%, red below that.
function level(oee) {
  if (oee >= 0.85) return "good";
  if (oee >= 0.6) return "ok";
  return "poor";
}

async function getJson(path) {
  const response = await fetch(path + query);
  return response.json();
}

async function loadDashboard() {
  const [overall, machines, daily, reasons] = await Promise.all([
    getJson("/api/oee/overall"),
    getJson("/api/oee/machines"),
    getJson("/api/oee/daily"),
    getJson("/api/downtime/reasons"),
  ]);

  if (overall.logs === 0) {
    document.getElementById("empty").hidden = false;
    return;
  }

  showKpis(overall);
  showMachines(machines);
  drawDowntime(reasons);
  drawTrend(daily);
}

function showKpis(overall) {
  const oee = document.getElementById("kpi-oee");
  oee.textContent = percent(overall.oee);
  oee.className = level(overall.oee);

  document.getElementById("kpi-availability").textContent = percent(overall.availability);
  document.getElementById("kpi-performance").textContent = percent(overall.performance);
  document.getElementById("kpi-quality").textContent = percent(overall.quality);

  const hoursLost = (overall.downtime_minutes / 60).toFixed(1);
  document.getElementById("kpi-logs").textContent = `${number(overall.logs)} shift logs`;
  document.getElementById("kpi-downtime").textContent = `${hoursLost} hours of downtime`;
  document.getElementById("kpi-parts").textContent = `${number(overall.total_parts)} parts made`;
  document.getElementById("kpi-rejected").textContent = `${number(overall.rejected_parts)} parts rejected`;
}

function showMachines(machines) {
  const rows = machines.map((machine) => `
    <tr>
      <td>${machine.machine_name}</td>
      <td class="muted">${machine.line}</td>
      <td class="num">${percent(machine.availability)}</td>
      <td class="num">${percent(machine.performance)}</td>
      <td class="num">${percent(machine.quality)}</td>
      <td><div class="oee-cell">
        <div class="bar"><span class="${level(machine.oee)}" style="width:${Math.min(machine.oee, 1) * 100}%"></span></div>
        <b>${percent(machine.oee)}</b></div>
      </td>
    </tr>`);
  document.getElementById("machine-rows").innerHTML = rows.join("");
}

Chart.defaults.font.family = getComputedStyle(document.body).fontFamily;
Chart.defaults.color = "#6b6a65";

function drawDowntime(reasons) {
  new Chart(document.getElementById("downtime-chart"), {
    type: "bar",
    data: {
      labels: reasons.map((reason) => reason.reason),
      datasets: [{
        label: "Hours lost",
        data: reasons.map((reason) => +(reason.minutes / 60).toFixed(1)),
        backgroundColor: "#c2410c",
        borderRadius: 4,
      }],
    },
    options: {
      indexAxis: "y", // horizontal bars, biggest cause on top
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: { x: { title: { display: true, text: "Hours lost" }, grid: { color: "#eceae4" } }, y: { grid: { display: false } } },
    },
  });
}

function drawTrend(daily) {
  new Chart(document.getElementById("trend-chart"), {
    type: "line",
    data: {
      labels: daily.map((day) => day.log_date.slice(5)), // MM-DD
      datasets: [{
        label: "OEE %",
        data: daily.map((day) => +(day.oee * 100).toFixed(1)),
        borderColor: "#0f766e",
        backgroundColor: "rgba(15, 118, 110, 0.08)",
        fill: true,
        tension: 0.3,
        pointRadius: 3,
      }],
    },
    options: {
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        y: { suggestedMin: 40, suggestedMax: 100, ticks: { callback: (value) => value + "%" }, grid: { color: "#eceae4" } },
        x: { grid: { display: false } },
      },
    },
  });
}

loadDashboard();
