const viewLoading = document.getElementById("view-loading");
const viewMain = document.getElementById("view-main");
const envStatus = document.getElementById("envStatus");
const openSettingsBtn = document.getElementById("openSettings");
const settingsModal = document.getElementById("settingsModal");
const closeSettingsBtn = document.getElementById("closeSettings");
const envChecklist = document.getElementById("envChecklist");

const stepBtn1 = document.getElementById("stepBtn1");
const stepBtn2 = document.getElementById("stepBtn2");
const stepBtn3 = document.getElementById("stepBtn3");
const stepBtn4 = document.getElementById("stepBtn4");
const step1 = document.getElementById("step1");
const step2 = document.getElementById("step2");
const step3 = document.getElementById("step3");
const step4 = document.getElementById("step4");

const researchPeriod = document.getElementById("researchPeriod");
const researchSource = document.getElementById("researchSource");
const researchQuery = document.getElementById("researchQuery");
const searchTrendingBtn = document.getElementById("searchTrending");
const trendingEmpty = document.getElementById("trendingEmpty");
const trendingList = document.getElementById("trendingList");
const selectAllTrendingBtn = document.getElementById("selectAllTrending");
const clearTrendingBtn = document.getElementById("clearTrending");
const quickGenerateBtn = document.getElementById("quickGenerate");
const toScriptBtn = document.getElementById("toScript");

const ideasCount = document.getElementById("ideasCount");
const ideasList = document.getElementById("ideasList");
const manualIdeaInput = document.getElementById("manualIdea");
const addManualIdeaBtn = document.getElementById("addManualIdea");
const scriptTitle = document.getElementById("scriptTitle");
const scriptMeta = document.getElementById("scriptMeta");
const scriptDuration = document.getElementById("scriptDuration");
const scriptAudio = document.getElementById("scriptAudio");
const scriptVideo = document.getElementById("scriptVideo");
const generateScriptBtn = document.getElementById("generateScript");
const scriptEditor = document.getElementById("scriptEditor");
const backToResearchBtn = document.getElementById("backToResearch");
const toRenderBtn = document.getElementById("toRender");

const jobsCount = document.getElementById("jobsCount");
const jobsList = document.getElementById("jobsList");
const jobTitle = document.getElementById("jobTitle");
const jobStatus = document.getElementById("jobStatus");
const jobProgress = document.getElementById("jobProgress");
const jobProgressLabel = document.getElementById("jobProgressLabel");
const jobProgressCount = document.getElementById("jobProgressCount");
const jobProgressFill = document.getElementById("jobProgressFill");
const jobPreview = document.getElementById("jobPreview");
const previewVideo = document.getElementById("previewVideo");
const cancelJobBtn = document.getElementById("cancelJob");
const deleteJobBtn = document.getElementById("deleteJob");
const backToScriptBtn = document.getElementById("backToScript");
const toPublishBtn = document.getElementById("toPublish");

const pendingCount = document.getElementById("pendingCount");
const pendingList = document.getElementById("pendingList");
const reviewTitle = document.getElementById("reviewTitle");
const reviewMeta = document.getElementById("reviewMeta");
const reviewPreview = document.getElementById("reviewPreview");
const reviewVideo = document.getElementById("reviewVideo");
const reviewMetadata = document.getElementById("reviewMetadata");
const metaTitle = document.getElementById("metaTitle");
const metaDesc = document.getElementById("metaDesc");
const metaTags = document.getElementById("metaTags");
const rejectBtn = document.getElementById("rejectBtn");
const approveBtn = document.getElementById("approveBtn");
const publishSection = document.getElementById("publishSection");
const publishMode = document.getElementById("publishMode");
const publishDate = document.getElementById("publishDate");
const publishBtn = document.getElementById("publishBtn");
const ytConnected = document.getElementById("ytConnected");
const connectYouTubeBtn = document.getElementById("connectYouTube");
const backToRenderBtn = document.getElementById("backToRender");

const quickModal = document.getElementById("quickModal");
const closeQuickBtn = document.getElementById("closeQuick");
const quickTopic = document.getElementById("quickTopic");
const quickDuration = document.getElementById("quickDuration");
const quickAudio = document.getElementById("quickAudio");
const quickVideo = document.getElementById("quickVideo");
const startQuickGenerateBtn = document.getElementById("startQuickGenerate");

const state = {
  step: 1,
  niche: "fitness_warmup",
  envReady: false,
  trending: [],
  ideas: [],
  currentIdea: null,
  currentScript: null,
  jobs: [],
  selectedJobId: null,
  pendingVideos: [],
  selectedPendingId: null,
  youtubeConnected: false,
};

let pollInterval = null;

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function setStep(n) {
  state.step = n;
  step1.hidden = n !== 1;
  step2.hidden = n !== 2;
  step3.hidden = n !== 3;
  step4.hidden = n !== 4;
  stepBtn1.classList.toggle("is-active", n === 1);
  stepBtn2.classList.toggle("is-active", n === 2);
  stepBtn3.classList.toggle("is-active", n === 3);
  stepBtn4.classList.toggle("is-active", n === 4);
  if (n === 3) {
    refreshJobs();
    startPolling();
  } else if (n === 4) {
    refreshPending();
    checkYouTubeStatus();
  } else {
    stopPolling();
  }
}

stepBtn1.addEventListener("click", () => setStep(1));
stepBtn2.addEventListener("click", () => setStep(2));
stepBtn3.addEventListener("click", () => setStep(3));
stepBtn4.addEventListener("click", () => setStep(4));

async function checkEnv() {
  const r = await window.api.checkEnv();
  if (r.ok && r.ready) {
    envStatus.textContent = "Ready";
    envStatus.classList.add("status-pill--on");
    envStatus.classList.remove("status-pill--err");
    state.envReady = true;
    viewLoading.hidden = true;
    viewMain.hidden = false;
  } else if (r.ok) {
    envStatus.textContent = "Missing config";
    envStatus.classList.add("status-pill--err");
    envStatus.classList.remove("status-pill--on");
    viewLoading.hidden = true;
    viewMain.hidden = false;
  } else {
    envStatus.textContent = "Engine error";
    envStatus.classList.add("status-pill--err");
  }
  return r;
}

function renderEnvChecklist(data) {
  envChecklist.innerHTML = "";
  const items = [
    { key: "openai", label: "OpenAI API Key" },
    { key: "pexels", label: "Pexels API Key" },
    { key: "gemini", label: "Gemini API Key (for Veo)" },
    { key: "ffmpeg", label: "FFmpeg" },
    { key: "youtube_api", label: "YouTube API Key" },
    { key: "youtube_oauth", label: "YouTube OAuth" },
  ];
  for (const item of items) {
    const ok = data[item.key];
    const el = document.createElement("div");
    el.className = `env-item ${ok ? "env-ok" : "env-err"}`;
    el.textContent = `${ok ? "✓" : "✗"} ${item.label}`;
    envChecklist.appendChild(el);
  }
  if (data.music_tracks !== undefined) {
    const el = document.createElement("div");
    el.className = `env-item ${data.music_tracks > 0 ? "env-ok" : "env-err"}`;
    el.textContent = `${data.music_tracks > 0 ? "✓" : "✗"} Music tracks (${data.music_tracks})`;
    envChecklist.appendChild(el);
  }
}

openSettingsBtn.addEventListener("click", async () => {
  const r = await window.api.checkEnv();
  if (r.ok) renderEnvChecklist(r);
  settingsModal.hidden = false;
});

closeSettingsBtn.addEventListener("click", () => {
  settingsModal.hidden = true;
});

settingsModal.addEventListener("click", (e) => {
  if (e.target.classList.contains("modal-backdrop")) {
    settingsModal.hidden = true;
  }
});

function renderTrending() {
  trendingList.innerHTML = "";
  if (!state.trending.length) {
    trendingEmpty.hidden = false;
    return;
  }
  trendingEmpty.hidden = true;
  for (const v of state.trending) {
    const el = document.createElement("div");
    el.className = `result-item${v.selected ? " is-selected" : ""}`;
    el.innerHTML = `
      <div class="result-title">
        <label style="display:flex;gap:0.5rem;align-items:flex-start;cursor:pointer;">
          <input type="checkbox" class="pick" ${v.selected ? "checked" : ""} />
          <span>${escapeHtml(v.title)}</span>
        </label>
      </div>
      <div class="result-meta">${escapeHtml(v.channel_handle || "")} · ${v.view_count?.toLocaleString() || 0} views · ${v.source}</div>
    `;
    const cb = el.querySelector("input.pick");
    cb.addEventListener("click", (e) => {
      e.stopPropagation();
      v.selected = cb.checked;
      renderTrending();
    });
    el.addEventListener("click", () => {
      v.selected = !v.selected;
      renderTrending();
    });
    trendingList.appendChild(el);
  }
}

searchTrendingBtn.addEventListener("click", async () => {
  searchTrendingBtn.disabled = true;
  searchTrendingBtn.textContent = "Searching...";
  const r = await window.api.fetchTrending({
    period: researchPeriod.value,
    source: researchSource.value,
    query: researchQuery.value || undefined,
  });
  searchTrendingBtn.disabled = false;
  searchTrendingBtn.textContent = "Search";
  if (r.ok && r.combined) {
    state.trending = r.combined.map((v) => ({ ...v, selected: false }));
    renderTrending();
  }
});

selectAllTrendingBtn.addEventListener("click", () => {
  for (const v of state.trending) v.selected = true;
  renderTrending();
});

clearTrendingBtn.addEventListener("click", () => {
  for (const v of state.trending) v.selected = false;
  renderTrending();
});

toScriptBtn.addEventListener("click", () => {
  const selected = state.trending.filter((v) => v.selected);
  state.ideas = selected.map((v) => ({
    id: v.video_id || crypto.randomUUID(),
    title: v.title,
    source: v.source,
    viewCount: v.view_count,
  }));
  renderIdeas();
  setStep(2);
});

quickGenerateBtn.addEventListener("click", () => {
  quickModal.hidden = false;
});

closeQuickBtn.addEventListener("click", () => {
  quickModal.hidden = true;
});

quickModal.addEventListener("click", (e) => {
  if (e.target.classList.contains("modal-backdrop")) {
    quickModal.hidden = true;
  }
});

startQuickGenerateBtn.addEventListener("click", async () => {
  const topic = quickTopic.value.trim();
  if (!topic) return;
  startQuickGenerateBtn.disabled = true;
  startQuickGenerateBtn.textContent = "Starting...";
  const r = await window.api.generateDirect({
    topic,
    duration: parseInt(quickDuration.value) || 12,
    audioMode: quickAudio.value,
    videoMode: quickVideo.value,
    niche: state.niche,
  });
  startQuickGenerateBtn.disabled = false;
  startQuickGenerateBtn.textContent = "Generate Video";
  quickModal.hidden = true;
  if (r.ok && r.job_id) {
    setStep(3);
    state.selectedJobId = r.job_id;
    refreshJobs();
  }
});

function renderIdeas() {
  ideasList.innerHTML = "";
  ideasCount.textContent = `${state.ideas.length} ideas`;
  for (const idea of state.ideas) {
    const el = document.createElement("div");
    el.className = `result-item${state.currentIdea?.id === idea.id ? " is-selected" : ""}`;
    el.innerHTML = `
      <div class="result-title">${escapeHtml(idea.title)}</div>
      <div class="result-meta">${idea.source || "manual"}${idea.viewCount ? ` · ${idea.viewCount.toLocaleString()} views` : ""}</div>
    `;
    el.addEventListener("click", () => {
      state.currentIdea = idea;
      state.currentScript = null;
      renderIdeas();
      renderScriptEditor();
      scriptTitle.textContent = idea.title;
      scriptMeta.textContent = idea.source || "manual";
    });
    ideasList.appendChild(el);
  }
}

addManualIdeaBtn.addEventListener("click", () => {
  const title = manualIdeaInput.value.trim();
  if (!title) return;
  state.ideas.push({
    id: crypto.randomUUID(),
    title,
    source: "manual",
  });
  manualIdeaInput.value = "";
  renderIdeas();
});

manualIdeaInput.addEventListener("keypress", (e) => {
  if (e.key === "Enter") addManualIdeaBtn.click();
});

generateScriptBtn.addEventListener("click", async () => {
  if (!state.currentIdea) return;
  generateScriptBtn.disabled = true;
  generateScriptBtn.textContent = "Generating...";
  const r = await window.api.generateScript({
    topic: state.currentIdea.title,
    duration: parseInt(scriptDuration.value) || 12,
    audioMode: scriptAudio.value,
    videoMode: scriptVideo.value,
    niche: state.niche,
  });
  generateScriptBtn.disabled = false;
  generateScriptBtn.textContent = "Generate Script";
  if (r.ok && r.script) {
    state.currentScript = r.script;
    renderScriptEditor();
  }
});

function renderScriptEditor() {
  if (!state.currentScript) {
    scriptEditor.innerHTML = '<div class="scenes-empty">Generate a script to see scenes here.</div>';
    return;
  }
  const script = state.currentScript;
  let html = `<div class="scene-item"><div class="scene-header"><span class="scene-num">TITLE</span></div><div class="scene-title">${escapeHtml(script.title_draft || script.title || "")}</div></div>`;
  if (script.scenes) {
    for (const scene of script.scenes) {
      html += `
        <div class="scene-item">
          <div class="scene-header">
            <span class="scene-num">Scene ${scene.id}</span>
            <span class="scene-duration">${scene.duration_sec}s</span>
          </div>
          <div class="scene-title">${escapeHtml(scene.on_screen_text || scene.exercise)}</div>
          <div class="scene-text">${escapeHtml(scene.voiceover || "")}</div>
        </div>
      `;
    }
  }
  scriptEditor.innerHTML = html;
}

backToResearchBtn.addEventListener("click", () => setStep(1));

toRenderBtn.addEventListener("click", async () => {
  if (!state.currentScript) return;
  toRenderBtn.disabled = true;
  toRenderBtn.textContent = "Starting...";
  const r = await window.api.generateDirect({
    topic: state.currentIdea?.title || state.currentScript.topic,
    duration: parseInt(scriptDuration.value) || 12,
    audioMode: scriptAudio.value,
    videoMode: scriptVideo.value,
    niche: state.niche,
  });
  toRenderBtn.disabled = false;
  toRenderBtn.textContent = "Render Video →";
  if (r.ok && r.job_id) {
    state.selectedJobId = r.job_id;
    setStep(3);
  }
});

async function refreshJobs() {
  const r = await window.api.listJobs();
  if (r.ok) {
    state.jobs = r.jobs || r || [];
    if (Array.isArray(state.jobs)) {
      renderJobs();
      if (state.selectedJobId) {
        updateSelectedJob();
      }
    }
  }
}

function renderJobs() {
  jobsList.innerHTML = "";
  const jobs = Array.isArray(state.jobs) ? state.jobs : [];
  jobsCount.textContent = `${jobs.length} jobs`;
  for (const job of jobs) {
    const el = document.createElement("div");
    el.className = `result-item${state.selectedJobId === job.id ? " is-selected" : ""}`;
    el.innerHTML = `
      <div class="result-title">${escapeHtml(job.topic || job.id)}</div>
      <div class="result-meta">${job.status} · ${job.stage_message || ""}</div>
    `;
    el.addEventListener("click", () => {
      state.selectedJobId = job.id;
      renderJobs();
      updateSelectedJob();
    });
    jobsList.appendChild(el);
  }
}

async function updateSelectedJob() {
  if (!state.selectedJobId) return;
  const r = await window.api.getJobStatus(state.selectedJobId);
  if (!r.ok) return;
  const job = r;
  jobTitle.textContent = job.topic || job.id;
  jobStatus.textContent = `${job.status} - ${job.stage_message || ""}`;
  
  if (job.status === "generating") {
    jobProgress.hidden = false;
    jobProgressLabel.textContent = job.stage || "Processing";
    jobProgressCount.textContent = `${job.progress_pct || 0}%`;
    jobProgressFill.style.width = `${job.progress_pct || 0}%`;
    jobPreview.hidden = true;
  } else if (job.status === "pending_review" || job.status === "approved" || job.status === "published") {
    jobProgress.hidden = true;
    if (job.video_path) {
      const url = await window.api.getVideoUrl(job.id);
      if (url.ok) {
        previewVideo.src = url.url;
        jobPreview.hidden = false;
      }
    }
  } else {
    jobProgress.hidden = true;
    jobPreview.hidden = true;
  }
}

function startPolling() {
  if (pollInterval) return;
  pollInterval = setInterval(() => {
    refreshJobs();
  }, 3000);
}

function stopPolling() {
  if (pollInterval) {
    clearInterval(pollInterval);
    pollInterval = null;
  }
}

cancelJobBtn.addEventListener("click", async () => {
  if (!state.selectedJobId) return;
  await window.api.cancelJob(state.selectedJobId);
  refreshJobs();
});

deleteJobBtn.addEventListener("click", async () => {
  if (!state.selectedJobId) return;
  await window.api.deleteJob(state.selectedJobId);
  state.selectedJobId = null;
  refreshJobs();
});

backToScriptBtn.addEventListener("click", () => setStep(2));

toPublishBtn.addEventListener("click", () => {
  setStep(4);
});

async function refreshPending() {
  const r = await window.api.listJobs();
  if (r.ok) {
    const jobs = r.jobs || r || [];
    state.pendingVideos = jobs.filter((j) => 
      j.status === "pending_review" || j.status === "approved"
    );
    renderPending();
  }
}

function renderPending() {
  pendingList.innerHTML = "";
  pendingCount.textContent = `${state.pendingVideos.length} videos`;
  for (const job of state.pendingVideos) {
    const el = document.createElement("div");
    el.className = `result-item${state.selectedPendingId === job.id ? " is-selected" : ""}`;
    el.innerHTML = `
      <div class="result-title">${escapeHtml(job.topic || job.id)}</div>
      <div class="result-meta">${job.status}</div>
    `;
    el.addEventListener("click", async () => {
      state.selectedPendingId = job.id;
      renderPending();
      await updateSelectedPending();
    });
    pendingList.appendChild(el);
  }
}

async function updateSelectedPending() {
  if (!state.selectedPendingId) return;
  const r = await window.api.getJobStatus(state.selectedPendingId);
  if (!r.ok) return;
  const job = r;
  reviewTitle.textContent = job.topic || job.id;
  reviewMeta.textContent = job.status;
  
  if (job.video_path) {
    const url = await window.api.getVideoUrl(job.id);
    if (url.ok) {
      reviewVideo.src = url.url;
      reviewPreview.hidden = false;
    }
  }
  
  if (job.metadata_json) {
    try {
      const meta = typeof job.metadata_json === "string" 
        ? JSON.parse(job.metadata_json) 
        : job.metadata_json;
      metaTitle.textContent = meta.title || "";
      metaDesc.textContent = meta.description || "";
      metaTags.textContent = (meta.tags || []).join(", ");
      reviewMetadata.hidden = false;
    } catch {
      reviewMetadata.hidden = true;
    }
  } else {
    reviewMetadata.hidden = true;
  }
  
  if (job.status === "approved") {
    publishSection.hidden = false;
    rejectBtn.hidden = true;
    approveBtn.hidden = true;
  } else {
    publishSection.hidden = true;
    rejectBtn.hidden = false;
    approveBtn.hidden = false;
  }
}

rejectBtn.addEventListener("click", async () => {
  if (!state.selectedPendingId) return;
  await window.api.rejectVideo(state.selectedPendingId);
  state.selectedPendingId = null;
  refreshPending();
});

approveBtn.addEventListener("click", async () => {
  if (!state.selectedPendingId) return;
  approveBtn.disabled = true;
  approveBtn.textContent = "Approving...";
  await window.api.approveVideo(state.selectedPendingId);
  approveBtn.disabled = false;
  approveBtn.textContent = "Approve";
  refreshPending();
  updateSelectedPending();
});

publishMode.addEventListener("change", () => {
  publishDate.hidden = publishMode.value !== "scheduled";
});

publishBtn.addEventListener("click", async () => {
  if (!state.selectedPendingId) return;
  publishBtn.disabled = true;
  publishBtn.textContent = "Publishing...";
  const publishAt = publishMode.value === "scheduled" ? publishDate.value : null;
  await window.api.publishVideo(state.selectedPendingId, publishAt);
  publishBtn.disabled = false;
  publishBtn.textContent = "Publish to YouTube";
  refreshPending();
});

async function checkYouTubeStatus() {
  const r = await window.api.getYouTubeStatus();
  state.youtubeConnected = r.ok && r.connected;
  ytConnected.hidden = !state.youtubeConnected;
  ytConnected.classList.toggle("status-pill--on", state.youtubeConnected);
  connectYouTubeBtn.hidden = state.youtubeConnected;
}

connectYouTubeBtn.addEventListener("click", async () => {
  connectYouTubeBtn.disabled = true;
  connectYouTubeBtn.textContent = "Connecting...";
  await window.api.startYouTubeAuth();
  connectYouTubeBtn.disabled = false;
  connectYouTubeBtn.textContent = "Connect YouTube";
  checkYouTubeStatus();
});

backToRenderBtn.addEventListener("click", () => setStep(3));

async function init() {
  await checkEnv();
}

init();
