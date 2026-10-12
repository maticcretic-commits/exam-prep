/* ExamPrep shared quiz engine v1.0.0
 * ONE copy serves every exam. Fix a bug here once, not N times.
 * Consumes data/<slug>.json in the unified schema. No other input.
 */
(function () {
  'use strict';
  var slug = document.body.getAttribute('data-exam');
  var LETTERS = ['A', 'B', 'C', 'D', 'E', 'F'];
  var PER_PAGE = 20;

  var S = {
    data: null,
    tab: 'practice',
    subject: 'all',
    query: '',
    page: 0,
    answered: {},   // id -> chosen index
    score: 0,
  };

  function el(id) { return document.getElementById(id); }
  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;')
      .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  function filteredQuestions() {
    var qs = S.data.questions;
    if (S.subject !== 'all') qs = qs.filter(function (q) { return q.subject === S.subject; });
    if (S.query) {
      var ql = S.query.toLowerCase();
      qs = qs.filter(function (q) {
        return (q.q + ' ' + (q.e || '') + ' ' + (q.topic || '')).toLowerCase().indexOf(ql) !== -1;
      });
    }
    return qs;
  }

  function subjects() {
    var seen = {}, out = [];
    S.data.questions.forEach(function (q) {
      if (q.subject && !seen[q.subject]) { seen[q.subject] = 1; out.push(q.subject); }
    });
    return out.sort();
  }

  /* ---------- practice tab ---------- */
  function renderPractice() {
    var qs = filteredQuestions();
    var pages = Math.max(1, Math.ceil(qs.length / PER_PAGE));
    if (S.page >= pages) S.page = pages - 1;
    var start = S.page * PER_PAGE;
    var slice = qs.slice(start, start + PER_PAGE);

    var h = '';
    h += '<div class="toolbar">';
    h += '<select id="fSubject" aria-label="Filter by subject"><option value="all">All subjects (' + S.data.questions.length + ')</option>';
    subjects().forEach(function (s) {
      var n = S.data.questions.filter(function (q) { return q.subject === s; }).length;
      h += '<option value="' + esc(s) + '"' + (S.subject === s ? ' selected' : '') + '>' + esc(s) + ' (' + n + ')</option>';
    });
    h += '</select>';
    h += '<input id="fSearch" type="search" placeholder="Search questions…" value="' + esc(S.query) + '" aria-label="Search questions">';
    h += '</div>';

    h += '<div class="stats"><span>Answered: <b>' + Object.keys(S.answered).length + '</b></span>'
      + '<span>Correct: <b class="good">' + S.score + '</b></span>'
      + '<span>Showing ' + (start + 1) + '–' + Math.min(start + PER_PAGE, qs.length) + ' of ' + qs.length + '</span></div>';

    if (!slice.length) h += '<p class="empty">No questions match your filter.</p>';
    slice.forEach(function (q, idx) {
      var n = start + idx + 1;
      var chosen = S.answered[q.id];
      h += '<article class="card" id="q-' + esc(q.id) + '">';
      h += '<div class="qmeta"><span class="chip">' + esc(q.subject || '') + '</span>'
        + (q.topic ? '<span class="chip dim">' + esc(q.topic) + '</span>' : '')
        + '<span class="qnum">Q' + n + '</span></div>';
      h += '<div class="qtext">' + q.q + '</div>';
      h += '<div class="opts">';
      q.o.forEach(function (opt, oi) {
        var cls = 'opt';
        if (chosen !== undefined) {
          if (oi === q.a) cls += ' correct';
          else if (oi === chosen) cls += ' wrong';
          else cls += ' dimmed';
        }
        h += '<button class="' + cls + '" data-qid="' + esc(q.id) + '" data-oi="' + oi + '"'
          + (chosen !== undefined ? ' disabled' : '') + '>'
          + '<span class="olet">' + LETTERS[oi] + '</span><span>' + opt + '</span></button>';
      });
      h += '</div>';
      if (chosen !== undefined) {
        h += '<div class="verdict ' + (chosen === q.a ? 'good' : 'bad') + '">'
          + (chosen === q.a ? 'Correct ✓' : 'Wrong ✗ — correct answer: ' + LETTERS[q.a]) + '</div>';
        if (q.e) h += '<div class="expl"><b>Explanation:</b> ' + q.e + '</div>';
      }
      h += '</article>';
    });

    h += '<div class="pager">';
    h += '<button id="pgPrev"' + (S.page === 0 ? ' disabled' : '') + '>← Prev</button>';
    h += '<span>Page ' + (S.page + 1) + ' / ' + pages + '</span>';
    h += '<button id="pgNext"' + (S.page >= pages - 1 ? ' disabled' : '') + '>Next →</button>';
    h += '</div>';

    el('tabBody').innerHTML = h;

    el('fSubject').addEventListener('change', function (e) { S.subject = e.target.value; S.page = 0; renderPractice(); });
    var deb = null;
    el('fSearch').addEventListener('input', function (e) {
      clearTimeout(deb);
      deb = setTimeout(function () { S.query = e.target.value.trim(); S.page = 0; renderPractice(); }, 250);
    });
    var pp = el('pgPrev'), pn = el('pgNext');
    if (pp) pp.addEventListener('click', function () { if (S.page > 0) { S.page--; renderPractice(); window.scrollTo(0, 0); } });
    if (pn) pn.addEventListener('click', function () { if (S.page < pages - 1) { S.page++; renderPractice(); window.scrollTo(0, 0); } });

    Array.prototype.forEach.call(document.querySelectorAll('.opt[data-qid]'), function (btn) {
      btn.addEventListener('click', function () {
        var qid = btn.getAttribute('data-qid');
        var oi = parseInt(btn.getAttribute('data-oi'), 10);
        if (S.answered[qid] !== undefined) return;
        S.answered[qid] = oi;
        var q = null;
        S.data.questions.forEach(function (x) { if (x.id === qid) q = x; });
        if (q && oi === q.a) S.score++;
        renderPractice();
      });
    });
  }

  /* ---------- one-liners tab ---------- */
  function renderOneliners() {
    var ols = S.data.oneliners;
    var h = '<div class="stats"><span>Total one-liners: <b>' + ols.length + '</b></span></div>';
    h += '<ol class="oneliners">';
    ols.forEach(function (o) { h += '<li>' + o.text + '</li>'; });
    h += '</ol>';
    el('tabBody').innerHTML = h;
  }

  /* ---------- capsules tab ---------- */
  function renderCapsules() {
    var caps = S.data.capsules;
    var h = '<div class="stats"><span>Total capsules: <b>' + caps.length + '</b></span></div>';
    h += '<div class="caps">';
    caps.forEach(function (c) {
      h += '<article class="card"><div class="qmeta"><span class="chip">' + esc(c.subject || '') + '</span></div>'
        + '<h3 class="captitle">' + c.title + '</h3>'
        + '<div class="capbody">' + c.body + '</div></article>';
    });
    h += '</div>';
    el('tabBody').innerHTML = h;
  }

  function renderTab() {
    Array.prototype.forEach.call(document.querySelectorAll('.tabbtn'), function (b) {
      b.classList.toggle('active', b.getAttribute('data-tab') === S.tab);
    });
    if (S.tab === 'practice') renderPractice();
    else if (S.tab === 'oneliners') renderOneliners();
    else renderCapsules();
    window.scrollTo(0, 0);
  }

  function boot(data) {
    S.data = data;
    document.title = data.title + ' — ExamPrep';
    var ttl = el('examTitle'); if (ttl) ttl.textContent = data.title;
    var sub = el('examSub');
    if (sub) sub.textContent = data.questions.length + ' MCQs · ' + data.oneliners.length + ' one-liners · ' + data.capsules.length + ' capsules';

    var tabs = '';
    tabs += '<button class="tabbtn" data-tab="practice">Practice (' + data.questions.length + ')</button>';
    if (data.oneliners.length) tabs += '<button class="tabbtn" data-tab="oneliners">One-liners (' + data.oneliners.length + ')</button>';
    if (data.capsules.length) tabs += '<button class="tabbtn" data-tab="capsules">Capsules (' + data.capsules.length + ')</button>';
    el('tabs').innerHTML = tabs;
    Array.prototype.forEach.call(document.querySelectorAll('.tabbtn'), function (b) {
      b.addEventListener('click', function () { S.tab = b.getAttribute('data-tab'); renderTab(); });
    });
    renderTab();
  }

  function fail(msg) {
    el('tabBody').innerHTML = '<p class="empty">Could not load question bank. ' + esc(msg) + '</p>';
  }

  document.addEventListener('DOMContentLoaded', function () {
    fetch('../../data/' + slug + '.json')
      .then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
      .then(boot).catch(function (e) { fail(e.message); });
  });
})();
