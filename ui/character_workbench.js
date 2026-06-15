let bridge = null;
let previewIsCurrent = false;
let activeEmotion = "happy";
let emotionImageSources = {};
let historyCards = [];

const els = {};
const EMOTIONS = ["happy", "angry", "shy", "sad"];
const SINGLE_CHOICE_APPEARANCE_GROUPS = new Set(["发色", "瞳色"]);
const APPEARANCE_STRENGTH_GROUPS = new Set(["整体风格"]);
const DEFAULT_PERSONALITY_STRENGTH = 3;

document.addEventListener("DOMContentLoaded", () => {
  for (const id of [
    "userName",
    "historySelect",
    "loadHistoryButton",
    "styleSelect",
    "appearanceTraits",
    "personalityTraits",
    "imagePlaceholder",
    "previewImage",
    "emotionTabs",
    "characterName",
    "characterGreeting",
    "characterPersona",
    "statusText",
    "generateButton",
    "saveCardButton",
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
    els.saveCardButton.disabled = true;
    els.statusText.textContent = "正在生成人设和四张情感预览图...";
    showPlaceholder("生成中...");
    resetEmotionPreview();
    els.characterName.textContent = "-";
    els.characterGreeting.textContent = "-";
    els.characterPersona.value = "";
  });

  bridge.generationFinished.connect((rawProfile) => {
    setBusy(false);
    const profile = JSON.parse(rawProfile);
    previewIsCurrent = true;
    els.applyButton.disabled = false;
    els.saveCardButton.disabled = false;
    els.statusText.textContent = "预览已生成，满意后点击“应用角色”。";
    els.characterName.textContent = profile.name || "-";
    els.characterGreeting.textContent = profile.greeting || "-";
    els.characterPersona.value = profile.persona || "";
    emotionImageSources = normalizeEmotionImages(profile);
    renderEmotionAvailability();
    if (!showEmotion(activeEmotion)) {
      showPlaceholder("没有可用预览图");
    }
  });

  bridge.generationFailed.connect((message) => {
    setBusy(false);
    previewIsCurrent = false;
    els.applyButton.disabled = true;
    els.saveCardButton.disabled = true;
    els.statusText.textContent = `生成失败：${message || "unknown error"}`;
    if (!els.previewImage.src) {
      showPlaceholder("生成失败");
    }
  });

  bridge.previewStale.connect(() => {
    previewIsCurrent = false;
    els.applyButton.disabled = true;
    els.saveCardButton.disabled = true;
    els.statusText.textContent = "选择已修改，请重新生成预览。";
  });

  bridge.cardSaved.connect((path) => {
    els.statusText.textContent = `角色卡已保存：${path}`;
    bridge.getHistoryCards((rawCards) => {
      renderHistoryCards(JSON.parse(rawCards));
    });
  });

  bridge.cardSaveFailed.connect((message) => {
    els.statusText.textContent = `保存失败：${message || "unknown error"}`;
  });
}

function renderInitialState(state) {
  const options = state.options || {};
  const defaults = state.defaults || {};

  els.userName.value = state.userName || "用户";
  renderHistoryCards(state.historyCards || []);
  renderStyleSelect(options.styles || [], defaults.style);
  renderAppearanceGroups(
    els.appearanceTraits,
    options.appearance_groups || null,
    options.appearance_traits || [],
    defaults.appearance_traits || [],
    defaults.appearance_style_dimensions || {},
  );
  renderTraitControls(
    els.personalityTraits,
    options.personality_traits || [],
    defaults.personality_traits || [],
    defaults.personality_dimensions || {},
    "强度",
  );

  els.userName.addEventListener("input", markStale);
  els.styleSelect.addEventListener("change", markStale);
  bindTraitControlEvents();

  els.generateButton.addEventListener("click", startGeneration);
  els.loadHistoryButton.addEventListener("click", loadSelectedHistory);
  els.saveCardButton.addEventListener("click", () => bridge.saveCharacterCard());
  els.applyButton.addEventListener("click", () => bridge.applyCharacter());
  els.cancelButton.addEventListener("click", () => bridge.cancel());
  els.emotionTabs.querySelectorAll(".emotion-tab").forEach((button) => {
    button.addEventListener("click", () => {
      setActiveEmotion(button.dataset.emotion);
    });
  });
}

function renderHistoryCards(cards) {
  historyCards = Array.isArray(cards) ? cards : [];
  els.historySelect.innerHTML = "";
  const emptyOption = document.createElement("option");
  emptyOption.value = "";
  emptyOption.textContent = historyCards.length ? "选择已保存角色" : "暂无历史角色";
  els.historySelect.appendChild(emptyOption);

  for (const card of historyCards) {
    const option = document.createElement("option");
    option.value = card.path;
    option.textContent = card.name ? `${card.name} · ${card.filename}` : card.filename;
    els.historySelect.appendChild(option);
  }
  els.loadHistoryButton.disabled = true;
  els.historySelect.disabled = !historyCards.length;
  els.historySelect.onchange = () => {
    els.loadHistoryButton.disabled = !els.historySelect.value;
  };
}

function loadSelectedHistory() {
  const path = els.historySelect.value;
  if (!path) {
    return;
  }
  bridge.loadHistoryCard(path);
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

function renderAppearanceGroups(container, groups, fallbackValues, defaults, styleDimensions) {
  container.innerHTML = "";
  const selected = new Set(defaults.map(baseTraitName));
  const normalizedGroups = normalizeAppearanceGroups(groups, fallbackValues);
  let groupIndex = 0;
  for (const [groupName, values] of normalizedGroups) {
    const isSingleChoice = SINGLE_CHOICE_APPEARANCE_GROUPS.has(groupName);
    const usesStrength = APPEARANCE_STRENGTH_GROUPS.has(groupName);
    const details = document.createElement("details");
    details.className = "appearance-folder";
    details.classList.toggle("is-single-choice", isSingleChoice);
    details.classList.toggle("uses-strength", usesStrength);
    details.open = groupIndex < 2 || values.some((value) => selected.has(value));

    const summary = document.createElement("summary");
    const title = document.createElement("span");
    title.textContent = groupName;
    const count = document.createElement("em");
    count.textContent = usesStrength ? "可调" : isSingleChoice ? "单选" : `${values.length} 项`;
    summary.append(title, count);
    details.appendChild(summary);

    const list = document.createElement("div");
    list.className = "chip-list nested";
    if (usesStrength) {
      renderTraitControls(list, values, defaults, styleDimensions, "倾向");
    } else {
      renderChipItems(list, values, selected, {
        inputType: isSingleChoice ? "radio" : "checkbox",
        name: `appearance-${groupIndex}`,
      });
    }
    details.appendChild(list);
    container.appendChild(details);
    groupIndex += 1;
  }
}

function normalizeAppearanceGroups(groups, fallbackValues) {
  if (groups && !Array.isArray(groups) && typeof groups === "object") {
    return Object.entries(groups).filter(([, values]) => Array.isArray(values));
  }
  if (Array.isArray(groups)) {
    return groups
      .map((group) => [group.name || group.title || "外貌", group.values || group.traits || []])
      .filter(([, values]) => Array.isArray(values));
  }
  return [["外貌", fallbackValues || []]];
}

function renderChips(container, values, defaults) {
  container.innerHTML = "";
  const selected = new Set(defaults);
  renderChipItems(container, values, selected);
}

function renderChipItems(container, values, selected, options = {}) {
  const inputType = options.inputType || "checkbox";
  for (const value of values) {
    const label = document.createElement("label");
    label.className = "chip";
    label.classList.toggle("is-radio", inputType === "radio");
    const input = document.createElement("input");
    input.type = inputType;
    if (options.name) {
      input.name = options.name;
    }
    input.value = value;
    input.checked = selected.has(value);
    const span = document.createElement("span");
    span.textContent = value;
    label.append(input, span);
    container.appendChild(label);
  }
}

function renderTraitControls(container, values, defaults, dimensions = {}, strengthLabelText = "强度") {
  container.innerHTML = "";
  const selected = new Set(defaults.map(baseTraitName));
  const strengths = new Map(defaults.map((value) => [baseTraitName(value), traitStrength(value)]));
  for (const [trait, strength] of Object.entries(normalizeTraitDimensions(dimensions))) {
    strengths.set(trait, strength);
  }

  for (const value of values) {
    const item = document.createElement("label");
    item.className = "trait-control";

    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.className = "trait-toggle";
    checkbox.value = value;
    checkbox.checked = selected.has(value);

    const body = document.createElement("span");
    body.className = "trait-body";

    const name = document.createElement("span");
    name.className = "trait-name";
    name.textContent = value;

    const strengthWrap = document.createElement("span");
    strengthWrap.className = "trait-strength";

    const strengthLabel = document.createElement("span");
    strengthLabel.className = "strength-label";
    strengthLabel.textContent = strengthLabelText;

    const slider = document.createElement("input");
    slider.type = "range";
    slider.min = "1";
    slider.max = "5";
    slider.step = "1";
    slider.value = String(strengths.get(value) || DEFAULT_PERSONALITY_STRENGTH);
    slider.disabled = !checkbox.checked;

    const output = document.createElement("output");
    output.textContent = slider.value;

    slider.addEventListener("input", () => {
      output.textContent = slider.value;
    });
    checkbox.addEventListener("change", () => {
      slider.disabled = !checkbox.checked;
      item.classList.toggle("is-selected", checkbox.checked);
    });

    item.classList.toggle("is-selected", checkbox.checked);
    strengthWrap.append(strengthLabel, slider, output);
    body.append(name, strengthWrap);
    item.append(checkbox, body);
    container.appendChild(item);
  }
}

function baseTraitName(value) {
  return String(value || "").replace(/\(强度[1-5]\/5\)$/, "");
}

function traitStrength(value) {
  const match = String(value || "").match(/\(强度([1-5])\/5\)$/);
  return match ? Number(match[1]) : DEFAULT_PERSONALITY_STRENGTH;
}

function normalizeTraitDimensions(dimensions) {
  if (!dimensions) {
    return {};
  }
  if (Array.isArray(dimensions)) {
    return Object.fromEntries(
      dimensions
        .filter((item) => item && item.trait)
        .map((item) => [item.trait, clampStrength(item.strength)]),
    );
  }
  if (typeof dimensions === "object") {
    return Object.fromEntries(
      Object.entries(dimensions).map(([trait, strength]) => [trait, clampStrength(strength)]),
    );
  }
  return {};
}

function clampStrength(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) {
    return DEFAULT_PERSONALITY_STRENGTH;
  }
  return Math.min(5, Math.max(1, Math.round(number)));
}

function selectedValues(container) {
  return Array.from(container.querySelectorAll("input:checked")).map((input) => baseTraitName(input.value));
}

function selectedPersonalityValues(container) {
  return Array.from(container.querySelectorAll(".trait-control")).flatMap((item) => {
    const checkbox = item.querySelector(".trait-toggle");
    if (!checkbox || !checkbox.checked) {
      return [];
    }
    return [baseTraitName(checkbox.value)];
  });
}

function selectedTraitDimensions(container) {
  return Array.from(container.querySelectorAll(".trait-control")).flatMap((item) => {
    const checkbox = item.querySelector(".trait-toggle");
    if (!checkbox || !checkbox.checked) {
      return [];
    }
    const slider = item.querySelector(".trait-strength input");
    const strength = slider ? clampStrength(slider.value) : DEFAULT_PERSONALITY_STRENGTH;
    return [[baseTraitName(checkbox.value), strength]];
  });
}

function startGeneration() {
  const payload = {
    user_name: els.userName.value.trim() || "用户",
    appearance_traits: selectedValues(els.appearanceTraits),
    personality_traits: selectedPersonalityValues(els.personalityTraits),
    identity_traits: [],
    personality_dimensions: Object.fromEntries(selectedTraitDimensions(els.personalityTraits)),
    appearance_style_dimensions: Object.fromEntries(
      selectedTraitDimensions(els.appearanceTraits).filter(([trait]) => APPEARANCE_STRENGTH_GROUPS.size && trait),
    ),
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

function normalizeEmotionImages(profile) {
  const images = {};
  const emotionImages = profile.emotion_images || {};
  for (const emotion of EMOTIONS) {
    const image = emotionImages[emotion];
    if (typeof image === "string") {
      images[emotion] = image;
    } else if (image && image.image_src) {
      images[emotion] = image.image_src;
    }
  }
  if (profile.image_src && !Object.keys(images).length) {
    images.happy = profile.image_src;
  }
  return images;
}

function setActiveEmotion(emotion) {
  if (!EMOTIONS.includes(emotion)) {
    return;
  }
  activeEmotion = emotion;
  renderEmotionAvailability();
  if (!showEmotion(emotion)) {
    showPlaceholder("这个情感还没有预览图");
  }
}

function showEmotion(emotion) {
  const src = emotionImageSources[emotion];
  if (!src) {
    return false;
  }
  els.previewImage.src = src;
  els.previewImage.hidden = false;
  els.imagePlaceholder.hidden = true;
  els.imagePlaceholder.textContent = "";
  return true;
}

function renderEmotionAvailability() {
  els.emotionTabs.querySelectorAll(".emotion-tab").forEach((button) => {
    const emotion = button.dataset.emotion;
    button.classList.toggle("is-active", emotion === activeEmotion);
    button.classList.toggle("is-missing", !emotionImageSources[emotion]);
  });
}

function resetEmotionPreview() {
  activeEmotion = "happy";
  emotionImageSources = {};
  renderEmotionAvailability();
}

function setBusy(isBusy) {
  els.generateButton.disabled = isBusy;
  els.saveCardButton.disabled = isBusy || !previewIsCurrent;
  els.cancelButton.disabled = isBusy;
  els.userName.disabled = isBusy;
  els.styleSelect.disabled = isBusy;
  document.querySelectorAll(".chip input, .trait-control input").forEach((input) => {
    input.disabled = isBusy;
  });
  if (!isBusy) {
    document.querySelectorAll(".trait-control").forEach((item) => {
      const checkbox = item.querySelector(".trait-toggle");
      const slider = item.querySelector(".trait-strength input");
      if (checkbox && slider) {
        slider.disabled = !checkbox.checked;
      }
    });
  }
}

function showPlaceholder(text) {
  els.previewImage.hidden = true;
  els.previewImage.removeAttribute("src");
  els.imagePlaceholder.hidden = false;
  els.imagePlaceholder.textContent = text;
}

function bindTraitControlEvents() {
  document.querySelectorAll(".chip input, .trait-toggle").forEach((input) => {
    input.addEventListener("change", markStale);
  });
  document.querySelectorAll(".trait-strength input").forEach((input) => {
    input.addEventListener("change", markStale);
  });
}
