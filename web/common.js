window.FengStudio = (() => {
  const PROJECT_KEY = "feng-studio-project-v1";
  const SESSION_KEY = "feng-studio-script-session-v1";
  const THEME_KEY = "feng-studio-theme";
  let snackbarTimer;

  function $(selector) {
    return document.querySelector(selector);
  }

  async function api(path, options = {}) {
    const response = await fetch(path, {
      headers: { "Content-Type": "application/json", ...(options.headers || {}) },
      ...options,
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(data.detail || `请求失败（${response.status}）`);
    }
    return data;
  }

  function notify(message) {
    const bar = $("#snackbar");
    if (!bar) return;
    bar.textContent = message;
    bar.classList.add("show");
    clearTimeout(snackbarTimer);
    snackbarTimer = setTimeout(() => bar.classList.remove("show"), 3200);
  }

  function setBusy(button, busy, busyText) {
    if (!button.dataset.originalHtml) {
      button.dataset.originalHtml = button.innerHTML;
    }
    button.disabled = busy;
    button.classList.toggle("busy", busy);
    button.innerHTML = busy ? busyText : button.dataset.originalHtml;
  }

  function formatTime(seconds) {
    const total = Math.max(0, Math.round(Number(seconds) || 0));
    const minutes = String(Math.floor(total / 60)).padStart(2, "0");
    const remain = String(total % 60).padStart(2, "0");
    return `${minutes}:${remain}`;
  }

  function loadJson(key, fallback) {
    try {
      return JSON.parse(localStorage.getItem(key)) ?? fallback;
    } catch {
      return fallback;
    }
  }

  function saveJson(key, value) {
    localStorage.setItem(key, JSON.stringify(value));
  }

  function applyTheme() {
    const theme = localStorage.getItem(THEME_KEY) || "light";
    document.documentElement.dataset.theme = theme;
    const toggle = $("#themeButton");
    toggle?.addEventListener("click", () => {
      const next =
        document.documentElement.dataset.theme === "dark" ? "light" : "dark";
      document.documentElement.dataset.theme = next;
      localStorage.setItem(THEME_KEY, next);
    });
  }

  async function loadStatus() {
    const statusRoot = $("#systemStatus");
    if (!statusRoot) return null;
    try {
      const status = await api("/api/status");
      const pills = [
        {
          ready: status.qwen_ready,
          label: status.qwen_ready ? status.model : "缺少 API Key",
        },
        {
          ready: status.tts_ready,
          label: status.tts_ready ? status.voice : "语音模型缺失",
        },
        {
          ready: status.asset_count > 0,
          label: `${status.asset_count} 张素材`,
        },
      ];
      statusRoot.innerHTML = pills
        .map(({ ready, label }, index) => {
          if (
            index === 0 &&
            !ready &&
            document.querySelector("#apiKeyDialog")
          ) {
            return `<button class="status-chip warn status-action" id="openApiKeyDialog" type="button">${label}</button>`;
          }
          return `<span class="status-chip ${ready ? "ready" : "warn"}">${label}</span>`;
        })
        .join("");
      document
        .querySelector("#openApiKeyDialog")
        ?.addEventListener("click", () =>
          document.querySelector("#apiKeyDialog")?.showModal(),
        );
      return status;
    } catch (error) {
      statusRoot.innerHTML = `<span class="status-chip warn">${error.message}</span>`;
      return null;
    }
  }

  applyTheme();

  return {
    $,
    api,
    notify,
    setBusy,
    formatTime,
    loadJson,
    saveJson,
    loadStatus,
    PROJECT_KEY,
    SESSION_KEY,
  };
})();
