const API = "";

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
}

function _saveVideoState() {
  const state = {};
  document.querySelectorAll("video[data-job-id]").forEach((v) => {
    state[v.dataset.jobId] = {
      time: v.currentTime,
      paused: v.paused,
    };
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

async function loadJobs() {
  const r = await fetch(`${API}/api/jobs`);
  const jobs = await r.json();
  const el = document.getElementById("jobs");
  if (!jobs.length) {
    el.innerHTML = "<p>No jobs yet.</p>";
    return;
  }
  const videoState = _saveVideoState();
  el.innerHTML = jobs
    .map((j) => {
      const canPlay = j.video_path && ["pending_review", "approved", "published", "scheduled"].includes(j.status);
      const video = canPlay
        ? `<video controls preload="metadata" data-job-id="${j.id}" src="/api/jobs/${j.id}/video?v=${j.updated_at || ""}"></video>`
        : "";
      const actions = [];
      if (j.status === "pending_review") {
        actions.push(`<button onclick="approve('${j.id}')">Approve</button>`);
        actions.push(`<button class="danger" onclick="reject('${j.id}')">Reject</button>`);
      }
      if (j.status === "approved") {
        actions.push(`<button onclick="publish('${j.id}')">Publish now</button>`);
      }
      if (j.error) {
        actions.push(`<span class="meta">Error: ${j.error}</span>`);
      }
      return `
        <div class="job">
          <div class="job-header">
            <span class="job-id">${j.id}</span>
            <span class="badge ${j.status}">${j.status}</span>
          </div>
          <div class="meta">${j.topic || ""}</div>
          ${video}
          <div class="job-actions">${actions.join("")}</div>
        </div>`;
    })
    .join("");
  _restoreVideoState(videoState);
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
  await fetch(`${API}/api/generate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ topic, duration, audio_mode }),
  });
  alert(
    duration === 1
      ? "1-min quick test started (~2-5 min to finish). Refresh jobs."
      : "Generation started. Refresh jobs in a few minutes."
  );
  loadJobs();
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
    alert("Competitor cache updated: " + d.path);
  } catch (err) {
    alert(err.message);
  }
};

document.getElementById("btn-auth").onclick = async () => {
  alert("A browser window will open for Google sign-in.");
  try {
    const r = await fetch(`${API}/api/auth-youtube`, { method: "POST" });
    if (!r.ok) {
      const d = await r.json();
      throw new Error(d.detail || "Auth failed");
    }
    alert("YouTube OAuth saved.");
    loadCheck();
  } catch (err) {
    alert(err.message);
  }
};

window.approve = async (id) => {
  const r = await fetch(`${API}/api/jobs/${id}/approve`, { method: "POST" });
  if (!r.ok) alert((await r.json()).detail);
  loadJobs();
};

window.reject = async (id) => {
  const r = await fetch(`${API}/api/jobs/${id}/reject`, { method: "POST" });
  if (!r.ok) alert((await r.json()).detail);
  loadJobs();
};

window.publish = async (id) => {
  if (!confirm("Publish this video to YouTube now?")) return;
  const r = await fetch(`${API}/api/jobs/${id}/publish`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({}),
  });
  const d = await r.json();
  if (!r.ok) alert(d.detail || "Publish failed");
  else alert("Published! Video ID: " + d.youtube_video_id);
  loadJobs();
};

loadCheck();
loadJobs();
// Refresh job list; skip while user is actively watching a preview
setInterval(() => {
  const active = document.querySelector("video[data-job-id]");
  if (active && !active.paused && active.currentTime > 0 && !active.ended) return;
  loadJobs();
}, 15000);
