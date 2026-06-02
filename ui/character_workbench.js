let bridge = null;
let previewIsCurrent = false;

const els = {};

document.addEventListener("DOMContentLoaded", () => {
  for (const id of [
    "userName",
    "styleSelect",
    "appearanceTraits",
    "personalityTraits",
    "identityTraits",
    "imagePlaceholder",
    "previewImage",
    "characterName",
    "characterGreeting",
    "characterPersona",
    "statusText",
    "generateButton",
    "applyButton",
    "cancelButton",
  ]) {
    els[id] = document.getElementById(id);
  }

  new QWebChannel(qt.webChannelTransport, (channel) => {
    bridge = channel.objects.characterWorkbench;
    connectBridgeSignals();
    bridge.getInitialState((rawState) => {
      renderInitialState(JSON.parse(rawState));
    });
  });
});

function connectBridgeSignals() {
  bridge.generationStarted.connect(() => {
    setBusy(true);
    previewIsCurrent = false;
    els.applyButton.disabled = true;
    els.statusText.textContent = "正在生成人设和预览图...";
    showPlaceholder("生成中...");
    els.characterName.textContent = "-";
    els.characterGreeting.textContent = "-";
    els.characterPersona.value = "";
  });

  bridge.generationFinished.connect((rawProfile) => {
    setBusy(false);
    const profile = JSON.parse(rawProfile);
    previewIsCurrent = true;
    els.applyButton.disabled = false;
    els.statusText.textContent = "预览已生成，满意后点击“应用角色”。";
    els.characterName.textContent = profile.name || "-";
    els.characterGreeting.textContent = profile.greeting || "-";
    els.characterPersona.value = profile.persona || "";
    if (profile.image_src) {
      els.previewImage.src = profile.image_src;
      els.previewImage.hidden = false;
      els.imagePlaceholder.hidden = true;
    } else {
      showPlaceholder("没有可用预览图");
    }
  });

  bridge.generationFailed.connect((message) => {
    setBusy(false);
    previewIsCurrent = false;
    els.applyButton.disabled = true;
    els.statusText.textContent = `生成失败：${message || "unknown error"}`;
    if (!els.previewImage.src) {
      showPlaceholder("生成失败");
    }
  });

  bridge.previewStale.connect(() => {
    previewIsCurrent = false;
    els.applyButton.disabled = true;
    els.statusText.textContent = "选择已修改，请重新生成预览。";
  });
}

function renderInitialState(state) {
  const options = state.options || {};
  const defaults = state.defaults || {};

  els.userName.value = state.userName || "用户";
  renderStyleSelect(options.styles || [], defaults.style);
  renderChips(els.appearanceTraits, options.appearance_traits || [], defaults.appearance_traits || []);
  renderChips(els.personalityTraits, options.personality_traits || [], defaults.personality_traits || []);
  renderChips(els.identityTraits, options.identity_traits || [], defaults.identity_traits || []);

  els.userName.addEventListener("input", markStale);
  els.styleSelect.addEventListener("change", markStale);
  document.querySelectorAll(".chip input").forEach((input) => {
    input.addEventListener("change", markStale);
  });

  els.generateButton.addEventListener("click", startGeneration);
  els.applyButton.addEventListener("click", () => bridge.applyCharacter());
  els.cancelButton.addEventListener("click", () => bridge.cancel());
}

function renderStyleSelect(styles, defaultStyle) {
  els.styleSelect.innerHTML = "";
  for (const style of styles) {
    const option = document.createElement("option");
    option.value = style;
    option.textContent = style;
    option.selected = style === defaultStyle;
    els.styleSelect.appendChild(option);
  }
}

function renderChips(container, values, defaults) {
  container.innerHTML = "";
  const selected = new Set(defaults);
  for (const value of values) {
    const label = document.createElement("label");
    label.className = "chip";
    const input = document.createElement("input");
    input.type = "checkbox";
    input.value = value;
    input.checked = selected.has(value);
    const span = document.createElement("span");
    span.textContent = value;
    label.append(input, span);
    container.appendChild(label);
  }
}

function selectedValues(container) {
  return Array.from(container.querySelectorAll("input:checked")).map((input) => input.value);
}

function startGeneration() {
  const payload = {
    user_name: els.userName.value.trim() || "用户",
    appearance_traits: selectedValues(els.appearanceTraits),
    personality_traits: selectedValues(els.personalityTraits),
    identity_traits: selectedValues(els.identityTraits),
    style: els.styleSelect.value,
  };
  bridge.startGeneration(JSON.stringify(payload));
}

function markStale() {
  if (!previewIsCurrent) {
    return;
  }
  bridge.markStale();
}

function setBusy(isBusy) {
  els.generateButton.disabled = isBusy;
  els.cancelButton.disabled = isBusy;
  els.userName.disabled = isBusy;
  els.styleSelect.disabled = isBusy;
  document.querySelectorAll(".chip input").forEach((input) => {
    input.disabled = isBusy;
  });
}

function showPlaceholder(text) {
  els.previewImage.hidden = true;
  els.previewImage.removeAttribute("src");
  els.imagePlaceholder.hidden = false;
  els.imagePlaceholder.textContent = text;
}
