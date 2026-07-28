document.addEventListener("DOMContentLoaded", () => {
  const {
    $,
    api,
    notify,
    setBusy,
    formatTime,
    loadJson,
    loadStatus,
    PROJECT_KEY,
  } = window.FengStudio;

  const project = loadJson(PROJECT_KEY, null);
  const state = {
    project,
    audio: null,
    scenes: [],
    assets: [],
    selectedScene: -1,
  };

  const elements = {
    question: $("#projectQuestion"),
    answer: $("#projectAnswer"),
    version: $("#selectedVersion"),
    tts: $("#ttsButton"),
    ttsProgress: $("#ttsProgress"),
    ttsMessage: $("#ttsMessage"),
    audio: $("#audioPlayer"),
    storyboardEmpty: $("#storyboardEmpty"),
    storyboard: $("#storyboardGrid"),
    sceneCount: $("#sceneCount"),
    assetCount: $("#assetCount"),
    assetStrip: $("#assetStrip"),
    assetDialog: $("#assetDialog"),
    assetDialogGrid: $("#assetDialogGrid"),
    closeDialog: $("#closeAssetDialog"),
    render: $("#renderButton"),
    renderProgress: $("#renderProgress"),
    renderMessage: $("#renderMessage"),
    aspectRatio: $("#aspectRatio"),
    video: $("#videoPlayer"),
  };

  function bindProject() {
    if (!project) {
      elements.tts.disabled = true;
      elements.question.textContent = "尚未采用语录";
      elements.answer.textContent = "请返回语录生成页面，选择一个候选版本。";
      notify("请先采用一个语录候选。");
      return;
    }
    elements.question.textContent = project.question;
    elements.answer.textContent = project.answer;
    elements.version.textContent = `候选 ${project.candidate}`;
  }

  function renderAssets() {
    elements.assetCount.textContent = String(state.assets.length);
    elements.assetStrip.innerHTML = "";
    elements.assetDialogGrid.innerHTML = "";

    state.assets.slice(0, 20).forEach((asset) => {
      const thumb = document.createElement("div");
      thumb.className = "asset-thumb";
      thumb.innerHTML = `
        <img src="${asset.url}" alt="表情包素材 ${asset.id + 1}" loading="lazy" />
        <span>${String(asset.id + 1).padStart(2, "0")}</span>
      `;
      elements.assetStrip.appendChild(thumb);
    });

    state.assets.forEach((asset) => {
      const button = document.createElement("button");
      button.type = "button";
      button.title = asset.filename;
      button.innerHTML = `<img src="${asset.url}" alt="表情包素材 ${asset.id + 1}" loading="lazy" />`;
      button.addEventListener("click", () => {
        if (state.selectedScene < 0) return;
        state.scenes[state.selectedScene].asset_id = asset.id;
        elements.assetDialog.close();
        renderStoryboard();
      });
      elements.assetDialogGrid.appendChild(button);
    });
  }

  function renderStoryboard() {
    elements.storyboard.innerHTML = "";
    state.scenes.forEach((scene, index) => {
      const card = document.createElement("article");
      card.className = "scene-card";
      card.innerHTML = `
        <button class="scene-image-button" type="button" aria-label="更换分镜 ${index + 1} 图片">
          <img src="/api/assets/${scene.asset_id}" alt="分镜 ${index + 1} 表情包" loading="lazy" />
          <span class="replace-chip">点击换图</span>
        </button>
        <div class="scene-body">
          <div class="scene-meta">
            <span>SCENE ${String(index + 1).padStart(2, "0")}</span>
            <span>${formatTime(scene.start_seconds)} · ${scene.duration_seconds.toFixed(1)}s</span>
          </div>
          <textarea aria-label="分镜 ${index + 1} 字幕"></textarea>
        </div>
      `;
      const textarea = card.querySelector("textarea");
      textarea.value = scene.text;
      textarea.addEventListener("input", (event) => {
        state.scenes[index].text = event.target.value;
      });
      card.querySelector(".scene-image-button").addEventListener("click", () => {
        state.selectedScene = index;
        elements.assetDialog.showModal();
      });
      elements.storyboard.appendChild(card);
    });
  }

  async function generateVoice() {
    if (!project) return;
    setBusy(elements.tts, true, "本地模型合成中…");
    elements.ttsProgress.classList.remove("hidden");
    elements.ttsMessage.textContent =
      "正在加载本地模型并生成完整配音，长文通常需要一至三分钟。";
    try {
      const data = await api("/api/tts", {
        method: "POST",
        body: JSON.stringify({
          question: project.question,
          answer: project.answer,
        }),
      });
      state.audio = data;
      elements.audio.src = data.audio_url;
      elements.audio.classList.remove("hidden");
      elements.ttsMessage.textContent = `配音完成 · ${formatTime(data.duration_seconds)} · 文本已备份`;

      const storyboard = await api("/api/storyboard", {
        method: "POST",
        body: JSON.stringify({
          answer: project.answer,
          duration_seconds: data.duration_seconds,
          max_chars: 38,
        }),
      });
      state.scenes = storyboard.scenes;
      elements.storyboardEmpty.classList.add("hidden");
      elements.storyboard.classList.remove("hidden");
      elements.sceneCount.textContent = String(state.scenes.length);
      elements.render.disabled = false;
      elements.renderMessage.textContent =
        "分镜已就绪，可替换图片、修改字幕并生成视频。";
      renderStoryboard();
      notify("配音和初版分镜已经完成。");
    } catch (error) {
      elements.ttsMessage.textContent = error.message;
      notify(error.message);
    } finally {
      setBusy(elements.tts, false);
      elements.ttsProgress.classList.add("hidden");
    }
  }

  async function renderVideo() {
    if (!state.audio || !state.scenes.length) return;
    setBusy(elements.render, true, "正在生成视频…");
    elements.renderProgress.classList.remove("hidden");
    elements.renderMessage.textContent =
      "正在合成表情包、字幕和配音，长视频可能需要几分钟。";
    try {
      const data = await api("/api/render", {
        method: "POST",
        body: JSON.stringify({
          run_id: state.audio.run_id,
          audio_path: state.audio.audio_url,
          topic: project.question,
          aspect_ratio: elements.aspectRatio.value,
          scenes: state.scenes,
        }),
      });
      elements.video.src = data.video_url;
      elements.video.classList.remove("hidden");
      elements.renderMessage.textContent = "视频已生成，可直接播放检查。";
      notify("MP4 已生成。");
    } catch (error) {
      elements.renderMessage.textContent = error.message;
      notify(error.message);
    } finally {
      setBusy(elements.render, false);
      elements.renderProgress.classList.add("hidden");
    }
  }

  async function initialize() {
    bindProject();
    loadStatus();
    try {
      const data = await api("/api/assets");
      state.assets = data.items;
      renderAssets();
    } catch (error) {
      notify(error.message);
    }
  }

  elements.tts.addEventListener("click", generateVoice);
  elements.render.addEventListener("click", renderVideo);
  elements.closeDialog.addEventListener("click", () => elements.assetDialog.close());
  elements.assetDialog.addEventListener("click", (event) => {
    if (event.target === elements.assetDialog) elements.assetDialog.close();
  });

  initialize();
});
