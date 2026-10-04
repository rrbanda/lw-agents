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
