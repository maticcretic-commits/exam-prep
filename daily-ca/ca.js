/* Daily Current Affairs — Watch -> Read -> Test.
   Data: ../data/ca-daily/index.json + ../data/ca-daily/YYYY-MM-DD.json
   State (localStorage): ca-lang, ca-answers, ca-progress, ca-revision. */
"use strict";

const $ = (s) => document.querySelector(s);
const LETTERS = ["A", "B", "C", "D"];
const store = {
  get(k, d) { try { const v = localStorage.getItem(k); return v ? JSON.parse(v) : d; } catch (e) { return d; } },
  set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) {} },
};
let lang = store.get("ca-lang", "hi");           // 'hi' | 'hg'
let manifest = null;
let dayData = null;
let curDate = null;
let catFilter = "All";

const answers = store.get("ca-answers", {});   // mcqId -> chosen index
const progress = store.get("ca-progress", {}); // date -> {watched:[ep], read:bool}
const revision = store.get("ca-revision", {}); // mcqId -> {due:'YYYY-MM-DD', stage:n, snap:{...}}

function esc(s) {
  return String(s == null ? "" : s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
function L(hi, hg) { return lang === "hi" ? hi : hg; }
function todayIST() {
  return new Date(Date.now() + 5.5 * 3600 * 1000).toISOString().slice(0, 10);
}
function addDays(iso, n) {
  const d = new Date(iso + "T00:00:00Z");
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
}
function vidUrl(id) { return "https://www.youtube.com/shorts/" + id; }

/* ---------- data ---------- */
async function load() {
  const res = await fetch("../data/ca-daily/index.json", { cache: "no-cache" });
  manifest = await res.json();
  const dates = manifest.days.map((d) => d.date);
  const want = new URLSearchParams(location.search).get("date");
  curDate = want && dates.includes(want) ? want : dates[dates.length - 1];
  await loadDay(curDate);
  renderRevision();
}

async function loadDay(iso) {
  curDate = iso;
  catFilter = "All";
  const res = await fetch("../data/ca-daily/" + iso + ".json", { cache: "no-cache" });
  dayData = await res.json();
  renderDay();
}

/* ---------- rendering ---------- */
function renderDay() {
  const dates = manifest.days.map((d) => d.date);
  const idx = dates.indexOf(curDate);
  const meta = manifest.days[idx];
  $("#dateLabel").textContent = L(meta.date_hi, meta.date_en) + "  📅";
  $("#prevDay").disabled = idx <= 0;
  $("#nextDay").disabled = idx >= dates.length - 1;

  const badge = $("#freshBadge");
  const today = todayIST();
  if (curDate === today) {
    badge.hidden = false;
    badge.className = "fresh ok";
    badge.textContent = L("✅ आज का संस्करण — ताज़ा", "✅ Today's edition — fresh");
  } else if (curDate === dates[dates.length - 1] && curDate < today) {
    badge.hidden = false;
    badge.className = "fresh";
    badge.textContent = L(
      "नवीनतम संस्करण: " + meta.date_hi + " — नए Shorts YouTube पर हर 6 घंटे आते हैं",
      "Latest edition: " + meta.date_en + " — new Shorts publish on YouTube every 6 hours");
  } else {
    badge.hidden = true;
  }

  // calendar drawer
  $("#calDrawer").innerHTML = manifest.days.map((d) =>
    `<button type="button" data-date="${d.date}" class="${d.date === curDate ? "active" : ""}">${esc(L(d.date_hi, d.date_en))}</button>`
  ).join("");
  $("#calDrawer").querySelectorAll("button").forEach((b) =>
    b.addEventListener("click", () => { $("#calDrawer").hidden = true; loadDay(b.dataset.date); }));

  // category chips
  const cats = new Map();
  dayData.episodes.forEach((ep) => ep.capsules.forEach((c) => {
    const key = c.category_en;
    if (!cats.has(key)) cats.set(key, c.category_hi);
  }));
  const chips = ["All", ...cats.keys()];
  $("#catChips").innerHTML = chips.map((c) =>
    `<button type="button" class="tabbtn ${c === catFilter ? "active" : ""}" data-cat="${esc(c)}">${esc(c === "All" ? L("सभी", "All") : L(cats.get(c), c))}</button>`
  ).join("");
  $("#catChips").querySelectorAll("button").forEach((b) =>
    b.addEventListener("click", () => { catFilter = b.dataset.cat; renderDay(); }));

  // episodes
  const body = $("#dayBody");
  body.innerHTML = dayData.episodes.map((ep) => episodeHtml(ep)).join("");
  body.querySelectorAll(".facade").forEach((f) =>
    f.addEventListener("click", () => playVideo(f), { once: true }));
  body.querySelectorAll(".opts").forEach((box) =>
    box.querySelectorAll(".opt").forEach((btn) =>
      btn.addEventListener("click", () => answerMcq(box, btn))));
  updateMission();
  observeRead();
}

function episodeHtml(ep) {
  const vid = lang === "hi" ? ep.video_hi : ep.video_hinglish;
  let h = `<section class="episode"><div class="ephead"><h3>${L("एपिसोड", "Episode")} ${ep.episode}</h3>` +
    `<span class="chip dim">${esc(L(dayData.date_hi, dayData.date_en))}</span></div>`;
  if (vid) {
    h += `<div class="watchwrap"><div class="facade" data-vid="${esc(vid)}" data-ep="${ep.episode}" role="button" aria-label="Watch Episode ${ep.episode}">` +
      `<img src="https://i.ytimg.com/vi/${esc(vid)}/hqdefault.jpg" alt="Episode ${ep.episode} Short thumbnail" loading="lazy">` +
      `<div class="play"><span>▶</span></div></div></div>`;
  }
  const caps = ep.capsules.filter((c) => catFilter === "All" || c.category_en === catFilter);
  h += caps.map((c) =>
    `<article class="card capcard"><div class="qmeta"><span class="chip">${esc(L(c.category_hi, c.category_en))}</span></div>` +
    `<h4>${esc(L(c.headline_hi, c.headline_hinglish))}</h4><p>${esc(L(c.detail_hi, c.detail_hinglish))}</p></article>`
  ).join("");
  if (ep.mcq) h += mcqHtml(ep.mcq, ep.episode);
  return h + "</section>";
}

function mcqHtml(m, epNo) {
  const chosen = answers[m.id];
  const done = chosen !== undefined;
  const opts = (lang === "hi" ? m.options_hi : m.options_hinglish).map((o, i) => {
    let cls = "opt";
    if (done) {
      if (i === m.answer_index) cls += " correct";
      else if (i === chosen) cls += " wrong";
      else cls += " dimmed";
    }
    return `<button type="button" class="${cls}" data-i="${i}" ${done ? "disabled" : ""}>` +
      `<span class="olet">${LETTERS[i]}</span><span>${esc(o)}</span></button>`;
  }).join("");
  let verdict = "";
  if (done) {
    const ok = chosen === m.answer_index;
    const correctText = (lang === "hi" ? m.options_hi : m.options_hinglish)[m.answer_index];
    verdict = `<p class="verdict ${ok ? "good" : "bad"}">${ok ? L("✅ सही जवाब!", "✅ Correct!") : L("❌ ग़लत — सही जवाब: ", "❌ Wrong — correct answer: ") + esc(correctText)}</p>` +
      `<div class="remember"><b>🧠 ${L("याद रखें", "Remember this")}</b>${esc(L(m.q_hi, m.q_hinglish))} → <b>${esc(correctText)}</b></div>`;
  }
  return `<article class="card mcq" data-mcq="${esc(m.id)}"><div class="qmeta"><span class="chip">${L("प्रश्न", "Question")} · Ep ${epNo}</span></div>` +
    `<p class="qtext">${esc(L(m.q_hi, m.q_hinglish))}</p><div class="opts">${opts}</div>${verdict}</article>`;
}

function playVideo(f) {
  const id = f.dataset.vid;
  f.innerHTML = `<iframe src="https://www.youtube-nocookie.com/embed/${esc(id)}?autoplay=1&rel=0" title="Current Affairs Short" allow="accelerometer; autoplay; encrypted-media; picture-in-picture" allowfullscreen></iframe>`;
  const p = progress[curDate] || (progress[curDate] = { watched: [], read: false });
  const ep = Number(f.dataset.ep);
  if (!p.watched.includes(ep)) p.watched.push(ep);
  store.set("ca-progress", progress);
  updateMission();
}

function answerMcq(box, btn) {
  const card = box.closest(".mcq");
  const mcqId = card.dataset.mcq;
  let found = null, epNo = null;
  dayData.episodes.forEach((ep) => { if (ep.mcq && ep.mcq.id === mcqId) { found = ep.mcq; epNo = ep.episode; } });
  if (!found) { // revision card
    const rev = revision[mcqId];
    if (!rev) return;
    found = rev.snap;
  }
  const chosen = Number(btn.dataset.i);
  answers[mcqId] = chosen;
  store.set("ca-answers", answers);
  const ok = chosen === found.answer_index;
  const today = todayIST();
  if (!ok) {
    revision[mcqId] = { due: addDays(today, 1), stage: 0, snap: snapshot(found, epNo) };
  } else if (revision[mcqId]) {
    const r = revision[mcqId];
    r.stage += 1;
    if (r.stage >= 3) delete revision[mcqId];
    else r.due = addDays(today, r.stage === 1 ? 3 : 7);
  }
  store.set("ca-revision", revision);
  if (dayData && dayData.episodes.some((ep) => ep.mcq && ep.mcq.id === mcqId)) renderDay();
  renderRevision();
}

function snapshot(m, epNo) {
  return { id: m.id, q_hi: m.q_hi, q_hinglish: m.q_hinglish, options_hi: m.options_hi,
           options_hinglish: m.options_hinglish, answer_index: m.answer_index, ep: epNo };
}

/* ---------- revision ---------- */
function renderRevision() {
  const today = todayIST();
  const due = Object.values(revision).filter((r) => r.due <= today);
  const box = $("#revisionBox");
  if (!due.length) { box.hidden = true; return; }
  box.hidden = false;
  $("#revisionList").innerHTML = due.map((r) => mcqHtml(r.snap, r.snap.ep || "")).join("");
  $("#revisionList").querySelectorAll(".opts").forEach((b) =>
    b.querySelectorAll(".opt").forEach((btn) =>
      btn.addEventListener("click", () => answerMcq(b, btn))));
}

/* ---------- mission ---------- */
function observeRead() {
  const firstMcq = document.querySelector("#dayBody .mcq");
  if (!firstMcq) return;
  const io = new IntersectionObserver((entries) => {
    if (entries.some((e) => e.isIntersecting)) {
      const p = progress[curDate] || (progress[curDate] = { watched: [], read: false });
      if (!p.read) { p.read = true; store.set("ca-progress", progress); updateMission(); }
      io.disconnect();
    }
  }, { threshold: 0.2 });
  io.observe(firstMcq);
}

function updateMission() {
  const box = $("#mission");
  if (!dayData) { box.hidden = true; return; }
  box.hidden = false;
  const p = progress[curDate] || { watched: [], read: false };
  const vids = dayData.episodes.filter((e) => e.video_hi || e.video_hinglish).length;
  const mcqs = dayData.episodes.filter((e) => e.mcq);
  const watchDone = vids === 0 || p.watched.length > 0;
  const testDone = mcqs.length > 0 && mcqs.every((e) => answers[e.mcq.id] !== undefined);
  $("#stepWatch").classList.toggle("done", watchDone);
  $("#stepRead").classList.toggle("done", !!p.read);
  $("#stepTest").classList.toggle("done", testDone);
  const msg = $("#missionMsg");
  if (watchDone && p.read && testDone) msg.textContent = L("🎉 आज का मिशन पूरा! कल फिर मिलते हैं।", "🎉 Mission complete for today! See you tomorrow.");
  else if (!watchDone) msg.textContent = L("पहले Short देखें — 60 सेकंड में पूरा दिन।", "Start with the Short — the whole day in 60 seconds.");
  else if (!p.read) msg.textContent = L("अब 5 कहानियाँ पढ़ें — हर कार्ड एक परीक्षा-तथ्य है।", "Now read the story cards — every card is one exam fact.");
  else msg.textContent = L("आख़िरी कदम: आज का प्रश्न हल करें।", "Last step: answer today's question.");
}

/* ---------- wiring ---------- */
function setLang(next) {
  lang = next;
  store.set("ca-lang", lang);
  $("#langHi").classList.toggle("active", lang === "hi");
  $("#langHg").classList.toggle("active", lang === "hg");
  document.documentElement.lang = lang === "hi" ? "hi" : "en";
  if (dayData) renderDay();
  renderRevision();
}
$("#langHi").addEventListener("click", () => setLang("hi"));
$("#langHg").addEventListener("click", () => setLang("hg"));
$("#prevDay").addEventListener("click", () => {
  const dates = manifest.days.map((d) => d.date);
  const i = dates.indexOf(curDate);
  if (i > 0) loadDay(dates[i - 1]);
});
$("#nextDay").addEventListener("click", () => {
  const dates = manifest.days.map((d) => d.date);
  const i = dates.indexOf(curDate);
  if (i < dates.length - 1) loadDay(dates[i + 1]);
});
$("#dateLabel").addEventListener("click", () => { $("#calDrawer").hidden = !$("#calDrawer").hidden; });

setLang(lang);
load().catch(() => { $("#dayBody").innerHTML = '<p class="empty">Could not load current affairs. Please try again later.</p>'; });
