"use strict";

(() => {
  const $ = (id) => document.getElementById(id);
  const state = {
    projects: [], status: null, mode: "demo", theme: "forest", view: "create",
    project: null, sceneIndex: 0, assetType: "all", assetRequest: 0,
    jobs: new Map(), timers: new Map(), currentJobId: null, audioScope: null,
    selectedSegment: null, busyCount: 0, courseLoaded: false,
  };
  const themeLabels = { forest: "森林探险", space: "太空旅行", ocean: "海洋奇遇" };
  const themeTitles = { forest: "森林里的\n奇妙相遇", space: "星星上的\n奇妙来信", ocean: "大海里的\n秘密约定" };
  const viewNames = { create: "创作故事", bookshelf: "我的作品书架", assets: "灵感素材库", agent: "Agent 工作台", course: "课程实践清单" };
  const statusLabels = { queued: "已排队", running: "正在执行", paused: "等待你的审阅", completed: "已完成", failed: "执行失败", pending: "等待执行", skipped: "已跳过" };
  const terminal = new Set(["completed", "failed"]);

  function node(tag, className, content) {
    const item = document.createElement(tag);
    if (className) item.className = className;
    if (content !== undefined && content !== null) item.textContent = String(content);
    return item;
  }
  function clear(item) { item.replaceChildren(); return item; }
  function displayText(value) {
    if (Array.isArray(value)) return value.map(displayText).join("、");
    if (value && typeof value === "object") return Object.entries(value).map(([k, v]) => `${k}：${displayText(v)}`).join("；");
    return value == null ? "" : String(value);
  }
  function safeURL(value) {
    if (!value || typeof value !== "string") return "";
    try {
      const parsed = new URL(value, window.location.origin);
      return ["http:", "https:"].includes(parsed.protocol) ? parsed.href : "";
    } catch { return ""; }
  }
  function projectPath(id, suffix = "") { return `/api/projects/${encodeURIComponent(id)}${suffix}`; }
  function syncFeedbackHost() {
    // Native dialogs occupy the top layer; body z-index cannot cross the backdrop.
    const dialogs = [...document.querySelectorAll("dialog[open]")];
    const host = dialogs.at(-1) || document.body;
    [$("toast-stack"), $("global-busy")].forEach((item) => {
      if (item && item.parentElement !== host) host.append(item);
    });
  }
  function toast(message, type = "success", duration = 6000) {
    syncFeedbackHost();
    const item = node("div", `toast ${type === "error" ? "error" : ""}`, message);
    $("toast-stack").append(item);
    setTimeout(() => item.remove(), duration);
  }
  async function api(path, options = {}) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), options.timeout || 180000);
    try {
      const headers = { Accept: "application/json", ...options.headers };
      const init = { ...options, headers, signal: controller.signal };
      if (options.body !== undefined && typeof options.body !== "string") {
        headers["Content-Type"] = "application/json";
        init.body = JSON.stringify(options.body);
      }
      const response = await fetch(path, init);
      const contentType = response.headers.get("content-type") || "";
      const result = contentType.includes("application/json") ? await response.json() : null;
      if (!response.ok) {
        const detail = result?.detail || result?.message;
        throw new Error(typeof detail === "string" ? detail : detail ? displayText(detail) : `本机服务返回 ${response.status}，请查看终端日志。`);
      }
      if (!result) throw new Error("本机服务返回了无法识别的内容，请检查服务是否已正确启动。");
      return result;
    } catch (error) {
      if (error.name === "AbortError") throw new Error("请求等待时间较长，请到 Agent 工作台查看任务，或检查模型连接后重试。");
      if (error instanceof TypeError) throw new Error("暂时无法连接本机服务，请确认启动窗口仍然开着，然后刷新页面。");
      throw error;
    } finally { clearTimeout(timer); }
  }
  async function action(button, message, operation) {
    if (button?.disabled) return;
    if (button) button.disabled = true;
    if (message) {
      state.busyCount += 1;
      syncFeedbackHost();
      $("global-busy-label").textContent = message;
      $("global-busy").hidden = false;
    }
    try { return await operation(); }
    catch (error) { toast(error.message || "操作未完成，请检查本机服务后重试。", "error", 10000); }
    finally {
      if (button) button.disabled = false;
      if (message) {
        state.busyCount = Math.max(0, state.busyCount - 1);
        $("global-busy").hidden = state.busyCount === 0;
      }
    }
  }
  function errorPanel(container, message, retry) {
    clear(container);
    const box = node("div", "server-error");
    box.append(node("strong", "", "故事屋还没有连接好"), node("p", "", message));
    if (retry) {
      const button = node("button", "button subtle", "重新连接 →");
      button.addEventListener("click", () => action(button, null, retry));
      box.append(button);
    }
    container.append(box);
  }
  function empty(container, icon, title, description, buttonLabel, onClick) {
    clear(container);
    const box = node("div", "empty-state");
    box.append(node("span", "empty-icon", icon), node("h3", "", title), node("p", "", description));
    if (buttonLabel) {
      const button = node("button", "button dark", buttonLabel);
      button.addEventListener("click", onClick);
      box.append(button);
    }
    container.append(box);
  }
  function themeOf(project) { return project.theme || project.inputs?.theme || "forest"; }
  function modeOf(project) { return project.mode === "live" ? "真实 AI 创作" : "本地示例"; }
  function sceneList(project) { return Array.isArray(project?.scenes) ? project.scenes : []; }
  function shortDate(value) {
    if (!value) return "保存在本机";
    const date = new Date(value);
    return Number.isNaN(date.valueOf()) ? "保存在本机" : new Intl.DateTimeFormat("zh-CN", { month: "numeric", day: "numeric", timeZone: "Asia/Shanghai" }).format(date);
  }

  function navigate() {
    const hash = window.location.hash.replace(/^#/, "");
    const view = Object.hasOwn(viewNames, hash) ? hash : "create";
    state.view = view;
    document.querySelectorAll(".view").forEach((item) => { item.hidden = item.id !== `view-${view}`; });
    document.querySelectorAll(".nav-item").forEach((item) => {
      const active = item.dataset.view === view;
      item.classList.toggle("active", active);
      if (active) item.setAttribute("aria-current", "page"); else item.removeAttribute("aria-current");
    });
    $("breadcrumb-current").textContent = viewNames[view];
    $("sidebar").classList.remove("open");
    if (view === "assets") loadAssets().catch((error) => errorPanel($("asset-results"), error.message, loadAssets));
    if (view === "course") loadCourse().catch((error) => errorPanel($("course-checks"), error.message, loadCourse));
    if (view === "bookshelf") renderBooks();
    if (view === "agent" && state.currentJobId) renderJob(state.jobs.get(state.currentJobId));
  }

  function coverFallback(project) {
    const theme = themeOf(project);
    const fallback = node("div", `cover-fallback ${theme}`);
    fallback.append(node("span", "cover-symbol", { forest: "♧", space: "✧", ocean: "≈" }[theme] || "✦"), node("small", "", themeLabels[theme] || "奇妙世界"));
    return fallback;
  }
  function bookCard(project) {
    const card = node("button", "book-card");
    card.type = "button";
    card.setAttribute("aria-label", `阅读《${project.title || "未命名故事"}》`);
    const cover = node("div", "book-cover");
    const imageURL = safeURL(project.cover_url || sceneList(project).find((scene) => scene.image_url)?.image_url);
    if (imageURL) {
      const image = node("img");
      image.src = imageURL;
      image.alt = `${project.title || "故事"}的绘本封面`;
      image.loading = "lazy";
      image.addEventListener("error", () => image.replaceWith(coverFallback(project)), { once: true });
      cover.append(image);
    } else { cover.append(coverFallback(project)); }
    cover.append(node("span", "book-badge", modeOf(project)));
    const body = node("div", "book-body");
    body.append(node("h3", "", project.title || "一段奇妙的冒险"));
    const meta = node("div", "book-meta");
    meta.append(node("span", "", `${project.inputs?.name || "小主角"}的冒险 · ${sceneList(project).length} 个场景`), node("span", "", shortDate(project.created_at)));
    const tags = node("div", "book-tags");
    tags.append(node("span", "book-tag", themeLabels[themeOf(project)] || "自选主题"));
    if (project.audio_url) tags.append(node("span", "book-tag", "♫ 有声绘本"));
    if (project.video_url) tags.append(node("span", "book-tag", "▷ 绘本视频"));
    body.append(meta, tags);
    card.append(cover, body);
    card.addEventListener("click", () => action(null, "正在翻开故事书……", () => openReader(project.id)));
    return card;
  }
  function renderBooks() {
    $("book-count").textContent = String(state.projects.length);
    $("bookshelf-total").textContent = `共 ${state.projects.length} 本故事`;
    const recent = clear($("recent-books"));
    const all = clear($("all-books"));
    const query = $("book-search").value.trim().toLowerCase();
    const selected = state.projects.filter((project) => `${project.title} ${project.inputs?.name || ""} ${themeLabels[themeOf(project)] || ""}`.toLowerCase().includes(query));
    state.projects.slice(0, 3).forEach((project) => recent.append(bookCard(project)));
    selected.forEach((project) => all.append(bookCard(project)));
    if (!state.projects.length) {
      empty(recent, "✧", "第一本故事，正等着你", "选一个喜欢的世界，为你的小主角种下一颗故事种子。", "开始第一本故事 →", () => $("creation-section").scrollIntoView({ behavior: "smooth" }));
      empty(all, "▤", "你的书架会从这里长大", "创作的故事和生成的音画都会保存在本机。", "创作新故事 →", () => { window.location.hash = "create"; });
    } else if (!selected.length) empty(all, "⌕", "还没有找到这本书", "试试故事名称、小主角名字，或者森林、海洋、太空。", "清除搜索", () => { $("book-search").value = ""; renderBooks(); });
    updateAgentProjects();
    updateHeroCover();
  }
  function updateHeroCover() {
    const url = safeURL("/files/library/images/character-cute-v6-eyes.png");
    if (!url) return;
    const art = document.querySelector(".hero-art");
    let image = art.querySelector(".hero-seed-image");
    if (!image) {
      image = node("img", "hero-seed-image");
      image.alt = "圆脸、大眼睛、绿色围巾的可爱小狐狸";
      image.addEventListener("error", () => { art.classList.remove("has-seed"); image.remove(); });
      art.prepend(image);
    }
    if (image.src !== url) image.src = url;
    art.classList.add("has-seed");
    art.setAttribute("aria-label", "圆脸、大眼睛、绿色围巾的可爱小狐狸");
  }
  async function refreshProjects() {
    const result = await api("/api/projects");
    state.projects = Array.isArray(result.projects) ? result.projects : [];
    renderBooks();
    return state.projects;
  }
  async function refreshStatus() {
    const result = await api("/api/status", { timeout: 20000 });
    state.status = result;
    const badge = $("connection-status");
    badge.classList.remove("offline");
    badge.replaceChildren(node("span"), document.createTextNode(result.ready === false ? "本机服务已连接" : "本机服务已就绪"));
    return result;
  }
  function upsertProject(project) {
    if (!project?.id) return;
    const index = state.projects.findIndex((item) => item.id === project.id);
    if (index < 0) state.projects.unshift(project); else state.projects[index] = project;
    renderBooks();
  }
  function updatePreview() {
    $("preview-name").textContent = $("child-name").value.trim() || "小主角";
    $("preview-title").textContent = themeTitles[state.theme];
    $("preview-title").style.whiteSpace = "pre-line";
    const colors = { forest: ["#e5e9d3", "#607047", "♧"], space: ["#e7e1ed", "#82708f", "✧"], ocean: ["#deebea", "#668e8c", "≈"] }[state.theme];
    const cover = document.querySelector(".preview-book");
    cover.style.background = colors[0];
    $("preview-title").style.color = colors[1];
    document.querySelector(".preview-tree").textContent = colors[2];
    document.querySelector(".preview-tree").style.color = colors[1];
  }
  function selectTheme(theme) {
    if (!Object.hasOwn(themeLabels, theme)) return;
    state.theme = theme;
    document.querySelectorAll(".theme-card").forEach((button) => {
      button.classList.toggle("selected", button.dataset.theme === theme);
      button.setAttribute("aria-pressed", String(button.dataset.theme === theme));
    });
    updatePreview();
  }
  function selectMode(mode) {
    state.mode = mode === "live" ? "live" : "demo";
    $("image-provider").addEventListener("change", () => { $("wan-settings").hidden = $("image-provider").value !== "wan"; });
  $("wan-model").addEventListener("change", () => { $("wan-free-confirmed").checked = false; });
  $("check-image-settings").addEventListener("click", () => action($("check-image-settings"), "正在检查本机配置……", async () => {
    await saveSettings();
    const result = await api("/api/settings/check-image", {method:"POST",body:{}});
    $("settings-test-result").hidden = false;
    $("settings-test-result").classList.remove("error");
    $("settings-test-result").textContent = result.message;
  }));
  document.querySelectorAll("[data-mode]").forEach((button) => {
      button.classList.toggle("active", button.dataset.mode === state.mode);
      button.setAttribute("aria-pressed", String(button.dataset.mode === state.mode));
    });
    $("mode-description").textContent = state.mode === "demo" ? "本地模板与程序插画示例，可直接体验；不会调用大模型。" : "使用你配置的免费模型真实生成文字与插画；需要有效密钥和网络连接。";
  }
  async function createProject() {
    const data = new FormData($("create-form"));
    const result = await api("/api/projects", { method: "POST", body: {
      name: String(data.get("name") || "小栗").trim(), age: Number(data.get("age")) || 6, audience_age: Number(data.get("audience_age")) || 6,
      interest: String(data.get("interest") || "").trim(), setting: String(data.get("setting") || "").trim(),
      length: data.get("length"), strategy: data.get("strategy"), theme: state.theme, mode: state.mode,
    } });
    if (!result.project?.id) throw new Error("服务未返回有效故事，请查看本机终端。");
    upsertProject(result.project);
    toast(state.mode === "demo" ? "本地示例故事已创建，接下来可以生成插画和有声书。" : "你的专属 AI 故事已完成，翻开看看吧。 ");
    await openReader(result.project.id, result.project);
    refreshStatus().catch(() => {});
  }

  function showDialog(dialog) {
    if (!dialog.open) dialog.showModal();
    syncFeedbackHost();
  }
  async function openReader(id, prefetched) {
    const project = prefetched || (await api(projectPath(id))).project;
    if (!project) throw new Error("没有找到这本故事。");
    $("story-audio").pause();
    state.project = project;
    state.sceneIndex = 0;
    state.selectedSegment = null;
    state.audioScope = null;
    renderReader();
    showDialog($("reader"));
    document.querySelector(".reader-center").scrollTop = 0;
  }
  function renderReader() {
    const project = state.project;
    if (!project) return;
    $("reader-title").textContent = project.title || "一段奇妙的冒险";
    $("reader-mode").textContent = modeOf(project);
    $("reader-moral").textContent = project.moral ? `✧ ${project.moral}` : "";
    $("download-pdf").href = projectPath(project.id, "/book.pdf");
    $("download-zip").href = projectPath(project.id, "/export.zip");
    const navigation = clear($("scene-navigation"));
    sceneList(project).forEach((scene, index) => {
      const button = node("button", "scene-nav-button");
      button.append(node("span", "", String(index + 1).padStart(2, "0")), document.createTextNode(scene.title || `第 ${index + 1} 个场景`));
      button.addEventListener("click", () => goToScene(index, true));
      navigation.append(button);
    });
    const characters = clear($("character-list"));
    (project.characters || []).forEach((character) => {
      const card = node("div", "character-card");
      card.append(node("strong", "", `${character.name || "故事伙伴"}${character.role ? ` · ${character.role}` : ""}`));
      if (character.traits) card.append(node("p", "", displayText(character.traits)));
      if (character.appearance) card.append(node("p", "", displayText(character.appearance)));
      characters.append(card);
    });
    if (!characters.children.length) characters.append(node("p", "help-text", "这本书还没有角色档案。"));
    const videoURL = safeURL(project.video_url);
    $("reader-video-wrap").hidden = !videoURL;
    if (videoURL && $("story-video").getAttribute("src") !== videoURL) $("story-video").src = videoURL;
    if (!videoURL) $("story-video").removeAttribute("src");
    state.sceneIndex = Math.min(state.sceneIndex, Math.max(0, sceneList(project).length - 1));
    renderScene();
    updateReaderJob();
  }
  function configureAudio() {
    const project = state.project;
    const scene = sceneList(project)[state.sceneIndex];
    const fullURL = safeURL(project?.audio_url);
    const sceneURL = safeURL(scene?.audio_url);
    const url = fullURL || sceneURL;
    const audio = $("story-audio");
    state.audioScope = fullURL ? "full" : sceneURL ? "scene" : null;
    audio.hidden = !url;
    $("audio-title").textContent = url ? fullURL ? "完整有声绘本 · 多角色朗读" : `这一页的声音 · 第 ${state.sceneIndex + 1} 页` : "让故事读给你听";
    $("audio-hint").textContent = url ? "播放时将根据真实配音时间轴高亮文字。点击文字也可跳转到对应朗读位置。" : "点击上方“生成有声书”，完成后在这里播放并同步查看朗读文字。";
    if (url && audio.getAttribute("src") !== url) {
      audio.pause();
      audio.src = url;
      audio.load();
    } else if (!url && audio.hasAttribute("src")) {
      audio.pause();
      audio.removeAttribute("src");
      audio.load();
    }
  }
  function localSegments(scene) {
    return Array.isArray(scene?.segments) ? scene.segments : [];
  }
  function fullSegments() {
    if (Array.isArray(state.project?.segments) && state.project.segments.length) return state.project.segments;
    let offset = 0;
    const all = [];
    sceneList(state.project).forEach((scene, sceneIndex) => {
      const segments = localSegments(scene);
      segments.forEach((segment) => all.push({ ...segment, scene_index: sceneIndex, start: offset + (Number(segment.start) || 0), end: offset + (Number(segment.end) || 0) }));
      offset += Number(scene.duration) || Math.max(0, ...segments.map((segment) => Number(segment.end) || 0));
    });
    return all;
  }
  function segmentTime(segment, index) {
    if (state.audioScope !== "full") return Number(segment.start) || 0;
    const all = fullSegments();
    const global = all.filter((item) => Number(item.scene_index) === state.sceneIndex);
    if (global[index]) return Number(global[index].start) || 0;
    const scenes = sceneList(state.project);
    const offset = scenes.slice(0, state.sceneIndex).reduce((sum, item) => sum + (Number(item.duration) || 0), 0);
    return offset + (Number(segment.start) || 0);
  }
  function renderScene() {
    const scenes = sceneList(state.project);
    const scene = scenes[state.sceneIndex];
    clear($("scene-text"));
    clear($("scene-dialogues"));
    if (!scene) {
      $("scene-title").textContent = "故事页还没有准备好";
      $("scene-text").textContent = "你可以先修改故事，补充场景后再继续制作绘本。";
      $("previous-scene").disabled = true;
      $("next-scene").disabled = true;
      $("scene-counter").textContent = "0 / 0";
      $("scene-image").hidden = true;
      $("scene-image-wrap").classList.add("no-image");
      configureAudio();
      return;
    }
    $("scene-number").textContent = `CHAPTER ${String(state.sceneIndex + 1).padStart(2, "0")} / ${String(scenes.length).padStart(2, "0")}`;
    $("scene-title").textContent = scene.title || `第 ${state.sceneIndex + 1} 页`;
    const imageURL = safeURL(scene.image_url);
    const image = $("scene-image");
    image.hidden = !imageURL;
    $("scene-image-wrap").classList.toggle("no-image", !imageURL);
    image.alt = scene.description || scene.title || "本页绘本插画";
    image.onerror = () => { image.hidden = true; $("scene-image-wrap").classList.add("no-image"); $("scene-image-note").textContent = "插画文件暂不可用，可重新生成"; };
    if (imageURL) image.src = imageURL; else image.removeAttribute("src");
    $("scene-image-note").textContent = imageURL ? state.project.mode === "live" ? "AI 配图 · 请核对角色一致性" : "本地程序插画示例" : "";
    const segments = localSegments(scene);
    if (segments.length) {
      segments.forEach((segment, index) => {
        const paragraph = node("p", "segment-paragraph");
        const isNarrator = !segment.character || /旁白|narrator/i.test(segment.character);
        if (!isNarrator) paragraph.append(node("strong", "segment-character", `${segment.character}：`));
        const span = node("span", "text-segment", segment.text || "");
        span.dataset.segmentIndex = String(index);
        span.tabIndex = 0;
        span.setAttribute("role", "button");
        span.setAttribute("aria-label", `朗读${isNarrator ? "旁白" : segment.character}：${segment.text || ""}`);
        const seek = () => {
          const audio = $("story-audio");
          if (!audio.src) return;
          audio.currentTime = segmentTime(segment, index);
          audio.play().catch(() => toast("请使用下方音频播放器开始朗读。"));
        };
        span.addEventListener("click", seek);
        span.addEventListener("keydown", (event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); seek(); } });
        paragraph.append(span);
        $("scene-text").append(paragraph);
      });
    } else {
      $("scene-text").textContent = scene.text || scene.description || "";
      (scene.dialogues || []).forEach((row) => {
        if (!row.text) return;
        if ((scene.text || "").includes(row.text)) return;
        const paragraph = node("p", "dialogue");
        paragraph.append(node("strong", "", `${row.character || "旁白"}：`), document.createTextNode(row.text));
        $("scene-dialogues").append(paragraph);
      });
    }
    $("scene-counter").textContent = `${String(state.sceneIndex + 1).padStart(2, "0")} / ${String(scenes.length).padStart(2, "0")}`;
    $("previous-scene").disabled = state.sceneIndex === 0;
    $("next-scene").disabled = state.sceneIndex === scenes.length - 1;
    document.querySelectorAll(".scene-nav-button").forEach((button, index) => button.classList.toggle("active", index === state.sceneIndex));
    configureAudio();
    state.selectedSegment = null;
    syncAudio({ follow: false });
  }
  function goToScene(index, seek = false) {
    if (!state.project || index < 0 || index >= sceneList(state.project).length) return;
    state.sceneIndex = index;
    renderScene();
    if (seek && state.audioScope === "full") {
      const segment = fullSegments().find((item) => Number(item.scene_index) === index);
      if (segment) $("story-audio").currentTime = Number(segment.start) || 0;
    }
    document.querySelector(".reader-center").scrollTop = 0;
  }
  function syncAudio({ follow = true } = {}) {
    if (!state.project) return;
    const audio = $("story-audio");
    const time = audio.currentTime;
    let active = -1;
    let nextScene = state.sceneIndex;
    if (state.audioScope === "full") {
      const timeline = fullSegments();
      const match = timeline.find((item) => time >= Number(item.start) && time < Number(item.end));
      if (match) {
        nextScene = Number(match.scene_index) || 0;
        const inScene = timeline.filter((item) => Number(item.scene_index) === nextScene);
        active = inScene.indexOf(match);
      }
    } else {
      active = localSegments(sceneList(state.project)[state.sceneIndex]).findIndex((item) => time >= Number(item.start) && time < Number(item.end));
    }
    if (nextScene !== state.sceneIndex && !audio.paused && follow) {
      state.sceneIndex = nextScene;
      renderScene();
    }
    const key = `${state.sceneIndex}:${active}`;
    if (state.selectedSegment === key) return;
    state.selectedSegment = key;
    $("scene-text").querySelectorAll(".text-segment").forEach((span, index) => {
      span.classList.toggle("playing", index === active);
      if (index === active) span.setAttribute("aria-current", "true"); else span.removeAttribute("aria-current");
    });
  }
  async function refreshCurrentProject(id) {
    const result = await api(projectPath(id));
    if (!result.project) return;
    upsertProject(result.project);
    if (state.project?.id === id) {
      state.project = result.project;
      renderReader();
    }
  }
  async function launchProjectJob(kind, button) {
    if (!state.project) return;
    const id = state.project.id;
    return action(button, "正在创建任务……", async () => {
      const result = await api(projectPath(id, `/${kind}`), { method: "POST", body: {} });
      if (!result.job_id) throw new Error("本机服务未返回任务编号。");
      startTracking(result.job_id, id);
      toast(`${{ images: "插画", audio: "有声书", video: "绘本视频" }[kind]}任务已提交，实际进度会在这里更新。`);
    });
  }

  function updateAgentProjects() {
    const select = $("agent-project");
    const previous = select.value;
    clear(select);
    if (!state.projects.length) {
      select.append(node("option", "", "先创作一本故事，再启动助手"));
      select.firstElementChild.value = "";
    } else {
      state.projects.forEach((project) => {
        const option = node("option", "", `${project.title || "未命名故事"} · ${modeOf(project)}`);
        option.value = project.id;
        select.append(option);
      });
      if (state.projects.some((item) => item.id === previous)) select.value = previous;
    }
    $("start-agent").disabled = !state.projects.length;
    $("prompt-compare").disabled = !state.projects.length;
  }
  function saveJobs() {
    try {
      const ids = [...state.jobs.values()].filter((job) => !terminal.has(job.status)).map((job) => ({ id: job.id, project_id: job.project_id }));
      localStorage.setItem("storysprout-active-jobs", JSON.stringify(ids));
    } catch { /* The app remains usable when browser storage is unavailable. */ }
  }
  function startTracking(id, projectId, restored = false) {
    const job = state.jobs.get(id) || { id, project_id: projectId, status: "queued", progress: 0, steps: [], logs: [] };
    state.jobs.set(id, job);
    state.currentJobId = id;
    saveJobs();
    renderJob(job);
    updateReaderJob();
    if (!state.timers.has(id)) pollJob(id, restored);
  }
  async function pollJob(id, restored = false) {
    if (state.timers.has(id)) { clearTimeout(state.timers.get(id)); state.timers.delete(id); }
    try {
      const previous = state.jobs.get(id);
      const job = await api(`/api/jobs/${encodeURIComponent(id)}`, { timeout: 30000 });
      state.jobs.set(id, job);
      if (state.currentJobId === id) renderJob(job);
      updateReaderJob();
      updateActivity();
      saveJobs();
      if (terminal.has(job.status)) {
        if (previous?.status !== job.status && !restored) {
          toast(job.status === "completed" ? "创作任务已完成，作品内容已更新。" : `任务未完成：${job.error || "请查看执行日志"}`, job.status === "failed" ? "error" : "success", 9000);
        }
        await Promise.allSettled([refreshCurrentProject(job.project_id), refreshStatus()]);
        if (state.view === "course") loadCourse().catch(() => {});
      } else {
        if (job.status === "paused" && previous?.status !== "paused") {
          toast("故事已完成并暂停，前往 Agent 工作台审阅和介入。", "success", 9000);
          refreshCurrentProject(job.project_id).catch(() => {});
        }
        state.timers.set(id, setTimeout(() => pollJob(id), job.status === "paused" ? 3500 : 1500));
      }
    } catch (error) {
      if (restored && /404|没有找到|不存在|未找到/.test(error.message)) {
        state.jobs.delete(id);
        if (state.currentJobId === id) state.currentJobId = null;
        saveJobs();
        updateActivity();
        return;
      }
      const job = state.jobs.get(id);
      if (job) job.connectionError = error.message;
      if (state.currentJobId === id) renderJob(job);
      state.timers.set(id, setTimeout(() => pollJob(id, restored), 5000));
    }
  }
  function updateActivity() {
    $("activity-dot").hidden = ![...state.jobs.values()].some((job) => !terminal.has(job.status));
  }
  function renderJob(job) {
    if (!job) return;
    $("agent-empty").hidden = true;
    $("agent-job").hidden = false;
    $("agent-status").textContent = statusLabels[job.status] || job.status;
    $("agent-status").className = `status-chip ${job.status || ""}`;
    const progress = Math.max(0, Math.min(100, Number(job.progress) || 0));
    $("job-progress-value").textContent = `${progress}%`;
    $("job-progress-bar").style.width = `${progress}%`;
    const project = state.projects.find((item) => item.id === job.project_id);
    $("job-progress-label").textContent = project ? `《${project.title}》` : "任务进度";
    const steps = clear($("job-steps"));
    (job.steps || []).forEach((step, index) => {
      steps.append(node("span", `job-step ${step.status || ""}`, `${step.status === "completed" ? "✓" : step.status === "running" ? "◌" : String(index + 1).padStart(2, "0")} ${step.name || step.tool || "执行步骤"}`));
    });
    const logs = $("job-logs");
    const wasNearBottom = logs.scrollTop + logs.clientHeight >= logs.scrollHeight - 35;
    clear(logs);
    (job.logs || []).forEach((entry) => {
      const row = node("div", "log-line");
      if (typeof entry === "string") row.append(node("span", "log-time", "—"), node("span", "", entry));
      else {
        let time = entry.time || "";
        const parsed = new Date(time);
        if (time && !Number.isNaN(parsed.valueOf())) time = new Intl.DateTimeFormat("zh-CN", { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false, timeZone: "Asia/Shanghai" }).format(parsed);
        row.append(node("span", "log-time", time || "—"), node("span", "", entry.message || displayText(entry)));
      }
      logs.append(row);
    });
    if (!logs.children.length) logs.append(node("p", "", "任务已提交，等待服务返回执行日志。"));
    if (wasNearBottom) logs.scrollTop = logs.scrollHeight;
    $("job-error").hidden = !(job.error || job.connectionError);
    $("job-error").textContent = job.error || (job.connectionError ? `连接暂时中断，正在重新获取真实状态：${job.connectionError}` : "");
    $("job-intervention").hidden = job.status !== "paused";
    const resultBox = clear($("job-result"));
    resultBox.hidden = !terminal.has(job.status);
    if (job.status === "completed") {
      resultBox.append(node("strong", "", "✓ 这一轮创作已完成"));
      if (job.result) {
        if (typeof job.result === "string") resultBox.append(node("p", "", job.result));
        else {
          const summary = job.result.message || job.result.summary;
          if (summary) resultBox.append(node("p", "", displayText(summary)));
          const report = job.result.comparisons || job.result.results || job.result;
          if (!summary || job.result.comparisons || job.result.results) resultBox.append(node("pre", "job-json", JSON.stringify(report, null, 2)));
        }
      }
      if (job.project_id) {
        const read = node("button", "button dark", "打开更新后的绘本 ↗");
        read.addEventListener("click", () => action(read, "正在打开绘本……", () => openReader(job.project_id)));
        resultBox.append(read);
      }
    } else if (job.status === "failed") resultBox.append(node("p", "", "已保留完成的作品与执行日志。根据上方错误调整配置或故事内容后，可以重新启动对应操作。"));
    if (job.project_id && [...$("agent-project").options].some((option) => option.value === job.project_id)) $("agent-project").value = job.project_id;
  }
  function updateReaderJob() {
    if (!state.project) return;
    const jobs = [...state.jobs.values()].filter((job) => job.project_id === state.project.id);
    const job = jobs.find((item) => !terminal.has(item.status)) || jobs.at(-1);
    $("reader-job").hidden = !job;
    if (!job) return;
    const step = (job.steps || []).find((item) => item.status === "running");
    $("reader-job-status").textContent = `${statusLabels[job.status] || job.status}${step ? ` · ${step.name}` : ""} · ${Math.max(0, Math.min(100, Number(job.progress) || 0))}%${job.error ? ` · ${job.error}` : ""}`;
    $("reader-job-details").dataset.jobId = job.id;
  }
  async function startAgent() {
    const projectId = $("agent-project").value;
    if (!projectId) throw new Error("请先创作一本故事，再启动创作助手。");
    const result = await api(projectPath(projectId, "/agent"), { method: "POST", body: { instruction: $("agent-instruction").value.trim(), pause_after_story: $("agent-pause").checked } });
    if (!result.job_id) throw new Error("本机服务未返回任务编号。");
    startTracking(result.job_id, projectId);
    toast("创作助手已启动，下面将据实展示执行日志。");
  }
  async function intervene() {
    if (!state.currentJobId) throw new Error("请先启动一个任务。");
    const instruction = $("intervention-text").value.trim();
    if (!instruction) throw new Error("先写下你希望调整的内容，再保存介入指令。");
    await api(`/api/jobs/${encodeURIComponent(state.currentJobId)}/intervene`, { method: "POST", body: { instruction } });
    $("intervention-text").value = "";
    toast("调整指令已保存，将在后续执行前处理。");
    await pollJob(state.currentJobId);
  }

  async function loadAssets() {
    const requestId = ++state.assetRequest;
    const query = $("asset-query").value.trim();
    const container = $("asset-results");
    if (!container.children.length) container.append(node("div", "loading-state", "正在寻找灵感……"));
    const result = await api(`/api/assets?q=${encodeURIComponent(query)}&type=${encodeURIComponent(state.assetType)}`);
    if (requestId !== state.assetRequest) return;
    const countText = result.counts ? `${result.counts.templates || 0} 个模板 · ${result.counts.images || 0} 张插画 · ${result.counts.sounds || 0} 段声音` : "";
    $("asset-engine").textContent = `${result.engine || "本机素材检索"}${result.clip_ready ? " · CLIP 语义检索已就绪" : " · 以本机实际检索引擎为准"}${countText ? `　${countText}` : ""}`;
    clear(container);
    const results = Array.isArray(result.results) ? result.results : [];
    if (!results.length) {
      empty(container, "⌕", "这个灵感还没有找到", "试试更简短的描述，或者切换到“全部素材”。素材仅来自本机素材库。", "看看全部素材", () => { $("asset-query").value = ""; setAssetType("all"); loadAssets().catch((error) => errorPanel(container, error.message, loadAssets)); });
      return;
    }
    results.forEach((asset) => {
      const type = asset.type || "template";
      const card = node("article", "asset-card");
      const url = safeURL(asset.url);
      if (type === "image" && url) {
        const image = node("img", "asset-image");
        image.src = url; image.alt = asset.title || "绘本插画素材"; image.loading = "lazy";
        image.addEventListener("error", () => image.replaceWith(node("div", "asset-icon", "▧")), { once: true });
        card.append(image);
      } else card.append(node("div", `asset-icon ${type}`, type === "sound" || type === "audio" ? "♫" : "▤"));
      const body = node("div", "asset-card-body");
      body.append(node("span", "asset-type", { template: "STORY SEED · 故事模板", image: "ILLUSTRATION · 插画素材", sound: "SOUND · 声音素材", audio: "SOUND · 声音素材" }[type] || "本机素材"), node("h3", "", asset.title || "未命名素材"), node("p", "", asset.description || ""));
      const tags = node("div", "asset-tags");
      (Array.isArray(asset.tags) ? asset.tags : []).slice(0, 5).forEach((tag) => tags.append(node("span", "book-tag", tag)));
      body.append(tags);
      if ((type === "sound" || type === "audio") && url) {
        const audio = node("audio"); audio.controls = true; audio.preload = "none"; audio.src = url;
        body.append(audio);
      } else if (type === "template") {
        const use = node("button", "text-button", "用这颗种子创作 ↗");
        use.type = "button";
        use.addEventListener("click", () => {
          const words = `${asset.title || ""} ${asset.description || ""} ${(asset.tags || []).join(" ")}`;
          const theme = /太空|星际|宇宙|space|planet|star/i.test(words) ? "space" : /海洋|大海|ocean|sea|鲸|珊瑚/i.test(words) ? "ocean" : "forest";
          selectTheme(theme);
          $("story-setting").value = `${asset.title || ""}${asset.description ? `：${asset.description}` : ""}`.slice(0, 180);
          window.location.hash = "create";
          setTimeout(() => $("creation-section").scrollIntoView({ behavior: "smooth" }), 40);
          toast("这颗故事种子已放进创作表单，可以继续添加你的想法。");
        });
        body.append(use);
      } else if (url) {
        const open = node("a", "text-button", "打开原始素材 ↗");
        open.href = url; open.target = "_blank"; open.rel = "noopener noreferrer";
        body.append(open);
      }
      card.append(body); container.append(card);
    });
  }
  function setAssetType(type) {
    state.assetType = type;
    document.querySelectorAll("[data-type]").forEach((button) => button.classList.toggle("active", button.dataset.type === type));
  }
  async function loadCourse() {
    const result = await api("/api/course");
    const checks = clear($("course-checks"));
    (result.checks || []).forEach((check) => {
      const card = node("div", "check-card");
      card.append(node("span", `check-mark ${check.passed ? "passed" : ""}`, check.passed ? "✓" : "·"));
      const body = node("div");
      const isAgentCount = ["两个完整Agent案例", "两个模型Agent成功任务"].includes(check.label);
      const checkTitle = check.label === "文生图API与角色一致性" ? "逐幕文生图API产物" : isAgentCount ? "两个模型Agent成功任务" : check.label || "实践检查";
      const checkDetail = (check.detail || "") + (isAgentCount ? "这里只统计工具运行成功记录，最终成品与所附轨迹的一致性需另行核对。" : "");
      body.append(node("h3", "", checkTitle), node("p", "", checkDetail));
      card.append(body); checks.append(card);
    });
    if (!checks.children.length) empty(checks, "☑", "清单还没有返回", "检查结果以本机服务返回的真实状态为准。", "重新获取", () => action(null, null, loadCourse));
    const weeks = clear($("course-weeks"));
    (result.weeks || []).forEach((week, index) => {
      const row = node("article", "week-row");
      const number = String(week.week || index + 1).replace(/第|周/g, "");
      row.append(node("span", "week-number", number.padStart(2, "0")));
      const body = node("div", "week-body");
      body.append(node("h3", "", week.title || "课程实践"));
      if (Array.isArray(week.details)) {
        const list = node("ul");
        week.details.forEach((detail) => list.append(node("li", "", displayText(detail)))); body.append(list);
      } else body.append(node("p", "", displayText(week.details)));
      const courseLabel = week.status === "completed" ? "技术产物已生成" : Number(week.week) === 8 ? "待现场展示" : "待技术核查";
      row.append(body, node("span", "status-chip", courseLabel));
      weeks.append(row);
    });
    state.courseLoaded = true;
  }

  async function openSettings() {
    await action(null, "正在读取本机设置……", async () => {
      const result = await api("/api/settings");
      $("text-base-url").value = result.text_base_url || "https://open.bigmodel.cn/api/paas/v4";
      $("image-base-url").value = result.image_base_url || "https://open.bigmodel.cn/api/paas/v4";
      if ([...$("text-model").options].some((option) => option.value === result.text_model)) $("text-model").value = result.text_model;
      if ([...$("image-model").options].some((option) => option.value === result.image_model)) $("image-model").value = result.image_model;
      $("image-provider").value = result.image_provider || "cogview";
      $("wan-base-url").value = result.wan_base_url || "https://dashscope.aliyuncs.com";
      $("wan-model").value = result.wan_model || "wan2.7-image-pro";
      $("wan-seed").value = result.wan_seed ?? 20261027;
      $("wan-free-confirmed").checked = Boolean(result.wan_free_tier_confirmed);
      $("wan-api-key").value = "";
      $("wan-key-state").textContent = result.wan_key_set ? "密钥已保存在本机" : "未配置";
      $("wan-settings").hidden = $("image-provider").value !== "wan";
      $("text-api-key").value = ""; $("image-api-key").value = "";
      $("text-key-state").textContent = result.text_key_set ? "密钥已保存在本机" : "未配置";
      $("image-key-state").textContent = result.image_key_set ? "密钥已保存在本机" : "未配置";
      $("text-api-key").placeholder = result.text_key_set ? "已保存密钥；留空保留原值" : "粘贴文字模型的 API Key";
      $("image-api-key").placeholder = result.image_key_set ? "已保存密钥；留空保留原值" : "粘贴图片模型的 API Key";
      $("settings-test-result").hidden = true;
      showDialog($("settings-dialog"));
    });
  }
  async function saveSettings() {
    const result = await api("/api/settings", { method: "POST", body: {
      text_base_url: $("text-base-url").value.trim(), text_model: $("text-model").value,
      text_api_key: $("text-api-key").value.trim(), image_base_url: $("image-base-url").value.trim(),
      image_model: $("image-model").value, image_api_key: $("image-api-key").value.trim(), mode: state.mode, free_only: true,
      image_provider: $("image-provider").value, wan_base_url: $("wan-base-url").value.trim(),
      wan_model: $("wan-model").value, wan_api_key: $("wan-api-key").value.trim(),
      wan_seed: $("wan-seed").value, wan_free_tier_confirmed: $("wan-free-confirmed").checked,
    } });
    $("text-api-key").value = ""; $("image-api-key").value = ""; $("wan-api-key").value = "";
    $("wan-key-state").textContent = result.wan_key_set ? "密钥已保存在本机" : "未配置";
    $("text-key-state").textContent = result.text_key_set ? "密钥已保存在本机" : "未配置";
    $("image-key-state").textContent = result.image_key_set ? "密钥已保存在本机" : "未配置";
    toast("配置已保存到本机，密钥不会在界面中回显。");
    await refreshStatus();
  }
  async function testSettings() {
    const resultBox = $("settings-test-result");
    resultBox.hidden = false;
    resultBox.classList.remove("error");
    resultBox.textContent = "正在测试已保存的免费模型配置……";
    try {
      const result = await api("/api/settings/test", { method: "POST", body: {} });
      resultBox.textContent = result.message || (result.ok ? "连接测试通过。" : "连接测试未通过，请检查模型与密钥。");
      resultBox.classList.toggle("error", !result.ok);
    } catch (error) { resultBox.textContent = error.message; resultBox.classList.add("error"); }
    refreshStatus().catch(() => {});
  }

  document.querySelectorAll("[data-mode]").forEach((button) => button.addEventListener("click", () => selectMode(button.dataset.mode)));
  document.querySelectorAll("[data-theme]").forEach((button) => button.addEventListener("click", () => selectTheme(button.dataset.theme)));
  $("child-name").addEventListener("input", updatePreview);
  $("create-form").addEventListener("submit", (event) => { event.preventDefault(); action($("create-submit"), state.mode === "live" ? "AI 正在认真构思你的故事……" : "正在创建本地示例故事……", createProject); });
  $("quick-experience").addEventListener("click", () => action($("quick-experience"), "正在打开示例绘本……", async () => {
    const demo = state.projects.find((project) => project.mode !== "live" && themeOf(project) === "forest") || state.projects.find((project) => project.mode !== "live");
    if (demo) await openReader(demo.id); else { selectMode("demo"); await createProject(); }
  }));
  $("book-search").addEventListener("input", renderBooks);
  $("mobile-menu").addEventListener("click", () => $("sidebar").classList.toggle("open"));
  document.addEventListener("click", (event) => { if (window.innerWidth <= 760 && !$("sidebar").contains(event.target) && !$("mobile-menu").contains(event.target)) $("sidebar").classList.remove("open"); });
  window.addEventListener("hashchange", navigate);
  $("close-reader").addEventListener("click", () => $("reader").close());
  $("reader").addEventListener("close", () => { $("story-audio").pause(); $("story-video").pause(); });
  document.querySelector(".reader-brand").addEventListener("click", () => $("reader").close());
  $("show-characters").addEventListener("click", () => { $("character-list").hidden = !$("character-list").hidden; });
  $("previous-scene").addEventListener("click", () => goToScene(state.sceneIndex - 1, true));
  $("next-scene").addEventListener("click", () => goToScene(state.sceneIndex + 1, true));
  $("story-audio").addEventListener("timeupdate", syncAudio);
  $("story-audio").addEventListener("seeked", syncAudio);
  $("story-audio").addEventListener("error", () => { if ($("story-audio").hasAttribute("src")) toast("音频文件暂时无法播放，请重新生成有声书或检查文件是否完整。", "error"); });
  $("generate-images").addEventListener("click", () => launchProjectJob("images", $("generate-images")));
  $("generate-audio").addEventListener("click", () => launchProjectJob("audio", $("generate-audio")));
  $("generate-video").addEventListener("click", () => launchProjectJob("video", $("generate-video")));
  $("reader-agent").addEventListener("click", () => { if (state.project) $("agent-project").value = state.project.id; $("reader").close(); window.location.hash = "agent"; });
  $("reader-job-details").addEventListener("click", () => { state.currentJobId = $("reader-job-details").dataset.jobId; renderJob(state.jobs.get(state.currentJobId)); $("reader").close(); window.location.hash = "agent"; });
  $("revise-form").addEventListener("submit", (event) => {
    event.preventDefault();
    const button = $("revise-form").querySelector("button");
    action(button, "正在按你的想法调整故事……", async () => {
      if (!state.project) return;
      const instruction = $("revision-text").value.trim();
      if (!instruction) throw new Error("请先写下希望调整的内容。");
      const result = await api(projectPath(state.project.id, "/revise"), { method: "POST", body: { instruction } });
      if (!result.project) throw new Error("服务没有返回修改后的故事。");
      state.project = result.project; upsertProject(result.project); renderReader(); $("revision-text").value = "";
      toast("故事已修改；文字变化后建议重新生成配图与配音。");
    });
  });
  $("start-agent").addEventListener("click", () => action($("start-agent"), "正在安排创作助手……", startAgent));
  $("prompt-compare").addEventListener("click", () => action($("prompt-compare"), "正在创建策略比较任务……", async () => {
    const projectId = $("agent-project").value;
    if (!projectId) throw new Error("请先选择一本故事。");
    const project = state.projects.find((item) => item.id === projectId);
    const result = await api("/api/prompt-compare", { method: "POST", body: { project_id: projectId, mode: project?.mode || "demo" } });
    if (!result.job_id) throw new Error("本机服务未返回任务编号。");
    startTracking(result.job_id, projectId);
    toast("三种策略比较任务已提交，比较结果与报告将在完成后显示。");
  }));
  $("send-intervention").addEventListener("click", () => action($("send-intervention"), "正在保存介入指令……", intervene));
  $("resume-job").addEventListener("click", () => action($("resume-job"), "正在恢复创作任务……", async () => {
    if (!state.currentJobId) throw new Error("没有可以恢复的任务。");
    if ($("intervention-text").value.trim()) await intervene();
    await api(`/api/jobs/${encodeURIComponent(state.currentJobId)}/resume`, { method: "POST", body: {} });
    await pollJob(state.currentJobId);
    toast("任务已恢复，将继续处理后续步骤。");
  }));
  $("asset-search-form").addEventListener("submit", (event) => { event.preventDefault(); action($("asset-search-form").querySelector("button"), null, loadAssets); });
  document.querySelectorAll("[data-type]").forEach((button) => button.addEventListener("click", () => { setAssetType(button.dataset.type); action(button, null, loadAssets); }));
  ["open-settings", "open-settings-side", "open-settings-bottom"].forEach((id) => $(id).addEventListener("click", openSettings));
  $("close-settings").addEventListener("click", () => $("settings-dialog").close());
  $("settings-dialog").addEventListener("close", () => { $("text-api-key").value = ""; $("image-api-key").value = ""; });
  $("settings-form").addEventListener("submit", (event) => { event.preventDefault(); action($("save-settings"), "正在保存本机设置……", saveSettings); });
  $("test-settings").addEventListener("click", () => action($("test-settings"), null, testSettings));
  document.querySelectorAll("dialog").forEach((dialog) => dialog.addEventListener("close", () => {
    // Covers button close, Escape and programmatic close; never leave notices hidden.
    [$("toast-stack"), $("global-busy")].forEach((item) => { if (item) document.body.append(item); });
    syncFeedbackHost();
  }));
  document.addEventListener("keydown", (event) => {
    if (!$("reader").open || ["INPUT", "TEXTAREA", "SELECT", "AUDIO", "VIDEO"].includes(document.activeElement?.tagName)) return;
    if (event.key === "ArrowLeft") { event.preventDefault(); goToScene(state.sceneIndex - 1, true); }
    if (event.key === "ArrowRight") { event.preventDefault(); goToScene(state.sceneIndex + 1, true); }
  });

  async function init() {
    $("child-name").value = "小栗";
    document.querySelector(".hero-seed-image")?.addEventListener("error", (event) => { event.currentTarget.remove(); document.querySelector(".hero-art").classList.remove("has-seed"); }, { once: true });
    updatePreview(); selectMode("demo"); navigate();
    const results = await Promise.allSettled([refreshStatus(), refreshProjects()]);
    if (results[0].status === "rejected") {
      $("connection-status").classList.add("offline");
      $("connection-status").replaceChildren(node("span"), document.createTextNode("本机服务未连接"));
    }
    if (results[1].status === "rejected") {
      errorPanel($("recent-books"), results[1].reason.message, refreshProjects);
      errorPanel($("all-books"), results[1].reason.message, refreshProjects);
    }
    try {
      const jobs = JSON.parse(localStorage.getItem("storysprout-active-jobs") || "[]");
      if (Array.isArray(jobs)) jobs.slice(0, 12).forEach((job) => { if (job?.id && job?.project_id) startTracking(job.id, job.project_id, true); });
    } catch { /* Empty storage is safe. */ }
  }
  init();
})();
