/* Research workspace — uses globals from app.js */

function formatViews(n) {
  if (n == null) return "—";
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1000) return `${(n / 1000).toFixed(1)}K`;
  return String(n);
}

function formatDuration(sec) {
  if (!sec) return "—";
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return m ? `${m}m ${s}s` : `${s}s`;
}

async function loadTrending() {
  const period = document.getElementById("research-period").value;
  const source = document.getElementById("research-source").value;
  const q = document.getElementById("research-query").value.trim();
  const el = document.getElementById("trending-table");
  el.innerHTML = `<p class="list-empty">Loading trending from YouTube… (may take 15–30s)</p>`;
  try {
    const params = new URLSearchParams({ period, source });
    if (q && source !== "competitors") params.set("q", q);
    const r = await fetch(`${API}/api/research/trending?${params}`);
    const d = await r.json();
    if (!r.ok) throw new Error(d.detail || "Failed to load trending");
    trendingData = d.combined || [];
    if (d.warnings?.length) {
      toast(d.warnings.join(" "), "info");
    }
    renderTrendingTable();
  } catch (err) {
    el.innerHTML = `<p class="error-text">${escapeHtml(err.message)}</p>`;
  }
}

function renderTrendingTable() {
  const el = document.getElementById("trending-table");
  if (!trendingData.length) {
    el.innerHTML = `<p class="list-empty">No videos found for this period. Try Last 30 days or Niche search.</p>`;
    return;
  }
  el.innerHTML = "";
  trendingData.slice(0, 40).forEach((v, i) => {
    const row = document.createElement("div");
    row.className = "trending-row";
    const main = document.createElement("div");
    const title = document.createElement("div");
    title.className = "trending-title";
    title.textContent = v.title;
    const meta = document.createElement("div");
    meta.className = "trending-meta";
    meta.textContent = `${v.channel_handle || v.source} · ${formatViews(v.view_count)} views · ${formatDuration(v.duration_sec)}`;
    main.appendChild(title);
    main.appendChild(meta);
    const actions = document.createElement("div");
    actions.className = "trending-actions";
    const saveBtn = document.createElement("button");
    saveBtn.type = "button";
    saveBtn.className = "btn btn-secondary btn-sm";
    saveBtn.textContent = "Save idea";
    saveBtn.onclick = () => saveTrendingAsIdea(i);
    const link = document.createElement("a");
    link.className = "btn btn-ghost btn-sm";
    link.href = v.url;
    link.target = "_blank";
    link.rel = "noopener";
    link.textContent = "YouTube";
    actions.appendChild(saveBtn);
    actions.appendChild(link);
    row.appendChild(main);
    row.appendChild(actions);
    el.appendChild(row);
  });
}

async function saveTrendingAsIdea(idx) {
  const v = trendingData[idx];
  if (!v) return;
  const period = document.getElementById("research-period").value;
  try {
    const r = await fetch(`${API}/api/ideas`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        title: v.title,
        notes: `Inspired by ${v.view_count} views in ${period}. ${v.url}`,
        source: v.source === "competitor" ? "competitor" : "niche",
        source_video_id: v.video_id,
        source_channel: v.channel_handle || "",
        view_count: v.view_count,
        period,
      }),
    });
    const d = await r.json();
    if (!r.ok) throw new Error(d.detail || "Save failed");
    toast("Idea saved", "success");
    selectedIdeaId = d.idea?.id;
    loadIdeas();
  } catch (err) {
    toast(err.message, "error");
  }
}

async function loadIdeas() {
  try {
    const r = await fetch(`${API}/api/ideas`);
    allIdeas = await r.json();
  } catch {
    allIdeas = [];
  }
  renderIdeasList();
}

function renderIdeasList() {
  const el = document.getElementById("ideas-list");
  if (!allIdeas.length) {
    el.innerHTML = `<p class="list-empty">No ideas yet. Save from trending.</p>`;
    return;
  }
  el.innerHTML = "";
  allIdeas.forEach((idea) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = `job-card${idea.id === selectedIdeaId ? " selected" : ""}`;
    btn.innerHTML = `
      <div class="job-card-top">
        <span class="job-card-topic">${escapeHtml(idea.title)}</span>
        <span class="badge ${idea.status}">${escapeHtml(idea.status)}</span>
      </div>
      ${idea.notes ? `<div class="idea-card-notes">${escapeHtml(idea.notes.slice(0, 80))}${idea.notes.length > 80 ? "…" : ""}</div>` : ""}`;
    btn.onclick = () => selectIdea(idea.id);
    el.appendChild(btn);
  });
}

function selectIdea(id) {
  selectedIdeaId = id;
  selectedDraftId = null;
  renderIdeasList();
  loadDrafts(id);
  const idea = allIdeas.find((i) => i.id === id);
  document.getElementById("draft-empty")?.classList.add("hidden");
  document.getElementById("draft-toolbar")?.classList.remove("hidden");
  document.getElementById("draft-scenes")?.classList.remove("hidden");
  const ideaTitle = document.getElementById("draft-idea-title");
  if (idea && ideaTitle) {
    ideaTitle.textContent = idea.title;
    ideaTitle.classList.remove("hidden");
  }
}

async function loadDrafts(ideaId = null) {
  try {
    const url = ideaId ? `${API}/api/drafts?idea_id=${ideaId}` : `${API}/api/drafts`;
    const r = await fetch(url);
    allDrafts = await r.json();
  } catch {
    allDrafts = [];
  }
  populateDraftSelects();
  updateCompareVisibility();
  const valid = allDrafts.filter(isDraftValid);
  if (valid.length) {
    selectedDraftId = valid[0].id;
    renderDraftScenes(valid[0]);
  } else if (allDrafts.length) {
    selectedDraftId = allDrafts[0].id;
    renderDraftScenes(allDrafts[0]);
  } else {
    renderDraftScenes(null);
  }
}

function populateDraftSelects() {
  const selA = document.getElementById("draft-select-a");
  const selB = document.getElementById("draft-select-b");
  if (!selA || !selB) return;
  selA.innerHTML = "";
  selB.innerHTML = "";
  if (!allDrafts.length) {
    const empty = document.createElement("option");
    empty.textContent = "No drafts yet";
    selA.appendChild(empty);
    return;
  }
  allDrafts.forEach((d) => {
    const label = isDraftValid(d)
      ? d.label || d.topic
      : `${d.label || d.topic} (empty — regenerate)`;
    const optA = document.createElement("option");
    optA.value = d.id;
    optA.textContent = label;
    selA.appendChild(optA);
    const optB = document.createElement("option");
    optB.value = d.id;
    optB.textContent = label;
    selB.appendChild(optB);
  });
  if (allDrafts.length > 1) selB.selectedIndex = 1;
  if (selectedDraftId) selA.value = selectedDraftId;
}

function parseDraftScript(draft) {
  if (!draft?.script_json || draft.script_json === "{}") return null;
  try {
    const script = JSON.parse(draft.script_json);
    if (!script || !Array.isArray(script.scenes) || !script.scenes.length) return null;
    return script;
  } catch {
    return null;
  }
}

function isDraftValid(draft) {
  return parseDraftScript(draft) !== null;
}

function updateCompareVisibility() {
  const wrap = document.getElementById("draft-compare-wrap");
  if (!wrap) return;
  wrap.classList.toggle("hidden", allDrafts.filter(isDraftValid).length < 2);
}

function renderDraftScenes(draft) {
  const labelEl = document.getElementById("draft-label");
  const listEl = document.getElementById("scene-list");
  if (!listEl) return;

  if (!draft) {
    if (labelEl) labelEl.textContent = "";
    listEl.innerHTML =
      '<p class="list-empty">No script draft yet. Click <strong>New script draft</strong> to generate one (~20s).</p>';
    return;
  }

  selectedDraftId = draft.id;
  const script = parseDraftScript(draft);
  if (labelEl) labelEl.textContent = `— ${draft.label || draft.topic}`;

  if (!script) {
    listEl.innerHTML =
      '<p class="list-empty">This draft is empty or invalid. Click <strong>New script draft</strong> to regenerate.</p>';
    return;
  }

  listEl.innerHTML = "";
  script.scenes.forEach((scene, idx) => {
    const div = document.createElement("div");
    div.className = "scene-item";
    div.innerHTML = `
      <div class="scene-item-head">
        <span>Scene ${scene.id} · ${scene.duration_sec}s · ${scene.provider || "stock"}</span>
        <div class="scene-move-btns">
          <button type="button" class="btn btn-ghost btn-sm" data-move-up ${idx === 0 ? "disabled" : ""}>↑</button>
          <button type="button" class="btn btn-ghost btn-sm" data-move-down ${idx === script.scenes.length - 1 ? "disabled" : ""}>↓</button>
        </div>
      </div>
      <label>On-screen text<input type="text" data-field="on_screen_text" /></label>
      <label>Visual prompt<textarea data-field="visual_prompt"></textarea></label>
      <label>Duration (sec)<input type="number" data-field="duration_sec" min="5" max="180" /></label>`;
    div.querySelector('[data-field="on_screen_text"]').value = scene.on_screen_text;
    div.querySelector('[data-field="visual_prompt"]').value = scene.visual_prompt || "";
    div.querySelector('[data-field="duration_sec"]').value = scene.duration_sec;
    div.querySelector("[data-move-up]")?.addEventListener("click", () => moveScene(idx, -1));
    div.querySelector("[data-move-down]")?.addEventListener("click", () => moveScene(idx, 1));
    listEl.appendChild(div);
  });
}

function getEditedScriptFromDom() {
  const draft = allDrafts.find((d) => d.id === selectedDraftId);
  const script = parseDraftScript(draft);
  if (!script) return null;
  const items = document.querySelectorAll("#scene-list .scene-item");
  items.forEach((item, idx) => {
    const scene = script.scenes[idx];
    if (!scene) return;
    scene.on_screen_text = item.querySelector('[data-field="on_screen_text"]')?.value || scene.on_screen_text;
    scene.visual_prompt = item.querySelector('[data-field="visual_prompt"]')?.value || scene.visual_prompt;
    scene.duration_sec =
      parseInt(item.querySelector('[data-field="duration_sec"]')?.value, 10) || scene.duration_sec;
  });
  script.total_duration_sec = script.scenes.reduce((s, sc) => s + sc.duration_sec, 0);
  return script;
}

function moveScene(idx, dir) {
  const draft = allDrafts.find((d) => d.id === selectedDraftId);
  const script = getEditedScriptFromDom() || parseDraftScript(draft);
  if (!script) return;
  const newIdx = idx + dir;
  if (newIdx < 0 || newIdx >= script.scenes.length) return;
  [script.scenes[idx], script.scenes[newIdx]] = [script.scenes[newIdx], script.scenes[idx]];
  script.scenes.forEach((s, i) => {
    s.id = i + 1;
  });
  draft.script_json = JSON.stringify(script);
  renderDraftScenes(draft);
}

async function saveDraftScenes() {
  if (!selectedDraftId) return;
  const script = getEditedScriptFromDom();
  if (!script) return;
  try {
    const r = await fetch(`${API}/api/drafts/${selectedDraftId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ script_json: JSON.stringify(script) }),
    });
    const d = await r.json();
    if (!r.ok) throw new Error(d.detail || "Save failed");
    toast("Draft scenes saved", "success");
    loadDrafts(selectedIdeaId);
  } catch (err) {
    toast(err.message, "error");
  }
}

async function generateDraftFromIdea() {
  const idea = allIdeas.find((i) => i.id === selectedIdeaId);
  if (!idea) {
    toast("Select an idea first", "error");
    return;
  }
  const btn = document.getElementById("btn-generate-draft-script");
  if (btn) {
    btn.disabled = true;
    btn.textContent = "Generating script…";
  }
  try {
    const r = await fetch(`${API}/api/drafts/generate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        topic: idea.title,
        duration: 1,
        audio_mode: "coach_voice",
        video_mode: "premium",
        idea_id: idea.id,
        extra_context: idea.notes || "",
      }),
    });
    const d = await r.json();
    if (!r.ok) throw new Error(d.detail || "Draft generation failed");
    toast("Script draft generated", "success");
    selectedDraftId = d.draft_id;
    await loadDrafts(selectedIdeaId);
  } catch (err) {
    toast(err.message, "error");
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = "New script draft";
    }
  }
}

async function generateVideoFromDraft() {
  if (!selectedDraftId) {
    toast("Select a draft first", "error");
    return;
  }
  await saveDraftScenes();
  try {
    const r = await fetch(`${API}/api/drafts/${selectedDraftId}/generate-video`, { method: "POST" });
    const d = await r.json();
    if (!r.ok) throw new Error(d.detail || "Generate failed");
    toast("Video generation started from draft", "success");
    switchView("studio");
    if (d.job_id) {
      selectedJobId = d.job_id;
      initialSelectDone = true;
    }
    loadJobs();
  } catch (err) {
    toast(err.message, "error");
  }
}

function compareDrafts() {
  const idA = document.getElementById("draft-select-a")?.value;
  const idB = document.getElementById("draft-select-b")?.value;
  const draftA = allDrafts.find((d) => d.id === idA);
  const draftB = allDrafts.find((d) => d.id === idB);
  const box = document.getElementById("draft-compare");
  if (!draftA || !draftB || !box) return;
  const scriptA = parseDraftScript(draftA);
  const scriptB = parseDraftScript(draftB);
  box.classList.remove("hidden");
  box.innerHTML = "";
  [draftA, draftB].forEach((draft, i) => {
    const script = i === 0 ? scriptA : scriptB;
    const first = script?.scenes?.[0]?.on_screen_text || "—";
    const last = script?.scenes?.[script.scenes.length - 1]?.on_screen_text || "—";
    const col = document.createElement("div");
    col.className = "draft-compare-col";
    col.innerHTML = `
      <strong>${escapeHtml(draft.label || draft.topic)}</strong>
      <p>Scenes: ${script?.scenes?.length || 0}</p>
      <p>Duration: ${script?.total_duration_sec || 0}s</p>
      <p>Title: ${escapeHtml(script?.title_draft || "")}</p>
      <p>First: ${escapeHtml(first)}</p>
      <p>Last: ${escapeHtml(last)}</p>`;
    box.appendChild(col);
  });
}

async function createManualIdea() {
  const title = prompt("Idea title / video topic:");
  if (!title?.trim()) return;
  try {
    const r = await fetch(`${API}/api/ideas`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title: title.trim(), source: "manual" }),
    });
    const d = await r.json();
    if (!r.ok) throw new Error(d.detail || "Failed");
    selectedIdeaId = d.idea?.id;
    loadIdeas();
    selectIdea(selectedIdeaId);
    toast("Idea created", "success");
  } catch (err) {
    toast(err.message, "error");
  }
}

function initResearchUI() {
  document.getElementById("btn-load-trending").onclick = loadTrending;
  document.getElementById("btn-refresh-research").onclick = async () => {
    try {
      const r = await fetch(`${API}/api/research/refresh`, { method: "POST" });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail || "Refresh failed");
      toast("Competitor cache updated", "success");
    } catch (err) {
      toast(err.message, "error");
    }
  };
  document.getElementById("btn-new-idea").onclick = createManualIdea;
  document.getElementById("btn-save-draft-scenes").onclick = saveDraftScenes;
  document.getElementById("btn-generate-from-draft").onclick = generateVideoFromDraft;
  document.getElementById("btn-generate-draft-script").onclick = generateDraftFromIdea;
  document.getElementById("btn-compare-drafts").onclick = compareDrafts;
  document.getElementById("draft-select-a").onchange = () => {
    const draft = allDrafts.find((d) => d.id === document.getElementById("draft-select-a").value);
    if (draft) renderDraftScenes(draft);
  };
}

initResearchUI();
