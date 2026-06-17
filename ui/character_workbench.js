let bridge = null;
let previewIsCurrent = false;
let activeEmotion = "happy";
let emotionImageSources = {};
let historyCards = [];
let customAttributes = [];
let latestProfile = null;
const customSelects = new Map();

const els = {};
const EMOTIONS = ["happy", "angry", "shy", "sad"];
const SINGLE_CHOICE_APPEARANCE_GROUPS = new Set(["发色", "瞳色", "发型", "服装"]);
const APPEARANCE_STRENGTH_GROUPS = new Set(["整体风格"]);
const DEFAULT_PERSONALITY_STRENGTH = 3;

const PERSONALITY_META = {
  "傲娇系": {
    description: "嘴硬心软，关心会藏在别扭语气里。",
    quote: "才不是特意来陪你的，只是顺路而已。",
  },
  "三无冷淡系": {
    description: "安静、克制，回应短但稳定可靠。",
    quote: "收到。任务已记录。",
  },
  "呆萌系": {
    description: "反应慢半拍，偶尔天然发言。",
    quote: "咦？刚才那个按钮是会发光的吗？",
  },
  "元气少女系": {
    description: "活力充沛，会主动把气氛点亮。",
    quote: "今天也一起加油吧！",
  },
  "温柔治愈系": {
    description: "耐心陪伴，擅长安慰与鼓励。",
    quote: "慢慢来，我会在这里陪着你。",
  },
  "毒舌系": {
    description: "吐槽精准，但不会真的伤害用户。",
    quote: "这个计划很有勇气，尤其是它还没开始。",
  },
  "害羞内向系": {
    description: "容易脸红，表达关心时很轻声。",
    quote: "那个……如果你需要的话，我可以陪你。",
  },
  "天然系": {
    description: "直觉行动，带一点不自觉的可爱。",
    quote: "欸嘿，好像不小心说出真心话了。",
  },
  "认真优等生系": {
    description: "自律、有条理，会帮你整理任务。",
    quote: "先完成最重要的一项，再休息五分钟。",
  },
  "慵懒系": {
    description: "语气放松，陪伴感轻柔不压迫。",
    quote: "再努力一点点，然后就可以躺平啦。",
  },
};

const STYLE_DESCRIPTIONS = {
  "清纯": "干净柔和，适合邻家感与日常陪伴。",
  "可爱": "圆润甜美，突出亲近感和俏皮表情。",
  "冷淡": "低调清爽，表情克制、气质安静。",
  "优雅": "线条细腻，姿态端正，有精致感。",
  "活泼": "动作轻快，色彩更明亮，元气感更强。",
};

const ATTRIBUTE_CATEGORIES = {
  personality: "性格",
  appearance: "外貌",
  worldview: "世界观",
  other: "其他",
};

document.addEventListener("DOMContentLoaded", () => {
  for (const id of [
    "userName",
    "historySelect",
    "loadHistoryButton",
    "styleSelect",
    "appearanceTraits",
    "appearanceSummary",
    "personalityTraits",
    "personalityCore",
    "personalityAvailable",
    "advancedPanel",
    "customAttributes",
    "customAttributeCategory",
    "customAttributeText",
    "imagePlaceholder",
    "previewImage",
    "emotionTabs",
    "characterName",
    "profileNickname",
    "profileAppearance",
    "profilePersonality",
    "profileCustomAttributes",
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
  setupHistoryDropdown();

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
    latestProfile = null;
    previewIsCurrent = false;
    els.applyButton.disabled = true;
    els.saveCardButton.disabled = true;
    els.statusText.textContent = "正在生成人设和四张情感预览图...";
    showPlaceholder("生成中...", "正在把设定整理成角色立绘。");
    resetEmotionPreview();
    renderProfileCard(null);
  });

  bridge.generationFinished.connect((rawProfile) => {
    setBusy(false);
    const profile = JSON.parse(rawProfile);
    latestProfile = profile;
    syncProfileToForm(profile);
    previewIsCurrent = true;
    els.applyButton.disabled = false;
    els.saveCardButton.disabled = false;
    els.statusText.textContent = "预览已生成，满意后点击“应用角色”。";
    renderProfileCard(profile);
    emotionImageSources = normalizeEmotionImages(profile);
    renderEmotionAvailability();
    if (!showEmotion(activeEmotion)) {
      showPlaceholder("没有可用预览图", "可以先保存角色卡，或重新生成一次。");
    }
  });

  bridge.generationFailed.connect((message) => {
    setBusy(false);
    previewIsCurrent = false;
    els.applyButton.disabled = true;
    els.saveCardButton.disabled = true;
    els.statusText.textContent = `生成失败：${message || "unknown error"}`;
    if (!els.previewImage.src) {
      showPlaceholder("生成失败", "请检查网络或 API key 后再试一次。");
    }
  });

  bridge.previewStale.connect(() => {
    previewIsCurrent = false;
    els.applyButton.disabled = true;
    els.saveCardButton.disabled = true;
    els.statusText.textContent = "选择已修改，请重新生成预览。";
    renderProfileCard(latestProfile);
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
  renderPersonalityPanel(
    options.personality_traits || [],
    defaults.personality_traits || [],
    defaults.personality_dimensions || {},
  );
  customAttributes = normalizeCustomAttributes(defaults.custom_attributes || defaults.customAttributes || []);
  renderCustomAttributes();
  renderAppearanceSummary();
  renderProfileCard(null);

  els.userName.addEventListener("input", handleFormChange);
  els.styleSelect.addEventListener("change", handleFormChange);
  els.customAttributeCategory.addEventListener("change", handleFormChange);
  els.customAttributeText.addEventListener("input", () => {
    renderProfileCard(latestProfile);
    handleFormChange();
  });
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
    syncHistoryDropdown();
  };
  renderHistoryDropdownMenu();
  syncAllCustomSelects();
}

function loadSelectedHistory() {
  const path = els.historySelect.value;
  if (!path) {
    return;
  }
  bridge.loadHistoryCard(path);
}

function historyDropdownElements() {
  return customSelects.get("historySelect") || {};
}

function renderCustomSelectMenu(selectId) {
  const config = customSelects.get(selectId);
  if (!config) {
    return;
  }
  const { select, menu } = config;
  menu.innerHTML = "";
  Array.from(select.options).forEach((option) => {
    const item = document.createElement("button");
    item.type = "button";
    item.className = "custom-select-option";
    item.dataset.value = option.value;
    item.setAttribute("role", "option");
    item.textContent = option.textContent;
    item.addEventListener("click", () => {
      select.value = option.value;
      select.dispatchEvent(new Event("change"));
      closeCustomSelect(selectId);
    });
    menu.appendChild(item);
  });
  syncCustomSelect(selectId);
}

function renderHistoryDropdownMenu() {
  renderCustomSelectMenu("historySelect");
}

function syncCustomSelect(selectId) {
  const config = customSelects.get(selectId);
  if (!config) {
    return;
  }
  const { select, button, menu, placeholder } = config;
  const selectedOption = select.options[select.selectedIndex];
  button.querySelector("span").textContent = selectedOption?.textContent || placeholder;
  button.disabled = select.disabled;
  button.classList.toggle("is-disabled", select.disabled);
  menu.querySelectorAll(".custom-select-option").forEach((item) => {
    const selected = item.dataset.value === select.value;
    item.classList.toggle("is-selected", selected);
    item.setAttribute("aria-selected", selected ? "true" : "false");
  });
  if (select.disabled) {
    closeCustomSelect(selectId);
  }
}

function syncHistoryDropdown() {
  syncCustomSelect("historySelect");
}

function syncAllCustomSelects() {
  customSelects.forEach((_, selectId) => syncCustomSelect(selectId));
}

function closeCustomSelect(selectId) {
  const config = customSelects.get(selectId);
  if (!config) {
    return;
  }
  const { button, menu } = config;
  button.setAttribute("aria-expanded", "false");
  menu.hidden = true;
}

function closeHistoryDropdown() {
  closeCustomSelect("historySelect");
}

function positionCustomSelect(selectId) {
  const config = customSelects.get(selectId);
  if (!config || config.menu.hidden) {
    return;
  }
  const { button, menu } = config;
  const rect = button.getBoundingClientRect();
  const gap = 8;
  const viewportPadding = 12;
  const availableBelow = window.innerHeight - rect.bottom - viewportPadding - gap;
  const availableAbove = rect.top - viewportPadding - gap;
  const openAbove = availableBelow < 180 && availableAbove > availableBelow;
  const maxHeight = Math.max(128, Math.min(232, openAbove ? availableAbove : availableBelow));

  menu.style.width = `${rect.width}px`;
  menu.style.left = `${Math.max(viewportPadding, Math.min(rect.left, window.innerWidth - rect.width - viewportPadding))}px`;
  menu.style.maxHeight = `${maxHeight}px`;
  menu.style.top = openAbove ? "auto" : `${rect.bottom + gap}px`;
  menu.style.bottom = openAbove ? `${window.innerHeight - rect.top + gap}px` : "auto";
}

function positionHistoryDropdown() {
  positionCustomSelect("historySelect");
}

function positionOpenCustomSelects() {
  customSelects.forEach((_, selectId) => positionCustomSelect(selectId));
}

function openCustomSelect(selectId) {
  const config = customSelects.get(selectId);
  if (!config || config.button.disabled) {
    return;
  }
  const { button, menu } = config;
  customSelects.forEach((_, otherSelectId) => {
    if (otherSelectId !== selectId) {
      closeCustomSelect(otherSelectId);
    }
  });
  menu.hidden = false;
  button.setAttribute("aria-expanded", "true");
  positionCustomSelect(selectId);
}

function openHistoryDropdown() {
  openCustomSelect("historySelect");
}

function setupCustomSelect(selectId, buttonId, menuId, placeholder) {
  const select = els[selectId];
  const button = document.getElementById(buttonId);
  const menu = document.getElementById(menuId);
  if (!select || !button || !menu) {
    return;
  }
  if (menu.parentElement !== document.body) {
    document.body.appendChild(menu);
  }
  customSelects.set(selectId, { select, button, menu, placeholder });
  button.addEventListener("click", () => {
    const willOpen = menu.hidden;
    if (willOpen) {
      openCustomSelect(selectId);
    } else {
      closeCustomSelect(selectId);
    }
  });
  button.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      closeCustomSelect(selectId);
    }
  });
  select.addEventListener("change", () => syncCustomSelect(selectId));
  renderCustomSelectMenu(selectId);
}

function setupHistoryDropdown() {
  setupCustomSelect("historySelect", "historySelectButton", "historySelectMenu", "选择已保存角色");
  setupCustomSelect("styleSelect", "styleSelectButton", "styleSelectMenu", "选择立绘风格");
  setupCustomSelect(
    "customAttributeCategory",
    "customAttributeCategoryButton",
    "customAttributeCategoryMenu",
    "性格",
  );
  document.addEventListener("click", (event) => {
    customSelects.forEach(({ button, menu }, selectId) => {
      if (!button.contains(event.target) && !menu.contains(event.target)) {
        closeCustomSelect(selectId);
      }
    });
  });
  window.addEventListener("resize", positionOpenCustomSelects);
  window.addEventListener("scroll", positionOpenCustomSelects, true);
}

function renderStyleSelect(styles, defaultStyle) {
  els.styleSelect.innerHTML = "";
  for (const style of styles) {
    const option = document.createElement("option");
    option.value = style;
    option.textContent = styleLabel(style);
    option.selected = style === defaultStyle;
    els.styleSelect.appendChild(option);
  }
  renderCustomSelectMenu("styleSelect");
}

function styleLabel(style) {
  const labels = {
    anime_desktop_pet: "二次元桌宠",
    live2d_like: "Live2D 感",
  };
  return labels[style] || style;
}

function renderAppearanceGroups(container, groups, fallbackValues, defaults, styleDimensions) {
  container.innerHTML = "";
  const selected = new Set(defaults.map(baseTraitName));
  const normalizedGroups = normalizeAppearanceGroups(groups, fallbackValues);
  let groupIndex = 0;
  for (const [groupName, values] of normalizedGroups) {
    const isSingleChoice = SINGLE_CHOICE_APPEARANCE_GROUPS.has(groupName);
    const usesStrength = APPEARANCE_STRENGTH_GROUPS.has(groupName);
    const section = document.createElement("section");
    section.className = "appearance-section";
    section.dataset.groupName = groupName;

    const header = document.createElement("div");
    header.className = "appearance-section-header";
    const title = document.createElement("div");
    title.className = "appearance-section-title";
    title.textContent = groupName;
    const meta = document.createElement("div");
    meta.className = "appearance-section-meta";
    meta.textContent = usesStrength ? `${values.length} 种风格` : isSingleChoice ? "单选" : `${values.length} 项`;
    header.append(title, meta);
    section.appendChild(header);

    const list = document.createElement("div");
    list.className = "chip-list";
    if (usesStrength) {
      renderStyleDimensionCards(list, values, defaults, styleDimensions);
    } else {
      renderChipItems(list, values, selected, {
        inputType: isSingleChoice ? "radio" : "checkbox",
        name: `appearance-${groupIndex}`,
      });
    }
    section.appendChild(list);
    container.appendChild(section);
    groupIndex += 1;
  }
  bindAppearanceEvents();
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

function renderChipItems(container, values, selected, options = {}) {
  const inputType = options.inputType || "checkbox";
  for (const value of values) {
    const label = document.createElement("label");
    label.className = "chip";
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

function renderStyleDimensionCards(container, values, defaults, dimensions = {}) {
  const selected = new Set(defaults.map(baseTraitName));
  const strengths = new Map(defaults.map((value) => [baseTraitName(value), traitStrength(value)]));
  for (const [trait, strength] of Object.entries(normalizeTraitDimensions(dimensions))) {
    strengths.set(trait, strength);
  }

  for (const value of values) {
    const label = document.createElement("label");
    label.className = "style-card trait-control";
    label.classList.toggle("is-selected", selected.has(value));

    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.className = "trait-toggle";
    checkbox.value = value;
    checkbox.checked = selected.has(value);

    const head = document.createElement("span");
    head.className = "style-card-head";

    const name = document.createElement("span");
    name.className = "style-name";
    name.textContent = value;

    const desc = document.createElement("p");
    desc.className = "style-desc";
    desc.textContent = STYLE_DESCRIPTIONS[value] || "影响整体气质和画面取向。";

    const strength = document.createElement("span");
    strength.className = "style-strength";
    const slider = document.createElement("input");
    slider.type = "range";
    slider.min = "1";
    slider.max = "5";
    slider.step = "1";
    slider.value = String(strengths.get(value) || DEFAULT_PERSONALITY_STRENGTH);
    slider.disabled = !checkbox.checked;
    const output = document.createElement("output");
    output.textContent = `Lv.${slider.value}`;
    slider.addEventListener("input", () => {
      output.textContent = `Lv.${slider.value}`;
    });
    strength.append(slider, output);

    checkbox.addEventListener("change", () => {
      slider.disabled = !checkbox.checked;
      label.classList.toggle("is-selected", checkbox.checked);
      handleFormChange();
    });
    slider.addEventListener("change", handleFormChange);
    head.append(checkbox, name);
    label.append(head, desc, strength);
    container.appendChild(label);
  }
}

function renderPersonalityPanel(values, defaults, dimensions = {}) {
  els.personalityTraits.innerHTML = "";
  els.personalityCore.innerHTML = "";
  els.personalityAvailable.innerHTML = "";
  const selected = new Set(defaults.map(baseTraitName));
  const strengths = new Map(defaults.map((value) => [baseTraitName(value), traitStrength(value)]));
  for (const [trait, strength] of Object.entries(normalizeTraitDimensions(dimensions))) {
    strengths.set(trait, strength);
  }

  for (const value of values) {
    const card = createPersonalityCard(value, selected.has(value), strengths.get(value) || DEFAULT_PERSONALITY_STRENGTH);
    els.personalityTraits.appendChild(card);
  }
  rebuildPersonalitySections();
}

function createPersonalityCard(value, checked, strength) {
  const label = document.createElement("label");
  label.className = "trait-control";

  const checkbox = document.createElement("input");
  checkbox.type = "checkbox";
  checkbox.className = "trait-toggle";
  checkbox.value = value;
  checkbox.checked = checked;

  const body = document.createElement("span");
  body.className = "trait-body";

  const name = document.createElement("span");
  name.className = "trait-name";
  name.textContent = value;

  const meta = PERSONALITY_META[value] || {
    description: "影响她与用户相处时最常出现的语气。",
    quote: "我会按照这个性格陪在你身边。",
  };
  const description = document.createElement("p");
  description.className = "trait-description";
  description.textContent = meta.description;
  const quote = document.createElement("p");
  quote.className = "trait-quote";
  quote.textContent = `“${meta.quote}”`;

  const strengthWrap = document.createElement("span");
  strengthWrap.className = "trait-strength";
  const strengthLabel = document.createElement("span");
  strengthLabel.className = "strength-label";
  strengthLabel.textContent = "强度";
  const slider = document.createElement("input");
  slider.type = "range";
  slider.min = "1";
  slider.max = "5";
  slider.step = "1";
  slider.value = String(strength);
  slider.disabled = !checked;
  const output = document.createElement("output");
  output.textContent = `Lv.${slider.value}`;

  slider.addEventListener("input", () => {
    output.textContent = `Lv.${slider.value}`;
    renderProfileCard(latestProfile);
  });
  slider.addEventListener("change", handleFormChange);
  checkbox.addEventListener("change", () => {
    slider.disabled = !checkbox.checked;
    label.classList.toggle("is-selected", checkbox.checked);
    rebuildPersonalitySections();
    handleFormChange();
  });

  strengthWrap.append(strengthLabel, slider, output);
  body.append(name, description, quote, strengthWrap);
  label.append(checkbox, body);
  label.classList.toggle("is-selected", checked);
  return label;
}

function rebuildPersonalitySections() {
  let coreCount = 0;
  let availableCount = 0;
  for (const card of Array.from(els.personalityTraits.querySelectorAll(".trait-control"))) {
    const checkbox = card.querySelector(".trait-toggle");
    card.classList.toggle("is-selected", checkbox.checked);
    if (checkbox.checked) {
      els.personalityCore.appendChild(card);
      coreCount += 1;
    } else {
      els.personalityAvailable.appendChild(card);
      availableCount += 1;
    }
  }
  ensureEmptyPersonalityState(els.personalityCore, coreCount, "");
  ensureEmptyPersonalityState(els.personalityAvailable, availableCount, "性格已全部启用。");
}

function ensureEmptyPersonalityState(container, count, text) {
  const old = container.querySelector(".personality-empty");
  if (old) {
    old.remove();
  }
  if (count > 0 || !text) {
    return;
  }
  const empty = document.createElement("div");
  empty.className = "personality-empty";
  empty.textContent = text;
  container.appendChild(empty);
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

function setSelectValue(select, value) {
  if (!select || !value) {
    return;
  }
  if (Array.from(select.options).some((option) => option.value === value)) {
    select.value = value;
  }
}

function syncProfileToForm(profile) {
  if (!profile || typeof profile !== "object") {
    return;
  }
  setSelectValue(els.styleSelect, profile.style);
  syncCustomSelect("styleSelect");
  syncAppearanceSelection(profile.appearance_traits || [], profile.appearance_style_dimensions || {});
  syncPersonalitySelection(profile.personality_traits || [], profile.personality_dimensions || {});
  customAttributes = normalizeCustomAttributes(profile.custom_attributes || profile.customAttributes || []);
  renderCustomAttributes();
  renderAppearanceSummary();
}

function syncAppearanceSelection(traits, dimensions = {}) {
  const selected = new Set((Array.isArray(traits) ? traits : []).map(baseTraitName));
  const strengths = normalizeTraitDimensions(dimensions);
  els.appearanceTraits.querySelectorAll(".chip input").forEach((input) => {
    input.checked = selected.has(baseTraitName(input.value));
  });
  els.appearanceTraits.querySelectorAll(".style-card.trait-control").forEach((card) => {
    syncTraitControl(card, selected, strengths);
  });
}

function syncPersonalitySelection(traits, dimensions = {}) {
  const selected = new Set((Array.isArray(traits) ? traits : []).map(baseTraitName));
  const strengths = normalizeTraitDimensions(dimensions);
  document.querySelectorAll(".personality-panel .trait-control").forEach((card) => {
    syncTraitControl(card, selected, strengths);
  });
  rebuildPersonalitySections();
}

function syncTraitControl(card, selected, strengths) {
  const checkbox = card.querySelector(".trait-toggle");
  if (!checkbox) {
    return;
  }
  const trait = baseTraitName(checkbox.value);
  const checked = selected.has(trait);
  checkbox.checked = checked;
  card.classList.toggle("is-selected", checked);
  const slider = card.querySelector("input[type='range']");
  const output = card.querySelector("output");
  if (slider) {
    slider.disabled = !checked;
    slider.value = String(strengths[trait] || DEFAULT_PERSONALITY_STRENGTH);
    if (output) {
      output.textContent = `Lv.${slider.value}`;
    }
  }
}

function selectedValues(container) {
  return Array.from(container.querySelectorAll("input:checked")).map((input) => baseTraitName(input.value));
}

function selectedPersonalityValues(container) {
  const scope = container === els.personalityTraits ? document.querySelector(".personality-panel") : container;
  return Array.from(scope.querySelectorAll(".trait-control")).flatMap((item) => {
    const checkbox = item.querySelector(".trait-toggle");
    if (!checkbox || !checkbox.checked) {
      return [];
    }
    return [baseTraitName(checkbox.value)];
  });
}

function selectedTraitDimensions(container) {
  const scope = container === els.personalityTraits ? document.querySelector(".personality-panel") : container;
  return Array.from(scope.querySelectorAll(".trait-control")).flatMap((item) => {
    const checkbox = item.querySelector(".trait-toggle");
    if (!checkbox || !checkbox.checked) {
      return [];
    }
    const slider = item.querySelector("input[type='range']");
    const strength = slider ? clampStrength(slider.value) : DEFAULT_PERSONALITY_STRENGTH;
    return [[baseTraitName(checkbox.value), strength]];
  });
}

function startGeneration() {
  const attrs = collectCustomAttributes();
  const payload = {
    user_name: els.userName.value.trim() || "用户",
    appearance_traits: selectedValues(els.appearanceTraits),
    personality_traits: selectedPersonalityValues(els.personalityTraits),
    identity_traits: [],
    personality_dimensions: Object.fromEntries(selectedTraitDimensions(els.personalityTraits)),
    appearance_style_dimensions: Object.fromEntries(
      selectedTraitDimensions(els.appearanceTraits).filter(([trait]) => APPEARANCE_STRENGTH_GROUPS.size && trait),
    ),
    customAttributes: attrs,
    custom_attributes: attrs,
    style: els.styleSelect.value,
  };
  bridge.startGeneration(JSON.stringify(payload));
}

function handleFormChange() {
  collectCustomAttributes();
  renderAppearanceSummary();
  renderProfileCard(latestProfile);
  markStale();
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
    showPlaceholder("这个情感还没有预览图", "生成完成后如果缺图，会用开心图作为主要预览。");
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
  els.imagePlaceholder.innerHTML = "";
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
  els.applyButton.disabled = isBusy || !previewIsCurrent;
  els.cancelButton.disabled = isBusy;
  document
    .querySelectorAll(
      "input, select, textarea, .chip input, .trait-control input",
    )
    .forEach((input) => {
      input.disabled = isBusy;
    });
  if (!isBusy) {
    document.querySelectorAll(".trait-control").forEach((item) => {
      const checkbox = item.querySelector(".trait-toggle");
      const slider = item.querySelector("input[type='range']");
      if (checkbox && slider) {
        slider.disabled = !checkbox.checked;
      }
    });
    renderHistoryCards(historyCards);
    els.userName.disabled = false;
    els.styleSelect.disabled = false;
    renderCustomAttributes();
  }
  syncAllCustomSelects();
}

function showPlaceholder(title, detail = "") {
  els.previewImage.hidden = true;
  els.previewImage.removeAttribute("src");
  els.imagePlaceholder.hidden = false;
  els.imagePlaceholder.innerHTML = "";
  const strong = document.createElement("strong");
  strong.textContent = title;
  const span = document.createElement("span");
  span.textContent = detail || "选择外貌与性格后，生成她的第一张预览。";
  els.imagePlaceholder.append(strong, span);
}

function bindAppearanceEvents() {
  document.querySelectorAll("#appearanceTraits .chip input").forEach((input) => {
    input.addEventListener("change", handleFormChange);
  });
}

function renderAppearanceSummary() {
  const values = selectedValues(els.appearanceTraits);
  if (!values.length) {
    els.appearanceSummary.textContent = "选择发色、瞳色和服装，生成你的专属桌宠。";
    return;
  }
  els.appearanceSummary.textContent = values.slice(0, 7).join(" · ");
}

function renderProfileCard(profile) {
  const appearance = selectedValues(els.appearanceTraits);
  const personalityDimensions = Object.fromEntries(selectedTraitDimensions(els.personalityTraits));
  const personality = selectedPersonalityValues(els.personalityTraits).map((trait) => {
    const level = personalityDimensions[trait] || DEFAULT_PERSONALITY_STRENGTH;
    return `${trait.replace(/系$/, "")} Lv.${level}`;
  });
  const attrs = collectCustomAttributes().filter((item) => item.enabled && item.description.trim());
  const nickname = els.userName.value.trim() || "用户";

  els.characterName.textContent = profile?.name || "未生成";
  els.profileNickname.textContent = nickname || "-";
  els.profileAppearance.textContent = appearance.length ? appearance.slice(0, 8).join(" · ") : "等待选择外貌";
  els.profilePersonality.textContent = personality.length ? personality.join(" / ") : "等待选择性格";
  els.profileCustomAttributes.textContent = attrs.length
    ? attrs.map((item) => `${ATTRIBUTE_CATEGORIES[item.category] || "其他"}：${item.description}`).join(" / ")
    : "暂无自定义设定";
  els.characterGreeting.textContent = profile?.greeting || "选择设定后，她会在这里准备第一句问候。";
  els.characterPersona.textContent = profile?.persona || "生成后这里会显示完整角色人设。";
}

function normalizeCustomAttributes(values) {
  if (!Array.isArray(values)) {
    return [];
  }
  const enabledItems = values.filter((item) => item && item.enabled !== false);
  if (!enabledItems.length) {
    return [];
  }
  const first = enabledItems[0] || {};
  const category = ATTRIBUTE_CATEGORIES[first.category] ? first.category : "other";
  const description = enabledItems
    .map((item) => {
      const name = String(item.name || "").trim();
      const text = String(item.description || "").trim();
      return [name, text].filter(Boolean).join("：");
    })
    .filter(Boolean)
    .join("\n");
  return description
    ? [
        {
          id: String(first.id || "custom-setting"),
          name: "自定义设定",
          category,
          intensity: 5,
          description,
          enabled: true,
        },
      ]
    : [];
}

function renderCustomAttributes() {
  const attribute = customAttributes[0] || {};
  els.customAttributeCategory.value = ATTRIBUTE_CATEGORIES[attribute.category] ? attribute.category : "personality";
  els.customAttributeText.value = attribute.description || "";
  syncCustomSelect("customAttributeCategory");
}

function collectCustomAttributes() {
  const description = els.customAttributeText.value.trim();
  if (!description) {
    customAttributes = [];
    return customAttributes;
  }
  const category = ATTRIBUTE_CATEGORIES[els.customAttributeCategory.value] ? els.customAttributeCategory.value : "other";
  customAttributes = [
    {
      id: "custom-setting",
      name: "自定义设定",
      category,
      intensity: 5,
      description,
      enabled: true,
      priority: "highest",
      overrides_base_options: true,
    },
  ];
  return customAttributes;
}

function cryptoRandomId() {
  if (window.crypto && window.crypto.randomUUID) {
    return window.crypto.randomUUID();
  }
  return `attr-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}
