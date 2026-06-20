const modal = document.querySelector(".video-modal");
const modalVideo = modal.querySelector("video");
const modalTitle = modal.querySelector("#video-modal-title");
const closeButton = modal.querySelector(".modal-close");
const videoTriggers = document.querySelectorAll("[data-video]");
let activeTrigger = null;
const expressionCharacter = document.querySelector("#expression-character");
const expressionName = document.querySelector("#expression-name");
const expressionCode = document.querySelector("#expression-code");
const expressionLine = document.querySelector("#expression-line");
const expressionTabs = document.querySelectorAll(".expression-tab");
const expressions = {
  happy: {
    name: "开心",
    line: "今天也一起把事情做好吧。",
  },
  angry: {
    name: "生气",
    line: "这件事可不能就这么算了。",
  },
  shy: {
    name: "害羞",
    line: "才、才不是特意为你做的。",
  },
  sad: {
    name: "伤心",
    line: "没关系，让我陪你待一会儿。",
  },
};

function setExpression(expression) {
  const state = expressions[expression];
  if (!state || !expressionCharacter) {
    return;
  }

  expressionCharacter.classList.add("is-changing");
  expressionCharacter.src = `./assets/images/emotions/${expression}.png`;
  expressionCharacter.alt = `角色${state.name}表情差分`;
  expressionName.textContent = state.name;
  expressionCode.textContent = expression.toUpperCase();
  expressionLine.textContent = state.line;

  expressionTabs.forEach((tab) => {
    const isActive = tab.dataset.expression === expression;
    tab.classList.toggle("is-active", isActive);
    tab.setAttribute("aria-selected", String(isActive));
  });

  window.setTimeout(() => {
    expressionCharacter.classList.remove("is-changing");
  }, 180);
}

expressionTabs.forEach((tab) => {
  tab.addEventListener("click", () => setExpression(tab.dataset.expression));
});

function closeVideo() {
  modalVideo.pause();
  modalVideo.removeAttribute("src");
  modalVideo.load();
  modal.close();
  document.body.classList.remove("modal-open");

  if (activeTrigger) {
    activeTrigger.focus();
    activeTrigger = null;
  }
}

videoTriggers.forEach((trigger) => {
  trigger.addEventListener("click", () => {
    activeTrigger = trigger;
    modalTitle.textContent = trigger.dataset.title;
    modalVideo.src = trigger.dataset.video;
    modal.showModal();
    document.body.classList.add("modal-open");
    modalVideo.play().catch(() => {
      // Native controls remain available when browser autoplay policy blocks playback.
    });
  });
});

closeButton.addEventListener("click", closeVideo);

modal.addEventListener("click", (event) => {
  if (event.target === modal) {
    closeVideo();
  }
});

modal.addEventListener("cancel", (event) => {
  event.preventDefault();
  closeVideo();
});

document.querySelector("#current-year").textContent = new Date().getFullYear();
