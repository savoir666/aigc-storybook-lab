(() => {
  const $ = (id) => document.getElementById(id);

  const THEME_LABELS = { forest: "森林探险", space: "太空旅行", ocean: "海洋奇遇" };
  const THEME_EMOJI = { forest: "🌳", space: "🚀", ocean: "🐚" };

  const state = {
    theme: "forest",
    project: null,
    sceneIndex: 0,
    submitting: false,
  };

  function showView(view) {
    ["setup-view", "loading-view", "story-view"].forEach((id) => {
      const el = $(id);
      if (!el) return;
      el.hidden = id !== view;
    });
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function showError(message) {
    const banner = $("error-banner");
    banner.textContent = message || "发生了未知错误，请稍后再试。";
    banner.hidden = false;
  }

  function clearError() {
    const banner = $("error-banner");
    banner.textContent = "";
    banner.hidden = true;
  }

  function selectTheme(theme) {
    if (!THEME_LABELS[theme]) return;
    state.theme = theme;
    document.querySelectorAll(".theme-card").forEach((card) => {
      const pressed = card.dataset.theme === theme;
      card.setAttribute("aria-pressed", String(pressed));
    });
  }

  function displayText(value) {
    if (Array.isArray(value)) return value.map(displayText).join("、");
    if (value && typeof value === "object") {
      return Object.entries(value)
        .map(([k, v]) => `${k}：${displayText(v)}`)
        .join("；");
    }
    return value == null ? "" : String(value);
  }

  function renderCharacters() {
    const list = $("character-list");
    list.replaceChildren();
    const characters = Array.isArray(state.project?.characters) ? state.project.characters : [];
    if (!characters.length) {
      const p = document.createElement("p");
      p.textContent = "故事里的伙伴马上就出现啦。";
      p.style.color = "var(--ink-500)";
      p.style.fontSize = "13px";
      list.append(p);
      return;
    }
    characters.forEach((c) => {
      const card = document.createElement("div");
      card.className = "character-card";
      const name = document.createElement("strong");
      name.textContent = `${c.name || "故事伙伴"}${c.role && c.role !== "character" ? ` · ${c.role}` : ""}`;
      card.append(name);
      if (c.traits) {
        const t = document.createElement("p");
        t.textContent = displayText(c.traits);
        card.append(t);
      }
      if (c.appearance) {
        const a = document.createElement("p");
        a.textContent = displayText(c.appearance);
        card.append(a);
      }
      list.append(card);
    });
  }

  function renderScene() {
    const scenes = Array.isArray(state.project?.scenes) ? state.project.scenes : [];
    const scene = scenes[state.sceneIndex];

    $("scene-counter").textContent = `${String(state.sceneIndex + 1).padStart(2, "0")} / ${String(scenes.length).padStart(2, "0")}`;
    $("prev-btn").disabled = state.sceneIndex === 0;
    $("next-btn").disabled = state.sceneIndex >= scenes.length - 1;

    if (!scene) {
      $("scene-number").textContent = "CHAPTER 00 / 00";
      $("scene-title").textContent = "故事还没有准备好";
      $("scene-mood").hidden = true;
      const body = $("scene-body");
      body.replaceChildren();
      const p = document.createElement("p");
      p.textContent = "请先填写表单并种下一颗故事种子吧。";
      body.append(p);
      return;
    }

    $("scene-number").textContent = `CHAPTER ${String(state.sceneIndex + 1).padStart(2, "0")} / ${String(scenes.length).padStart(2, "0")}`;
    $("scene-title").textContent = scene.title || `第 ${state.sceneIndex + 1} 幕`;

    const mood = $("scene-mood");
    if (scene.mood) {
      mood.textContent = `情绪：${scene.mood}`;
      mood.hidden = false;
    } else {
      mood.hidden = true;
    }

    const body = $("scene-body");
    body.replaceChildren();

    const img = $("scene-image");
    const note = $("scene-image-note");
    img.hidden = true;
    note.hidden = false;
    note.textContent = "这一幕暂时没有插画";
    img.removeAttribute("src");
    const demoTheme = state.project?.inputs?.theme || state.project?.theme || state.theme;
    const sceneArt = state.project?.mode === "demo" && THEME_LABELS[demoTheme] ? `/demo-scenes/${demoTheme}-${String(state.sceneIndex + 1).padStart(2, "0")}.svg?v=2` : scene.image_url;
    if (sceneArt) {
      try {
        const url = new URL(sceneArt, location.origin);
        if (url.origin === location.origin && (url.pathname.startsWith("/files/") || url.pathname.startsWith("/demo-scenes/"))) {
          img.alt = scene.description || scene.title || "故事插画";
          img.onload = () => { img.hidden = false; note.hidden = true; };
          img.onerror = () => { img.hidden = true; note.hidden = false; note.textContent = "插画暂时无法显示，仍可阅读正文"; };
          img.src = url.href;
        }
      } catch (_) { /* Keep the readable placeholder for invalid image URLs. */ }
    }

    // text and dialogues describe the same story; render a single version.
    const dialogues = Array.isArray(scene.dialogues) ? scene.dialogues : [];
    const rows = dialogues.filter(row => row && row.text);
    if (rows.length) {
      rows.forEach(row => {
        const narrator = ["旁白", "叙述者", "narrator"].includes(row.character);
        const line = document.createElement(narrator ? "p" : "div");
        if (narrator) {
          line.textContent = row.text;
        } else {
          line.className = "dialogue-line";
          const strong = document.createElement("strong");
          strong.textContent = `${row.character || "故事伙伴"}：`;
          const span = document.createElement("span");
          span.textContent = row.text;
          line.append(strong, span);
        }
        body.append(line);
      });
    } else {
      const narr = document.createElement("p");
      narr.textContent = scene.text || scene.description || "";
      body.append(narr);
    }
  }

  function renderStory() {
    const project = state.project;
    if (!project) return;

    $("story-title").textContent = project.title || "一段奇妙的冒险";
    $("story-theme-pill").textContent = `${THEME_EMOJI[project.theme || state.theme] || "✨"} ${THEME_LABELS[project.theme || state.theme] || "奇妙世界"}`;
    $("story-mode-chip").textContent = project.mode === "live" ? "真实 AI 创作" : "本地模板 · Demo";

    const moral = $("story-moral");
    if (project.moral) {
      moral.textContent = `✧ ${project.moral}`;
      moral.hidden = false;
    } else {
      moral.hidden = true;
    }

    renderCharacters();
    renderScene();
  }

  async function apiPost(path, body) {
    const response = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(body),
    });
    const contentType = response.headers.get("content-type") || "";
    const result = contentType.includes("application/json") ? await response.json() : null;
    if (!response.ok) {
      const detail = result?.detail || result?.message || `服务返回 HTTP ${response.status}`;
      const message = Array.isArray(detail) ? detail.map(item => `${(item.loc || []).filter(x => x !== "body").join(".")}：${item.msg || "参数有误"}`).join("；") : (typeof detail === "string" ? detail : "提交内容有误，请检查表单。");
      throw new Error(message);
    }
    if (!result) throw new Error("本机服务没有返回有效内容。");
    return result;
  }

  function validateForm(data) {
    const name = (data.name || "").trim();
    if (!name) return "请先填写主角姓名，故事需要一个称呼。";
    if (name.length > 20) return "主角姓名最多 20 个字。";
    if (!Number.isInteger(data.age) || data.age < 3 || data.age > 12) return "主角年龄请填写 3–12 之间的数字。";
    if (!Number.isInteger(data.audience_age) || data.audience_age < 3 || data.audience_age > 12) return "读者年龄请填写 3–12 之间的数字。";
    return null;
  }

  async function handleSubmit(event) {
    event.preventDefault();
    if (state.submitting) return;
    clearError();

    const form = event.currentTarget;
    const nameInput = $("name");
    if (!nameInput.value.trim()) {
      showError("主角姓名是必填项哦，给你的小主角起个名字吧 ✨");
      nameInput.focus();
      return;
    }

    const radio = document.querySelector('input[name="length"]:checked');
    const payload = {
      name: nameInput.value.trim(),
      age: Number($("age").value),
      audience_age: Number($("audience_age").value),
      interest: ($("interest").value || "").trim(),
      setting: ($("setting").value || "").trim(),
      theme: state.theme,
      length: radio ? radio.value : "medium",
      strategy: "role_play",
      mode: "demo",
    };

    const error = validateForm(payload);
    if (error) {
      showError(error);
      return;
    }

    state.submitting = true;
    const btn = $("submit-btn");
    btn.disabled = true;
    btn.querySelector(".submit-text").textContent = "正在准备故事……";

    showView("loading-view");

    try {
      const result = await apiPost("/api/projects", payload);
      if (!result || !result.project) {
        throw new Error("服务没有返回故事，请稍后再试。");
      }
      state.project = result.project;
      state.sceneIndex = 0;
      renderStory();
      showView("story-view");
    } catch (err) {
      showView("setup-view");
      const msg = err && err.message ? err.message : "暂时无法连接本机故事服务，请确认服务窗口仍然开着，然后刷新页面。";
      showError(msg);
    } finally {
      state.submitting = false;
      btn.disabled = false;
      btn.querySelector(".submit-text").textContent = "种下这颗故事种子";
    }
  }

  function nextScene() {
    const scenes = state.project?.scenes || [];
    if (state.sceneIndex < scenes.length - 1) {
      state.sceneIndex += 1;
      renderScene();
    }
  }

  function prevScene() {
    if (state.sceneIndex > 0) {
      state.sceneIndex -= 1;
      renderScene();
    }
  }

  function restart() {
    state.project = null;
    state.sceneIndex = 0;
    showView("setup-view");
    clearError();
  }

  function init() {
    document.querySelectorAll(".theme-card").forEach((card) => {
      card.addEventListener("click", () => selectTheme(card.dataset.theme));
    });

    $("story-form").addEventListener("submit", handleSubmit);
    $("prev-btn").addEventListener("click", prevScene);
    $("next-btn").addEventListener("click", nextScene);
    $("restart-btn").addEventListener("click", restart);

    document.addEventListener("keydown", (e) => {
      if ($("story-view").hidden || !state.project) return;
      if (e.key === "ArrowLeft") prevScene();
      else if (e.key === "ArrowRight") nextScene();
    });

    showView("setup-view");
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
