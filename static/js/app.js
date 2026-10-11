/* اتزان — منطق الواجهة: تنقل بين الأقسام + التواصل مع Flask API */
(() => {
  "use strict";

  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
  const VIEWS = ["home", "goals", "challenges", "progress", "account"];
  const LOGIN_URL = "/login";
  const LANDING_URL = "/";
  const DAY_NAMES = ["الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]; // weekday(): Mon=0
  const RING_LEN = 264; // 2πr حيث r=42

  // ---------- أدوات مساعدة ----------
  const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const icon = (name, cls = "ic") => `<svg class="${cls}" aria-hidden="true"><use href="#i-${esc(name)}"/></svg>`;

  async function api(path, method = "GET", body) {
    const res = await fetch(path, {
      method,
      headers: { "X-Requested-With": "itizan", ...(body ? { "Content-Type": "application/json" } : {}) },
      body: body ? JSON.stringify(body) : undefined,
    });
    if (res.status === 401 && !path.startsWith("/api/account")) { window.location.assign(LOGIN_URL); }
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || "حدث خطأ، يُرجى المحاولة مرة أخرى.");
    return data;
  }

  let toastTimer;
  function toast(msg) {
    const t = $("#toast");
    t.textContent = msg;
    t.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => (t.hidden = true), 2600);
  }

  // العدد والمعدود في العربية: 1 واحدة، 2 مثنى، 3-10 جمع قلة، 11 فأكثر مفرد منصوب
  const plural = (n, one, two, few, many) => (n === 1 ? one : n === 2 ? two : n >= 3 && n <= 10 ? few : many);
  const minutesText = (m) => (!m ? "طوال اليوم"
    : Number.isInteger(m) ? plural(m, "دقيقة واحدة", "دقيقتان", `${m} دقائق`, `${m} دقيقة`) : `${m} دقيقة`);
  // gen = true حين يكون العدد مضافاً إليه (مجروراً): «تم حفظ ساعتين» لا «ساعتان»
  const hoursText = (h, gen = false) => (Number.isInteger(h)
    ? plural(h, "ساعة واحدة", gen ? "ساعتين" : "ساعتان", `${h} ساعات`, `${h} ساعة`) : `${h} ساعة`);

  // ---------- التنقل ----------
  function showView(name) {
    if (!VIEWS.includes(name)) name = "home";
    VIEWS.forEach((v) => ($(`#view-${v}`).hidden = v !== name));
    $$(".sidenav a").forEach((a) => a.classList.toggle("is-active", a.dataset.view === name));
    setMenu(false);
    window.scrollTo({ top: 0 });
    loadWho();
    ({ home: loadHome, goals: loadGoals, challenges: loadChallenges, progress: loadProgress, account: loadAccount })[name]();
  }
  const route = () => showView(location.hash.replace("#", ""));
  window.addEventListener("hashchange", route);
  function setMenu(open) {
    $("#sidebar").classList.toggle("is-open", open);
    $("#backdrop").hidden = !open;
    $("#menuBtn").setAttribute("aria-expanded", String(open));
  }
  $("#menuBtn").addEventListener("click", () => setMenu(!$("#sidebar").classList.contains("is-open")));
  $("#backdrop").addEventListener("click", () => setMenu(false));
  $(".sidenav").addEventListener("click", (ev) => { if (ev.target.closest("a")) setMenu(false); });
  document.addEventListener("keydown", (ev) => { if (ev.key === "Escape") setMenu(false); });

  // ---------- الشجرة ----------
  function treeSvg(stage) {
    const sand = "#EAE1C7", mound = "#D9C9A0", navy = "#0B1528", g1 = "#A9BCA5", g2 = "#8FA58C", g3 = "#5F7A5C", coral = "#F6866E";
    const ground = `<ellipse cx="100" cy="178" rx="70" ry="8" fill="#5F7A5C" opacity=".22"/><path d="M50 178q50-28 100 0z" fill="${mound}"/>`;
    const parts = [
      // 0: بذرة
      `<g fill="none" stroke="${g3}" stroke-width="2.5" stroke-linecap="round" stroke-dasharray="1 7" opacity=".7">
         <path d="M100 150V118"/><path d="M100 128c-14-1-22-8-23-20 13 0 22 7 23 20z"/><path d="M100 122c14-1 22-8 23-20-13 0-22 7-23 20z"/>
       </g>
       <ellipse cx="100" cy="160" rx="12" ry="8" fill="${navy}"/><circle cx="105" cy="156.5" r="2.4" fill="${coral}"/>`,
      // 1: نبتة
      `<path d="M100 164V138" stroke="${g3}" stroke-width="3.5" stroke-linecap="round" fill="none"/>
       <path d="M100 146c-16-1-25-9-26-24 15 0 25 9 26 24z" fill="${g2}"/>
       <path d="M100 140c16-1 25-9 26-24-15 0-25 9-26 24z" fill="${g3}"/>`,
      // 2: شتلة
      `<path d="M100 164V104" stroke="${g3}" stroke-width="4" stroke-linecap="round" fill="none"/>
       <path d="M100 152c-18 0-28-9-30-24 17 0 28 9 30 24z" fill="${g2}"/>
       <path d="M100 146c18 0 28-9 30-24-17 0-28 9-30 24z" fill="${g3}"/>
       <path d="M100 126c-14 0-22-7-24-19 13 0 22 7 24 19z" fill="${g1}"/>
       <path d="M100 120c14 0 22-7 24-19-13 0-22 7-24 19z" fill="${g2}"/>
       <path d="M100 106c-6-6-6-14 0-22 6 8 6 16 0 22z" fill="${coral}"/>`,
      // 3: شجيرة
      `<rect x="96" y="140" width="8" height="30" rx="3" fill="${navy}"/>
       <circle cx="78" cy="138" r="20" fill="${g1}"/><circle cx="122" cy="138" r="20" fill="${g3}"/>
       <circle cx="100" cy="122" r="27" fill="${g2}"/><circle cx="90" cy="114" r="9" fill="${g1}" opacity=".7"/>`,
      // 4: شجرة فتية
      `<path d="M94 172V118h12v54z" fill="${navy}"/>
       <path d="M100 142l-20-16M100 134l20-14" stroke="${navy}" stroke-width="5" stroke-linecap="round" fill="none"/>
       <circle cx="66" cy="108" r="24" fill="${g1}"/><circle cx="134" cy="108" r="24" fill="${g3}"/>
       <circle cx="100" cy="82" r="34" fill="${g2}"/><circle cx="100" cy="114" r="24" fill="${g3}"/>
       <circle cx="86" cy="74" r="12" fill="${g1}" opacity=".7"/>`,
      // 5: شجرة مثمرة
      `<path d="M90 174V112h20v62z" fill="${navy}"/>
       <path d="M100 146l-26-20M100 138l26-18" stroke="${navy}" stroke-width="6" stroke-linecap="round" fill="none"/>
       <circle cx="56" cy="102" r="28" fill="${g1}"/><circle cx="144" cy="102" r="28" fill="${g3}"/>
       <circle cx="100" cy="64" r="38" fill="${g2}"/><circle cx="68" cy="76" r="24" fill="${g3}"/>
       <circle cx="132" cy="76" r="24" fill="${g1}"/><circle cx="100" cy="104" r="30" fill="${g2}"/>
       <circle cx="84" cy="52" r="12" fill="${g1}" opacity=".7"/>
       <circle cx="68" cy="94" r="5.5" fill="${coral}"/><circle cx="130" cy="88" r="5.5" fill="${coral}"/>
       <circle cx="100" cy="56" r="5.5" fill="${coral}"/><circle cx="86" cy="114" r="5.5" fill="${coral}"/>
       <circle cx="118" cy="116" r="5.5" fill="${coral}"/><circle cx="50" cy="110" r="5.5" fill="${coral}"/>
       <circle cx="152" cy="108" r="5.5" fill="${coral}"/>`,
    ];
    return `<svg viewBox="0 0 200 200" aria-hidden="true">${ground}${parts[Math.max(0, Math.min(5, stage))]}</svg>`;
  }

  let lastTreeStage = null;

  function renderPath(el, t) {
    el.style.setProperty("--p", String(t.max_stage ? t.stage / t.max_stage : 0));
    el.innerHTML = t.stages.map((x) => `
      <li class="${x.reached ? "reached" : ""} ${x.stage === t.stage ? "current" : ""}" ${x.stage === t.stage ? 'aria-current="step"' : ""}>
        <span class="mini">${treeSvg(x.stage)}</span>
        <span>${esc(x.name)}</span>
      </li>`).join("");
  }

  function sparkle() {
    const scene = $("#treeScene");
    for (let i = 0; i < 7; i++) {
      const sp = document.createElement("span");
      sp.className = "spark";
      sp.style.left = `${30 + Math.random() * 40}%`;
      sp.style.animationDelay = `${i * 70}ms`;
      scene.appendChild(sp);
      setTimeout(() => sp.remove(), 1700);
    }
  }

  function renderTree(t, opts = {}) {
    const art = $("#treeArt");
    const changed = lastTreeStage !== t.stage;
    art.innerHTML = treeSvg(t.stage);
    art.setAttribute("aria-label", `${t.stage_name}. ${t.status_text} ${t.hint}`);
    if (changed) { art.classList.remove("grow-in"); void art.offsetWidth; art.classList.add("grow-in"); }
    lastTreeStage = t.stage;
    // نمو تدريجي داخل المرحلة الواحدة: تكبر الشجرة قليلاً مع كل إنجاز
    art.style.transform = `scale(${(0.84 + 0.16 * t.progress_percent / 100).toFixed(3)})`;

    const resting = t.status === "resting";
    $("#treeCard").classList.toggle("is-resting", resting);
    $("#treeName").textContent = t.stage_name;
    $("#treeChipText").textContent = { new: "في البداية", thriving: "تنمو", resting: "تستريح" }[t.status];
    $("#treeChipIcon").setAttribute("href", resting ? "#i-moon" : "#i-leaf");
    $("#treeChip").title = t.status_text;
    const next = t.stages[t.stage + 1];
    const barPct = next ? Math.min(100, Math.round(t.completed_days / next.need * 100)) : 100;
    $("#treeBarFill").style.width = `${barPct}%`;
    $("#treeBar").setAttribute("aria-valuenow", String(barPct));
    $("#treeCount").textContent = next ? `${t.completed_days}/${next.need}` : `${t.completed_days}`;
    renderPath($("#homePath"), t);
    if (opts.celebrate) sparkle();
  }

  // ---------- الرئيسية ----------
  async function loadHome() {
    try {
      const d = await api("/api/today");
      renderToday(d);
      $("#usageHours").value = d.usage_today === null || d.usage_today === undefined ? "" : d.usage_today;
      $("#usageQuality").value = d.usage_quality_today || "";
      const done = d.week.filter((x) => x.completed).length;
      $("#ringNum").textContent = `${done}/7`;
      $("#ringFg").style.strokeDashoffset = RING_LEN * (1 - done / 7);
      renderTree(await api("/api/tree"));
    } catch (e) { toast(e.message); }
  }

  function renderToday(d) {
    const multi = d.items.length > 1;
    $("#goalsLabel").textContent = multi ? "أهدافي" : "هدفي الحالي";
    $("#goalChips").innerHTML = d.items.map((i) => `<li>${icon(i.goal.icon)}<span>${esc(i.goal.title)}</span></li>`).join("");
    $("#todayLabel").textContent = multi ? `تحديات اليوم (${d.completed_count}/${d.total})` : "تحدي اليوم";
    $("#todayCard").classList.toggle("is-done", d.completed);
    $("#todayList").innerHTML = d.items.map((i) => {
      const c = i.challenge;
      return `
      <li class="today-item ${i.completed ? "is-done" : ""}">
        <span class="today-badge">${icon(c.icon)}</span>
        <div class="today-body">
          ${multi ? `<span class="today-goal">${esc(i.goal.title)}</span>` : ""}
          <h3>${esc(c.title)}</h3>
          <p>${esc(c.description)}</p>
          <div class="today-meta">${icon("clock", "ic ic-sm")}<span>${minutesText(c.minutes)}</span></div>
        </div>
        <div class="today-actions">
          ${i.completed
            ? `<span class="done-pill">${icon("check")}تم إكمال المهمة</span>
               <button class="btn btn-ghost" type="button" data-undo="${esc(i.goal.key)}">${icon("undo")}<span>تراجع</span></button>`
            : `<button class="btn btn-primary" type="button" data-complete="${esc(i.goal.key)}">${icon("check")}<span>أكملتُ المهمة</span></button>`}
        </div>
      </li>`;
    }).join("");
  }

  $("#todayList").addEventListener("click", async (ev) => {
    const done = ev.target.closest("[data-complete]"), undo = ev.target.closest("[data-undo]");
    if (!done && !undo) return;
    try {
      if (done) {
        done.disabled = true;
        const r = await api("/api/today/complete", "POST", { goal_key: done.dataset.complete });
        renderTree(r.tree, { celebrate: r.tree_grew });
        toast(r.already ? "سبق أن أكملتَ هذه المهمة."
          : r.tree_grew ? `أحسنت! نمت شجرتك وصارت ${r.tree.stage_name}.`
          : `أحسنت! حصلت على ${r.points} نقاط.`);
      } else {
        const r = await api("/api/today/undo", "POST", { goal_key: undo.dataset.undo });
        renderTree(r.tree);
        toast("تم التراجع عن إكمال المهمة، وبقيت شجرتك على أعلى مرحلة بلغتها.");
      }
    } catch (e) { toast(e.message); }
    loadHome();
  });

  $("#usageSave").addEventListener("click", async () => {
    const v = $("#usageHours").value;
    try {
      const r = await api("/api/usage", "POST", { hours: v, quality: $("#usageQuality").value || null });
      toast(`تم حفظ ${hoursText(r.hours, true)}.`);
    } catch (e) { toast(e.message); }
  });

  // ---------- أهدافي ----------
  let goalCatalog = [], goalSel = [], goalMax = 3;

  function renderGoals() {
    $("#goalList").innerHTML = goalCatalog.map((g) => {
      const on = goalSel.includes(g.key);
      return `<li><button class="goal-item ${on ? "is-selected" : ""}" type="button" data-key="${esc(g.key)}" aria-pressed="${on}">
        <span class="badge">${icon(g.icon)}</span>
        <span class="label">${esc(g.title)}</span>
        <span class="tick">${icon("check")}</span>
      </button></li>`;
    }).join("");
    $("#goalsCount").textContent = `عدد الأهداف المختارة: ${goalSel.length} من ${goalMax}`;
    $("#goalsSave").disabled = goalSel.length === 0;
  }

  async function loadGoals() {
    try {
      const d = await api("/api/goals");
      goalCatalog = d.goals; goalSel = d.selected.slice(); goalMax = d.max;
      renderGoals();
    } catch (e) { toast(e.message); }
  }

  $("#goalList").addEventListener("click", (ev) => {
    const btn = ev.target.closest(".goal-item");
    if (!btn) return;
    const key = btn.dataset.key;
    if (goalSel.includes(key)) {
      if (goalSel.length === 1) { toast("اختر هدفاً واحداً على الأقل."); return; }
      goalSel = goalSel.filter((k) => k !== key);
    } else {
      if (goalSel.length >= goalMax) { toast(`يمكنك اختيار حتى ${goalMax} أهداف.`); return; }
      goalSel.push(key);
    }
    renderGoals();
  });

  $("#goalsSave").addEventListener("click", async () => {
    try {
      await api("/api/goals", "POST", { goal_keys: goalSel });
      toast("تم حفظ أهدافك.");
      location.hash = "#home";
    } catch (e) { toast(e.message); }
  });

  // ---------- تحدياتي ----------
  function renderWeekStrip(week) {
    return week.map((d) => `
      <li class="${d.completed ? "done" : ""} ${d.is_today ? "today" : ""}">
        <span class="dot">${icon("check")}</span>
        <span>${DAY_NAMES[d.weekday]}</span>
      </li>`).join("");
  }

  async function loadChallenges() {
    try {
      const d = await api("/api/challenges");
      $("#chGoal").textContent = d.groups.map((g) => g.goal.title).join(" · ");
      $("#weekStrip").innerHTML = renderWeekStrip(d.week);
      $("#challengeGroups").innerHTML = d.groups.map((g) => `
        <section class="ch-group" aria-label="${esc(g.goal.title)}">
          <h3 class="section-label group-label">${icon(g.goal.icon)}<span>${esc(g.goal.title)}</span></h3>
          <ul class="challenge-list">
            ${g.challenges.map((c) => `
            <li class="challenge ${c.is_today ? "is-today" : ""}">
              <span class="badge">${icon(c.icon)}</span>
              <div class="body">
                <h4>${esc(c.title)}</h4>
                <p>${esc(c.description)}</p>
              </div>
              ${c.completed
                ? `<span class="btn btn-ghost">${icon("check")}مكتمل</span>`
                : c.is_today
                  ? `<a class="btn btn-primary" href="#home">تحدي اليوم</a>`
                  : `<button class="btn btn-ghost" type="button" data-pick="${c.id}">اختره لليوم</button>`}
            </li>`).join("")}
          </ul>
        </section>`).join("");
    } catch (e) { toast(e.message); }
  }
  $("#challengeGroups").addEventListener("click", async (ev) => {
    const btn = ev.target.closest("[data-pick]");
    if (!btn) return;
    try {
      await api(`/api/challenges/${btn.dataset.pick}/select`, "POST");
      toast("تم اختيار تحدي اليوم.");
      location.hash = "#home";
    } catch (e) { toast(e.message); }
  });

  // ---------- تقدمي ----------
  function renderUsage(u) {
    const max = Math.max(4, ...u.week.map((x) => x.hours || 0));
    $("#usageBars").innerHTML = u.week.map((x) => {
      const h = x.hours === null ? 6 : Math.max(6, Math.round((x.hours / max) * 90));
      return `<div class="bar ${x.hours === null ? "" : "done"}" title="${x.hours === null ? "لم يُسجَّل" : hoursText(x.hours)}">
        <small>${x.hours === null ? "—" : esc(x.hours)}</small>
        <i style="height:${h}px"></i><span>${DAY_NAMES[x.weekday]}</span></div>`;
    }).join("");
    let note = "سجّل ساعاتك يومياً من الصفحة الرئيسية لتظهر المقارنة هنا.";
    if (u.avg_week !== null) {
      note = `متوسط هذا الأسبوع: ${hoursText(u.avg_week)} يومياً.`;
      if (u.avg_prev !== null) {
        const diff = Math.round((u.avg_week - u.avg_prev) * 10) / 10;
        note += diff < 0 ? ` انخفض بمقدار ${hoursText(Math.abs(diff), true)} عن الأسبوع السابق (${hoursText(u.avg_prev)}).`
             : diff > 0 ? ` ارتفع بمقدار ${hoursText(diff, true)} عن الأسبوع السابق (${hoursText(u.avg_prev)}).`
             : ` مطابق للأسبوع السابق (${hoursText(u.avg_prev)}).`;
      }
    }
    if (u.rated_days) note += ` عدد الأيام التي وصفتَ فيها استخدامك بأنه «تصفّح بلا هدف»: ${u.aimless_days} من أصل ${u.rated_days}.`;
    $("#usageNote").textContent = note;
  }

  async function loadProgress() {
    try {
      const d = await api("/api/progress");
      $("#stWeek").textContent = `${d.week_done}/7`;
      $("#stStreak").textContent = d.streak;
      $("#stTotal").textContent = d.total_completed;
      $("#stPoints").textContent = d.points;
      $("#bars").innerHTML = d.week.map((x) => `
        <div class="bar ${x.completed ? "done" : ""}" title="${x.completed ? "مكتمل" : "غير مكتمل"}">
          <i></i><span>${DAY_NAMES[x.weekday]}</span>
        </div>`).join("");
      renderUsage(d.usage);
      renderPath($("#progressPath"), await api("/api/tree"));
      $("#history").innerHTML = d.history.length
        ? d.history.map((h) => `<li><span>${esc(h.title)}</span><span class="muted">${esc(h.day)}</span><span class="pts">+${h.points}</span></li>`).join("")
        : `<li class="empty">لا توجد مهام مكتملة بعد. أكمل أول مهمة لك من الصفحة الرئيسية.</li>`;
    } catch (e) { toast(e.message); }
  }

  // ---------- الحساب ----------
  function loadWho() {
    api("/api/me").then((me) => { $("#whoName").textContent = me.display_name; }).catch(() => {});
  }

  async function loadAccount() {
    try {
      const me = await api("/api/me");
      $("#acName").textContent = me.display_name;
      $("#acUser").textContent = me.username;
      $("#delPass").value = "";
    } catch (e) { toast(e.message); }
  }

  $("#logoutBtn").addEventListener("click", async () => {
    try { await api("/api/logout", "POST"); } finally { window.location.assign(LANDING_URL); }
  });

  $("#deleteBtn").addEventListener("click", async () => {
    const pass = $("#delPass").value;
    if (!pass) { toast("أدخل كلمة المرور للتأكيد."); return; }
    if (!window.confirm("هل أنت متأكد من حذف حسابك وجميع بياناتك نهائياً؟")) return;
    try {
      await api("/api/account/delete", "POST", { password: pass });
      window.location.assign(LANDING_URL);
    } catch (e) { toast(e.message); }
  });


  route();
})();
