/* اتزان — نماذج تسجيل الدخول وإنشاء الحساب */
(() => {
  "use strict";
  const AFTER_AUTH = "/app";

  async function send(path, body) {
    const res = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Requested-With": "itizan" },
      body: JSON.stringify(body),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || "حدث خطأ، يُرجى المحاولة مرة أخرى.");
    return data;
  }

  function bind(formId, errId, path, fields) {
    const form = document.getElementById(formId);
    if (!form) return;
    const err = document.getElementById(errId);
    form.addEventListener("submit", async (ev) => {
      ev.preventDefault();
      err.hidden = true;
      const body = {};
      fields.forEach((f) => (body[f] = form.elements[f].value));
      const btn = form.querySelector("button[type=submit]");
      btn.disabled = true;
      try {
        await send(path, body);
        window.location.assign(AFTER_AUTH);
      } catch (e) {
        err.textContent = e.message;
        err.hidden = false;
        btn.disabled = false;
      }
    });
  }

  bind("loginForm", "loginError", "/api/login", ["username", "password"]);
  bind("registerForm", "registerError", "/api/register", ["display_name", "username", "password"]);
})();
