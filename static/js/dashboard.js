// ── Toast ──────────────────────────────────────────────────────────────────────
const toastContainer = document.createElement("div");
toastContainer.className = "toast-container";
document.body.appendChild(toastContainer);

function showToast(msg, type = "success") {
  const t = document.createElement("div");
  t.className = `toast toast-${type}`;
  t.textContent = msg;
  toastContainer.appendChild(t);
  setTimeout(() => t.remove(), 3200);
}

// ── API helpers ────────────────────────────────────────────────────────────────
async function apiPost(url, data) {
  const r = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  return r.json();
}

// ── Modal helpers ──────────────────────────────────────────────────────────────
function openModal(id) {
  document.getElementById(id)?.classList.add("open");
}
function closeModal(id) {
  document.getElementById(id)?.classList.remove("open");
}

// Close modal on bg click
document.querySelectorAll(".modal-bg").forEach((bg) => {
  bg.addEventListener("click", (e) => {
    if (e.target === bg) bg.classList.remove("open");
  });
});

// ── Withdrawal Actions ─────────────────────────────────────────────────────────
async function approveWithdrawal(id) {
  if (!confirm(`Approve withdrawal #${id}?`)) return;
  const r = await apiPost(`/api/withdrawal/${id}/approve`, {});
  if (r.success) {
    showToast(`✅ Withdrawal #${id} approved!`);
    setTimeout(() => location.reload(), 1000);
  } else {
    showToast("❌ Failed to approve.", "error");
  }
}

async function rejectWithdrawal(id) {
  const reason = prompt("Rejection reason:");
  if (!reason) return;
  const r = await apiPost(`/api/withdrawal/${id}/reject`, { reason });
  if (r.success) {
    showToast(`✅ Withdrawal #${id} rejected.`);
    setTimeout(() => location.reload(), 1000);
  } else {
    showToast("❌ Failed to reject.", "error");
  }
}

// ── Balance Edit ───────────────────────────────────────────────────────────────
async function editBalance(userId, guildId, currentBal) {
  const amount = prompt(`New balance for user ${userId}:`, currentBal);
  if (amount === null || isNaN(+amount)) return;
  const r = await apiPost(`/api/user/${userId}/balance`, {
    amount: +amount, guild_id: guildId, hold: false
  });
  if (r.success) {
    showToast("✅ Balance updated!");
    setTimeout(() => location.reload(), 800);
  } else {
    showToast("❌ Failed.", "error");
  }
}

// ── Settings task save ─────────────────────────────────────────────────────────
async function saveTask(guildId) {
  const task = document.getElementById(`task-${guildId}`)?.value;
  if (!task) return;
  const r = await apiPost("/api/settings/task", { guild_id: guildId, task });
  if (r.success) showToast("✅ Task updated!");
  else showToast("❌ Failed.", "error");
}

// ── Charts (simple canvas sparkline) ──────────────────────────────────────────
async function loadChart() {
  const canvas = document.getElementById("txChart");
  if (!canvas) return;
  const data = await fetch("/api/stats").then((r) => r.json()).catch(() => []);
  if (!data.length) return;

  const ctx = canvas.getContext("2d");
  const W = canvas.width = canvas.offsetWidth;
  const H = canvas.height = 120;
  const values = data.map((d) => d.total || 0).reverse();
  const labels = data.map((d) => d.day?.slice(5) || "").reverse();
  const max = Math.max(...values, 1);

  // Background gradient
  const grad = ctx.createLinearGradient(0, 0, 0, H);
  grad.addColorStop(0, "rgba(88,101,242,0.3)");
  grad.addColorStop(1, "rgba(88,101,242,0)");

  const pts = values.map((v, i) => ({
    x: (i / (values.length - 1)) * (W - 40) + 20,
    y: H - 20 - ((v / max) * (H - 40)),
  }));

  // Fill
  ctx.beginPath();
  ctx.moveTo(pts[0].x, H - 20);
  pts.forEach((p) => ctx.lineTo(p.x, p.y));
  ctx.lineTo(pts[pts.length - 1].x, H - 20);
  ctx.closePath();
  ctx.fillStyle = grad;
  ctx.fill();

  // Line
  ctx.beginPath();
  ctx.moveTo(pts[0].x, pts[0].y);
  pts.forEach((p) => ctx.lineTo(p.x, p.y));
  ctx.strokeStyle = "#5865f2";
  ctx.lineWidth = 2.5;
  ctx.lineJoin = "round";
  ctx.stroke();

  // Dots
  pts.forEach((p) => {
    ctx.beginPath();
    ctx.arc(p.x, p.y, 4, 0, Math.PI * 2);
    ctx.fillStyle = "#7983f5";
    ctx.fill();
  });

  // Labels
  labels.forEach((l, i) => {
    ctx.fillStyle = "rgba(255,255,255,0.3)";
    ctx.font = "10px DM Sans";
    ctx.textAlign = "center";
    ctx.fillText(l, pts[i].x, H - 4);
  });
}

document.addEventListener("DOMContentLoaded", () => {
  loadChart();
});
