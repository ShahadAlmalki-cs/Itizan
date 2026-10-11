/* اتزان — قائمة الصفحة الرئيسية على الشاشات الضيقة */
(() => {
  "use strict";
  const toggle = document.getElementById("navToggle");
  const nav = document.getElementById("topnav");
  if (!toggle || !nav) return;
  const setOpen = (open) => {
    nav.classList.toggle("is-open", open);
    toggle.setAttribute("aria-expanded", String(open));
  };
  toggle.addEventListener("click", () => setOpen(!nav.classList.contains("is-open")));
  nav.addEventListener("click", (ev) => { if (ev.target.closest("a")) setOpen(false); });
  document.addEventListener("click", (ev) => { if (!ev.target.closest(".topbar")) setOpen(false); });
  document.addEventListener("keydown", (ev) => { if (ev.key === "Escape") setOpen(false); });
})();
