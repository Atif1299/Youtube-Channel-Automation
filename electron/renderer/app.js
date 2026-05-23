const API = window.appConfig?.apiBase || "http://127.0.0.1:8765";

let pollTimer = null;

function toast(msg, type = "info") {
  const box = document.getElementById("toast-container");
  const el = document.createElement("div");
  el.className = `toast toast-${type}`;
  el.textContent = msg;
  box.appendChild(el);
  setTimeout(() => el.remove(), 5000);
}

function elapsedSince(iso) {
  if (!iso) return "";
  const sec = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
  if (sec < 60) return `${sec}s`;
  return `${Math.floor(sec / 60)}m ${sec % 60}s`;
}

function isReady(c) {
  if (typeof c.ready === "boolean") return c.ready;
  return Boolean(c.openai && c.pexels && c.ffmpeg);
}

async function loadCheck() {
  const r = await fetch(`${API}/api/check`);
  const c = await r.json();
  const parts = [];
  parts.push(c.openai ? "OpenAI ✓" : "OpenAI ✗");
  parts.push(c.pexels ? "Pexels ✓" : "Pexels ✗");
  parts.push(c.ffmpeg ? "FFmpeg ✓" : "FFmpeg ✗");
  parts.push(`Music: ${c.music_tracks}`);
  parts.push(c.youtube_oauth ? "YouTube OAuth ✓" : "YouTube OAuth ✗");
  document.getElementById("status-bar").textContent = parts.join(" · ");

  const setup = document.getElementById("setup-panel");
  const issues = document.getElementById("setup-issues");
  if (!isReady(c)) {
    setup.classList.remove("hidden");
    const list = [];
    if (!c.openai) list.push("<li>Missing OPENAI_API_KEY in .env</li>");
    if (!c.pexels) list.push("<li>Missing PEXELS_API_KEY in .env</li>");
    if (!c.ffmpeg) list.push(`<li>FFmpeg: ${c.ffmpeg_msg || "not found"}</li>`);
    issues.innerHTML = list.join("");
  } else {
    setup.classList.add("hidden");
  }
  return c;
}

function _saveVideoState() {
  const state = {};
  document.querySelectorAll("video[data-job-id]").forEach((v) => {
    state[v.dataset.jobId] = { time: v.currentTime, paused: v.paused };
  });
  return state;
}

function _restoreVideoState(state) {
  document.querySelectorAll("video[data-job-id]").forEach((v) => {
    const s = state[v.dataset.jobId];
    if (!s) return;
    v.currentTime = s.time;
    if (!s.paused) v.play().catch(() => {});
  });
}

function progressBar(pct) {
  const p = Math.min(100, Math.max(0, pct || 0));
  return `<div class="progress"><div class="progress-fill" style="width:${p}%"></div></div>`;
}

async function loadJobs() {
  const r = await fetch(`${API}/api/jobs`);
  const jobs = await r.json();
  const el = document.getElementById("jobs");
  if (!jobs.length) {
    el.innerHTML = "<p>No jobs yet.</p>";
    schedulePoll(jobs);
    return;
  }
  const videoState = _saveVideoState();
  el.innerHTML = jobs
    .map((j) => {
      const canPlay =
        j.video_path &&
        ["pending_review", "approved", "published", "scheduled"].includes(j.status);
      const video = canPlay
        ? `<video controls preload="metadata" data-job-id="${j.id}" src="${API}/api/jobs/${j.id}/video?v=${encodeURIComponent(j.updated_at || "")}"></video>`
        : "";
      const actions = [];
      if (j.status === "pending_review") {
        actions.push(`<button onclick="approve('${j.id}')">Approve</button>`);
        actions.push(`<button class="danger" onclick="reject('${j.id}')">Reject</button>`);
      }
      if (j.status === "approved") {
        actions.push(`<button onclick="publishNow('${j.id}')">Publish now</button>`);
        actions.push(
          `<button class="secondary" onclick="publishScheduled('${j.id}')">Schedule publish</button>`
        );
      }
      let stageHtml = "";
      if (j.status === "generating" || j.status === "uploading") {
        stageHtml = `
          <div class="stage-info">
            <span class="spinner"></span>
            <span>${j.stage_message || j.status}…</span>
            <span class="meta">(${elapsedSince(j.updated_at)} elapsed)</span>
          </div>
          ${progressBar(j.progress_pct)}`;
      } else if (j.stage_message && j.status === "failed") {
        stageHtml = `<div class="meta error-text">${j.stage_message}</div>`;
      }
      if (j.error) {
        stageHtml += `<div class="meta error-text">Error: ${j.error}</div>`;
      }
      if (j.youtube_video_id) {
        stageHtml += `<div class="meta">YouTube ID: ${j.youtube_video_id}</div>`;
      }
      return `
        <div class="job">
          <div class="job-header">
            <span class="job-id">${j.id}</span>
            <span class="badge ${j.status}">${j.status}</span>
          </div>
          <div class="meta">${j.topic || ""}</div>
          ${stageHtml}
          ${video}
          <div class="job-actions">${actions.join("")}</div>
        </div>`;
    })
    .join("");
  _restoreVideoState(videoState);
  schedulePoll(jobs);
}

function schedulePoll(jobs) {
  if (pollTimer) clearInterval(pollTimer);
  const active = jobs.some((j) => j.status === "generating" || j.status === "uploading");
  const interval = active ? 5000 : 15000;
  pollTimer = setInterval(() => {
    const playing = document.querySelector("video[data-job-id]");
    if (playing && !playing.paused && playing.currentTime > 0 && !playing.ended) return;
    loadCheck();
    loadJobs();
  }, interval);
}

document.getElementById("btn-quick-test").onclick = async () => {
  document.getElementById("duration").value = "1";
  document.getElementById("audio").value = "coach_voice";
  if (!document.getElementById("topic").value.trim()) {
    document.getElementById("topic").value = "1 min desk stretch quick test";
  }
  await startGenerate();
};

async function startGenerate() {
  const topic = document.getElementById("topic").value;
  const duration = parseInt(document.getElementById("duration").value, 10);
  const audio_mode = document.getElementById("audio").value;
  const btn = document.getElementById("btn-generate");
  btn.disabled = true;
  try {
    const r = await fetch(`${API}/api/generate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ topic, duration, audio_mode }),
    });
    const d = await r.json();
    if (!r.ok) throw new Error(d.detail || "Generate failed");
    toast(
      duration === 1
        ? "Quick test started — watch progress below."
        : "Generation started — watch progress below.",
      "success"
    );
    loadJobs();
  } catch (err) {
    toast(err.message, "error");
  } finally {
    btn.disabled = false;
  }
}

document.getElementById("generate-form").onsubmit = async (e) => {
  e.preventDefault();
  await startGenerate();
};

document.getElementById("btn-refresh").onclick = () => {
  loadCheck();
  loadJobs();
};

document.getElementById("btn-research").onclick = async () => {
  try {
    const r = await fetch(`${API}/api/research`, { method: "POST" });
    const d = await r.json();
    if (!r.ok) throw new Error(d.detail || "Failed");
    toast("Competitor cache updated", "success");
  } catch (err) {
    toast(err.message, "error");
  }
};

document.getElementById("btn-auth").onclick = async () => {
  toast("Complete sign-in in the browser window…", "info");
  try {
    const r = await fetch(`${API}/api/auth-youtube`, { method: "POST" });
    if (!r.ok) {
      const d = await r.json();
      throw new Error(d.detail || "Auth failed");
    }
    toast("YouTube OAuth saved.", "success");
    loadCheck();
  } catch (err) {
    toast(err.message, "error");
  }
};

window.approve = async (id) => {
  const r = await fetch(`${API}/api/jobs/${id}/approve`, { method: "POST" });
  if (!r.ok) toast((await r.json()).detail, "error");
  else toast("Approved — metadata generated.", "success");
  loadJobs();
};

window.reject = async (id) => {
  const r = await fetch(`${API}/api/jobs/${id}/reject`, { method: "POST" });
  if (!r.ok) toast((await r.json()).detail, "error");
  else toast("Rejected.", "info");
  loadJobs();
};

window.publishNow = async (id) => {
  if (!confirm("Publish this video to YouTube now?")) return;
  try {
    const r = await fetch(`${API}/api/jobs/${id}/publish`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    });
    const d = await r.json();
    if (!r.ok) throw new Error(d.detail || "Publish failed");
    toast("Published! Video ID: " + d.youtube_video_id, "success");
    loadJobs();
  } catch (err) {
    toast(err.message, "error");
  }
};

window.publishScheduled = async (id) => {
  const raw = prompt(
    "Schedule publish (ISO 8601, e.g. 2026-06-01T18:00:00+05:00):",
    ""
  );
  if (!raw) return;
  try {
    const r = await fetch(`${API}/api/jobs/${id}/publish`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ publish_at: raw }),
    });
    const d = await r.json();
    if (!r.ok) throw new Error(d.detail || "Schedule failed");
    toast("Scheduled! Video ID: " + d.youtube_video_id, "success");
    loadJobs();
  } catch (err) {
    toast(err.message, "error");
  }
};

loadCheck();
loadJobs();

