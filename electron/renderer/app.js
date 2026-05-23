const API = window.appConfig?.apiBase || "http://127.0.0.1:8765";

let pollTimer = null;
let selectedJobId = null;
let activeFilter = "all";
let allJobs = [];
let initialSelectDone = false;
let pendingPublishJobId = null;
let jobMetadataCache = {};

const PLAYABLE_STATUSES = ["pending_review", "approved", "published", "scheduled"];

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

function relativeTime(iso) {
  if (!iso) return "";
  const sec = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
  if (sec < 60) return "just now";
  if (sec < 3600) return `${Math.floor(sec / 60)}m ago`;
  if (sec < 86400) return `${Math.floor(sec / 3600)}h ago`;
  return `${Math.floor(sec / 86400)}d ago`;
}

function isReady(c) {
  if (typeof c.ready === "boolean") return c.ready;
  return Boolean(c.openai && c.pexels && c.ffmpeg);
}

function statusLabel(status) {
  return (status || "").replace(/_/g, " ");
}

function filterJobs(jobs) {
  switch (activeFilter) {
    case "active":
      return jobs.filter((j) => j.status === "generating" || j.status === "uploading");
    case "review":
      return jobs.filter((j) => j.status === "pending_review");
    case "approved":
      return jobs.filter((j) => j.status === "approved");
    case "done":
      return jobs.filter((j) => j.status === "published" || j.status === "scheduled");
    case "failed":
      return jobs.filter((j) => j.status === "failed");
    default:
      return jobs;
  }
}

function pickAutoSelectJob(jobs) {
  const sorted = [...jobs].sort(
    (a, b) => new Date(b.updated_at || b.created_at) - new Date(a.updated_at || a.created_at)
  );
  return (
    sorted.find((j) => j.status === "pending_review") ||
    sorted.find((j) => j.status === "generating" || j.status === "uploading") ||
    sorted[0] ||
    null
  );
}

async function loadCheck() {
  const r = await fetch(`${API}/api/check`);
  const c = await r.json();

  const checklist = document.getElementById("env-checklist");
  checklist.innerHTML = [
    checklistItem("OpenAI API key", c.openai),
    checklistItem("Pexels API key", c.pexels),
    checklistItem("FFmpeg", c.ffmpeg, c.ffmpeg_msg),
    checklistItem("YouTube OAuth", c.youtube_oauth),
    checklistItem(`Music tracks (${c.music_tracks || 0})`, (c.music_tracks || 0) > 0),
  ].join("");

  const setup = document.getElementById("setup-warning");
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
    issues.innerHTML = "";
  }
  return c;
}

function checklistItem(label, ok, detail) {
  const icon = ok ? "✓" : "✗";
  const cls = ok ? "check-ok" : "check-fail";
  const extra = !ok && detail ? ` — ${detail}` : "";
  return `<li><span class="${cls}">${icon}</span> ${label}${extra}</li>`;
}

function progressBar(pct) {
  const p = Math.min(100, Math.max(0, pct || 0));
  return `<div class="progress"><div class="progress-fill" style="width:${p}%"></div></div>`;
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

function selectJob(id) {
  selectedJobId = id;
  renderJobList(allJobs);
  const job = allJobs.find((j) => j.id === id);
  renderDetail(job);
}

function renderJobList(jobs) {
  const el = document.getElementById("job-list");
  const filtered = filterJobs(jobs);

  if (!filtered.length) {
    el.innerHTML = `<p class="list-empty">No jobs in this view.</p>`;
    return;
  }

  el.innerHTML = filtered
    .map((j) => {
      const topic = j.topic || "Untitled";
      const selected = j.id === selectedJobId ? " selected" : "";
      const active = j.status === "generating" || j.status === "uploading";
      const progress =
        active && j.progress_pct != null
          ? progressBar(j.progress_pct)
          : active
            ? progressBar(0)
            : "";
      return `
        <button type="button" class="job-card${selected}" data-job-id="${j.id}">
          <div class="job-card-top">
            <span class="job-card-topic">${escapeHtml(topic)}</span>
            <span class="badge ${j.status}">${statusLabel(j.status)}</span>
          </div>
          <div class="job-card-time">${relativeTime(j.updated_at || j.created_at)}</div>
          ${progress}
        </button>`;
    })
    .join("");

  el.querySelectorAll(".job-card").forEach((btn) => {
    btn.onclick = () => selectJob(btn.dataset.jobId);
  });
}

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

async function fetchMetadata(jobId) {
  try {
    const r = await fetch(`${API}/api/jobs/${jobId}/metadata`);
    if (!r.ok) return null;
    const data = await r.json();
    jobMetadataCache[jobId] = data;
    return data;
  } catch {
    return null;
  }
}

function renderMetadataBlock(meta) {
  if (!meta) return "";
  const rows = [];
  if (meta.title) rows.push(["Title", meta.title]);
  if (meta.description) rows.push(["Description", meta.description]);
  if (meta.tags?.length) rows.push(["Tags", meta.tags.join(", ")]);
  if (!rows.length) return "";
  return `
    <div class="detail-block">
      <h3>YouTube metadata</h3>
      <dl class="metadata-grid">
        ${rows.map(([k, v]) => `<dt>${k}</dt><dd>${escapeHtml(v)}</dd>`).join("")}
      </dl>
    </div>`;
}

function renderDetail(job) {
  const empty = document.getElementById("detail-empty");
  const content = document.getElementById("detail-content");

  if (!job) {
    empty.classList.remove("hidden");
    content.classList.add("hidden");
    content.innerHTML = "";
    return;
  }

  empty.classList.add("hidden");
  content.classList.remove("hidden");

  const videoState = _saveVideoState();
  const canPlay = job.video_path && PLAYABLE_STATUSES.includes(job.status);
  const video = canPlay
    ? `<div class="detail-video-wrap"><video controls preload="metadata" data-job-id="${job.id}" src="${API}/api/jobs/${job.id}/video?v=${encodeURIComponent(job.updated_at || "")}"></video></div>`
    : "";

  let stageHtml = "";
  if (job.status === "generating" || job.status === "uploading") {
    stageHtml = `
      <div class="detail-stage">
        <div class="stage-info">
          <span class="spinner"></span>
          <span>${escapeHtml(job.stage_message || job.status)}…</span>
          <span class="meta">(${elapsedSince(job.updated_at)} elapsed)</span>
        </div>
        ${progressBar(job.progress_pct)}
      </div>`;
  } else if (job.stage_message && job.status === "failed") {
    stageHtml = `<div class="detail-stage"><p class="error-text">${escapeHtml(job.stage_message)}</p></div>`;
  }

  if (job.error) {
    stageHtml += `<p class="error-text">Error: ${escapeHtml(job.error)}</p>`;
  }

  let actionsHtml = "";
  if (job.status === "pending_review") {
    actionsHtml = `
      <div class="detail-actions">
        <button type="button" class="btn btn-primary" data-action="approve">Approve</button>
        <button type="button" class="btn btn-danger" data-action="reject">Reject</button>
      </div>`;
  } else if (job.status === "approved") {
    actionsHtml = `
      <div class="detail-actions">
        <button type="button" class="btn btn-primary" data-action="publish-now">Publish now</button>
      </div>
      <div class="schedule-row">
        <input type="datetime-local" id="schedule-datetime" />
        <button type="button" class="btn btn-secondary" data-action="publish-schedule">Schedule publish</button>
      </div>`;
  } else if (job.status === "published" || job.status === "scheduled") {
    const ytUrl = job.youtube_video_id
      ? `https://www.youtube.com/watch?v=${job.youtube_video_id}`
      : "";
    actionsHtml = `
      <div class="detail-block">
        <h3>YouTube</h3>
        ${ytUrl ? `<p><a class="youtube-link" href="${ytUrl}" target="_blank" rel="noopener">Watch on YouTube</a></p>` : ""}
        ${job.youtube_video_id ? `<p class="meta">Video ID: ${escapeHtml(job.youtube_video_id)}</p>` : ""}
      </div>`;
  } else if (job.status === "failed") {
    actionsHtml = `<p class="meta">Generation failed. Create a new video to retry.</p>`;
  }

  const cachedMeta = jobMetadataCache[job.id];
  let metaBlock = "";
  if (cachedMeta) {
    metaBlock = renderMetadataBlock(cachedMeta);
  } else if (
    ["approved", "published", "scheduled"].includes(job.status) &&
    job.metadata_json
  ) {
    try {
      metaBlock = renderMetadataBlock(JSON.parse(job.metadata_json));
    } catch {
      metaBlock = "";
    }
  }

  content.innerHTML = `
    <div class="detail-header">
      <h2>${escapeHtml(job.topic || "Untitled")}</h2>
      <div class="detail-meta-row">
        <span class="badge ${job.status}">${statusLabel(job.status)}</span>
        <span class="detail-id">${escapeHtml(job.id)}</span>
        <button type="button" class="btn btn-secondary btn-sm btn-copy-id" data-action="copy-id">Copy ID</button>
      </div>
    </div>
    ${stageHtml}
    ${video}
    ${actionsHtml}
    <div id="metadata-slot">${metaBlock}</div>`;

  _restoreVideoState(videoState);

  content.querySelector('[data-action="approve"]')?.addEventListener("click", () => approve(job.id));
  content.querySelector('[data-action="reject"]')?.addEventListener("click", () => reject(job.id));
  content.querySelector('[data-action="publish-now"]')?.addEventListener("click", () =>
    openPublishConfirm(job.id)
  );
  content.querySelector('[data-action="publish-schedule"]')?.addEventListener("click", () =>
    publishScheduled(job.id)
  );
  content.querySelector('[data-action="copy-id"]')?.addEventListener("click", () => {
    navigator.clipboard.writeText(job.id).then(() => toast("Job ID copied", "success"));
  });

  if (["approved", "published", "scheduled"].includes(job.status) && !cachedMeta) {
    fetchMetadata(job.id).then((meta) => {
      if (meta && selectedJobId === job.id) {
        const slot = document.getElementById("metadata-slot");
        if (slot) slot.innerHTML = renderMetadataBlock(meta);
      }
    });
  }
}

async function loadJobs() {
  const r = await fetch(`${API}/api/jobs`);
  const jobs = await r.json();
  allJobs = jobs;

  if (!initialSelectDone) {
    const pick = pickAutoSelectJob(jobs);
    if (pick) selectedJobId = pick.id;
    initialSelectDone = true;
  } else if (selectedJobId && !jobs.find((j) => j.id === selectedJobId)) {
    selectedJobId = jobs[0]?.id || null;
  }

  renderJobList(jobs);
  renderDetail(jobs.find((j) => j.id === selectedJobId));
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

function openNewVideoModal() {
  const overlay = document.getElementById("modal-overlay");
  overlay.classList.remove("hidden");
  overlay.setAttribute("aria-hidden", "false");
  document.getElementById("topic").focus();
}

function closeNewVideoModal() {
  const overlay = document.getElementById("modal-overlay");
  overlay.classList.add("hidden");
  overlay.setAttribute("aria-hidden", "true");
}

function openSettingsDrawer() {
  loadCheck();
  const overlay = document.getElementById("drawer-overlay");
  overlay.classList.remove("hidden");
  overlay.setAttribute("aria-hidden", "false");
}

function closeSettingsDrawer() {
  const overlay = document.getElementById("drawer-overlay");
  overlay.classList.add("hidden");
  overlay.setAttribute("aria-hidden", "true");
}

function openPublishConfirm(jobId) {
  pendingPublishJobId = jobId;
  const job = allJobs.find((j) => j.id === jobId);
  const text = document.getElementById("publish-confirm-text");
  text.textContent = job?.topic
    ? `Publish "${job.topic}" to YouTube as public?`
    : "This will upload the video as public.";
  const overlay = document.getElementById("publish-overlay");
  overlay.classList.remove("hidden");
  overlay.setAttribute("aria-hidden", "false");
}

function closePublishConfirm() {
  pendingPublishJobId = null;
  const overlay = document.getElementById("publish-overlay");
  overlay.classList.add("hidden");
  overlay.setAttribute("aria-hidden", "true");
}

function applyPreset(quick) {
  if (quick) {
    document.getElementById("duration").value = "1";
    document.getElementById("audio").value = "coach_voice";
    if (!document.getElementById("topic").value.trim()) {
      document.getElementById("topic").value = "1 min desk stretch quick test";
    }
  } else {
    document.getElementById("duration").value = "12";
    document.getElementById("audio").value = "coach_voice";
  }
}

async function startGenerate() {
  const topic = document.getElementById("topic").value.trim();
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
    closeNewVideoModal();
    toast(duration === 1 ? "Quick test started." : "Generation started.", "success");
    if (d.job_id) {
      selectedJobId = d.job_id;
      initialSelectDone = true;
    }
    loadJobs();
  } catch (err) {
    toast(err.message, "error");
  } finally {
    btn.disabled = false;
  }
}

async function approve(id) {
  const r = await fetch(`${API}/api/jobs/${id}/approve`, { method: "POST" });
  if (!r.ok) {
    toast((await r.json()).detail, "error");
  } else {
    toast("Approved — metadata generated.", "success");
    delete jobMetadataCache[id];
    selectedJobId = id;
    loadJobs();
  }
}

async function reject(id) {
  const r = await fetch(`${API}/api/jobs/${id}/reject`, { method: "POST" });
  if (!r.ok) toast((await r.json()).detail, "error");
  else toast("Rejected.", "info");
  loadJobs();
}

async function publishNow(id) {
  try {
    const r = await fetch(`${API}/api/jobs/${id}/publish`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    });
    const d = await r.json();
    if (!r.ok) throw new Error(d.detail || "Publish failed");
    toast("Published! Video ID: " + d.youtube_video_id, "success");
    selectedJobId = id;
    loadJobs();
  } catch (err) {
    toast(err.message, "error");
  }
}

function datetimeLocalToIso(value) {
  if (!value) return null;
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return null;
  return d.toISOString();
}

async function publishScheduled(id) {
  const input = document.getElementById("schedule-datetime");
  const raw = datetimeLocalToIso(input?.value);
  if (!raw) {
    toast("Pick a date and time to schedule.", "error");
    return;
  }
  try {
    const r = await fetch(`${API}/api/jobs/${id}/publish`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ publish_at: raw }),
    });
    const d = await r.json();
    if (!r.ok) throw new Error(d.detail || "Schedule failed");
    toast("Scheduled! Video ID: " + d.youtube_video_id, "success");
    selectedJobId = id;
    loadJobs();
  } catch (err) {
    toast(err.message, "error");
  }
}

document.getElementById("btn-new-video").onclick = openNewVideoModal;
document.getElementById("btn-empty-create").onclick = openNewVideoModal;
document.getElementById("modal-close").onclick = closeNewVideoModal;
document.getElementById("modal-cancel").onclick = closeNewVideoModal;
document.getElementById("modal-overlay").onclick = (e) => {
  if (e.target.id === "modal-overlay") closeNewVideoModal();
};

document.getElementById("btn-settings").onclick = openSettingsDrawer;
document.getElementById("drawer-close").onclick = closeSettingsDrawer;
document.getElementById("drawer-overlay").onclick = (e) => {
  if (e.target.id === "drawer-overlay") closeSettingsDrawer();
};

document.getElementById("preset-quick").onclick = () => applyPreset(true);
document.getElementById("preset-standard").onclick = () => applyPreset(false);

document.getElementById("generate-form").onsubmit = async (e) => {
  e.preventDefault();
  await startGenerate();
};

document.getElementById("publish-cancel").onclick = closePublishConfirm;
document.getElementById("publish-overlay").onclick = (e) => {
  if (e.target.id === "publish-overlay") closePublishConfirm();
};
document.getElementById("publish-confirm").onclick = async () => {
  const id = pendingPublishJobId;
  closePublishConfirm();
  if (id) await publishNow(id);
};

document.querySelectorAll(".filter-tab").forEach((tab) => {
  tab.onclick = () => {
    document.querySelectorAll(".filter-tab").forEach((t) => t.classList.remove("active"));
    tab.classList.add("active");
    activeFilter = tab.dataset.filter;
    renderJobList(allJobs);
  };
});

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

loadCheck();
loadJobs();
