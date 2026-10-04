const root = document.documentElement;
const key = "lw-domain-theme";
const toggle = document.getElementById("theme-toggle");
const saved = localStorage.getItem(key);
if (saved === "dark" || saved === "light") {
  root.setAttribute("data-theme", saved);
}

function labelTheme() {
  const dark = root.getAttribute("data-theme") === "dark";
  toggle.textContent = dark ? "Light theme" : "Dark theme";
}

labelTheme();
toggle.addEventListener("click", () => {
  const next = root.getAttribute("data-theme") === "dark" ? "light" : "dark";
  root.setAttribute("data-theme", next);
  localStorage.setItem(key, next);
  labelTheme();
});

const filter = document.getElementById("nav-filter");
filter.addEventListener("input", () => {
  const query = filter.value.trim().toLowerCase();
  document.querySelectorAll(".nav a").forEach((link) => {
    const show = !query || link.textContent.toLowerCase().includes(query);
    link.hidden = !show;
  });
});

const navToggle = document.getElementById("nav-toggle");
navToggle.addEventListener("click", () => {
  const open = document.body.classList.toggle("nav-open");
  navToggle.setAttribute("aria-expanded", String(open));
});

document.querySelectorAll(".nav a").forEach((link) => {
  link.addEventListener("click", () => {
    document.body.classList.remove("nav-open");
    navToggle.setAttribute("aria-expanded", "false");
  });
});

function initLifecycle() {
  const stage = document.querySelector(".lifecycle-stage");
  if (!stage) return;
  const tabs = [...stage.querySelectorAll('[role="tab"]')];
  const panels = [...stage.querySelectorAll(".phase-panel")];
  const progress = stage.querySelector(".phase-progress > span");
  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (!tabs.length) return;

  function centerTab(tab) {
    const track = stage.querySelector(".phase-track");
    const left = tab.offsetLeft - (track.clientWidth - tab.offsetWidth) / 2;
    track.scrollTo({ left: Math.max(0, left), behavior: reduce ? "auto" : "smooth" });
  }

  function select(index, options = {}) {
    const next = (index + tabs.length) % tabs.length;
    tabs.forEach((tab, tabIndex) => {
      const on = tabIndex === next;
      tab.setAttribute("aria-selected", String(on));
      tab.tabIndex = on ? 0 : -1;
    });
    panels.forEach((panel, panelIndex) => {
      panel.hidden = panelIndex !== next;
    });
    if (progress) progress.style.width = `${((next + 1) / tabs.length) * 100}%`;
    centerTab(tabs[next]);
    if (options.focus) tabs[next].focus();
    if (options.hash) history.replaceState(null, "", `#${panels[next].id}`);
    if (options.fromHash) {
      stage.scrollIntoView({ block: "nearest", behavior: reduce ? "auto" : "smooth" });
    }
  }

  tabs.forEach((tab, index) => {
    tab.addEventListener("click", () => select(index, { hash: true }));
    tab.addEventListener("keydown", (event) => {
      const key = event.key;
      if (!["ArrowRight", "ArrowLeft", "Home", "End"].includes(key)) return;
      event.preventDefault();
      if (key === "ArrowRight") select(index + 1, { focus: true, hash: true });
      if (key === "ArrowLeft") select(index - 1, { focus: true, hash: true });
      if (key === "Home") select(0, { focus: true, hash: true });
      if (key === "End") select(tabs.length - 1, { focus: true, hash: true });
    });
  });

  stage.querySelectorAll(".phase-shift").forEach((button) => {
    button.addEventListener("click", () => {
      const current = tabs.findIndex((tab) => tab.getAttribute("aria-selected") === "true");
      const dir = Number(button.getAttribute("data-dir"));
      select((current < 0 ? 0 : current) + dir, { hash: true });
    });
  });

  const fromHash = panels.findIndex((panel) => panel.id === location.hash.slice(1));
  select(fromHash >= 0 ? fromHash : 0, { fromHash: fromHash >= 0 });
  window.addEventListener("hashchange", () => {
    const hashed = panels.findIndex((panel) => panel.id === location.hash.slice(1));
    if (hashed >= 0) select(hashed, { fromHash: true });
  });
}

initLifecycle();
