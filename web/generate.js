document.addEventListener("DOMContentLoaded", () => {
  const {
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
  } = window.FengStudio;

  const state = loadJson(SESSION_KEY, {
    question: "",
    attempt: 0,
    candidates: [],
    activeCandidate: -1,
  });

  const elements = {
    question: $("#questionInput"),
    questionCount: $("#questionCount"),
    generate: $("#generateButton"),
    retry: $("#retryButton"),
    continue: $("#continueButton"),
    empty: $("#emptyState"),
    card: $("#candidateCard"),
    answer: $("#answerEditor"),
    answerCount: $("#answerCount"),
    estimate: $("#durationEstimate"),
    label: $("#candidateLabel"),
    versions: $("#versionSwitcher"),
    apiKeyDialog: $("#apiKeyDialog"),
    apiKeyInput: $("#apiKeyInput"),
    saveApiKey: $("#saveApiKeyButton"),
    closeApiKey: $("#closeApiKeyDialog"),
  };

  function persist() {
    saveJson(SESSION_KEY, state);
  }

  function updateMetrics() {
    const answer = elements.answer.value;
    if (state.activeCandidate >= 0) {
      state.candidates[state.activeCandidate].answer = answer;
      persist();
    }
    const count = answer.replace(/\s/g, "").length;
    elements.answerCount.textContent = `${count} 字`;
    elements.estimate.textContent = `约 ${formatTime(count / 4.6)}`;
  }

  function renderVersions() {
    elements.versions.innerHTML = "";
    state.candidates.forEach((candidate, index) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = `version-button${index === state.activeCandidate ? " active" : ""}`;
      button.textContent = String(index + 1);
      button.title = `候选 ${index + 1}`;
      button.addEventListener("click", () => showCandidate(index));
      elements.versions.appendChild(button);
    });
  }

  function showCandidate(index) {
    state.activeCandidate = index;
    elements.empty.classList.add("hidden");
    elements.card.classList.remove("hidden");
    elements.answer.value = state.candidates[index].answer;
    elements.label.textContent = `候选 ${index + 1}`;
    renderVersions();
    updateMetrics();
    persist();
  }

  async function generate() {
    const question = elements.question.value.trim();
    if (!question) {
      notify("请先输入一个问题。");
      elements.question.focus();
      return;
    }
    state.question = question;
    state.attempt += 1;
    persist();
    setBusy(elements.generate, true, "正在生成…");
    setBusy(elements.retry, true, "正在生成新版本…");
    try {
      const data = await api("/api/generate", {
        method: "POST",
        body: JSON.stringify({ question, attempt: state.attempt }),
      });
      state.candidates.push({ attempt: data.attempt, answer: data.answer });
      showCandidate(state.candidates.length - 1);
      notify(`候选 ${state.candidates.length} 已生成。`);
    } catch (error) {
      state.attempt -= 1;
      persist();
      notify(error.message);
    } finally {
      setBusy(elements.generate, false);
      setBusy(elements.retry, false);
    }
  }

  function continueToProduction() {
    const answer = elements.answer.value.trim();
    if (!answer) {
      notify("当前候选内容为空。");
      return;
    }
    const project = {
      question: state.question,
      answer,
      candidate: state.activeCandidate + 1,
      savedAt: new Date().toISOString(),
    };
    saveJson(PROJECT_KEY, project);
    window.location.href = "/production";
  }

  elements.question.value = state.question || "";
  elements.questionCount.textContent = `${elements.question.value.length} / 500`;
  if (state.candidates.length) {
    const active = Math.min(
      Math.max(state.activeCandidate, 0),
      state.candidates.length - 1,
    );
    showCandidate(active);
  }

  elements.question.addEventListener("input", () => {
    state.question = elements.question.value;
    elements.questionCount.textContent = `${elements.question.value.length} / 500`;
    persist();
  });
  elements.answer.addEventListener("input", updateMetrics);
  elements.generate.addEventListener("click", generate);
  elements.retry.addEventListener("click", generate);
  elements.continue.addEventListener("click", continueToProduction);
  elements.closeApiKey.addEventListener("click", () =>
    elements.apiKeyDialog.close(),
  );
  elements.saveApiKey.addEventListener("click", async () => {
    const apiKey = elements.apiKeyInput.value.trim();
    if (!apiKey) {
      notify("请输入 DASHSCOPE_API_KEY。");
      return;
    }
    setBusy(elements.saveApiKey, true, "正在保存…");
    try {
      await api("/api/settings/qwen", {
        method: "POST",
        body: JSON.stringify({ api_key: apiKey }),
      });
      elements.apiKeyInput.value = "";
      elements.apiKeyDialog.close();
      await loadStatus();
      notify("千问连接配置已保存到当前服务。");
    } catch (error) {
      notify(error.message);
    } finally {
      setBusy(elements.saveApiKey, false);
    }
  });

  loadStatus();
});
