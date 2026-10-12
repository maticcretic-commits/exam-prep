/* ExamPrep shared quiz engine v1.1.0
 * ONE copy serves every exam. Fix a bug here once, not N times.
 * Consumes data/<slug>.json in the unified schema. No other input.
 * v1.1.0 adds: Vacancies tab (listings[] with deadline badges, sort, filters,
 *   plus pipeline[] and directory[]) and Videos tab (click-to-play YouTube).
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
    listSort: 'deadline',
    listCat: 'all',
    listQuery: ''
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

  /* ---------- vacancies tab (v1.1.0) ---------- */
  function daysLeft(ds) {
    var m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(ds || '');
    if (!m) return null;
    var d = new Date(+m[1], +m[2] - 1, +m[3]);
    var now = new Date(); now.setHours(0, 0, 0, 0);
    return Math.round((d - now) / 86400000);
  }

  function deadlineBadge(l) {
    var n = daysLeft(l.deadline);
    if (n === null) return '';
    if (n < 0) return '<span class="badge closed">Closed</span>';
    if (n === 0) return '<span class="badge urgent">Closes today</span>';
    if (n <= 7) return '<span class="badge urgent">' + n + ' day' + (n === 1 ? '' : 's') + ' left</span>';
    if (n <= 15) return '<span class="badge warn">' + n + ' days left</span>';
    return '<span class="badge ok">' + n + ' days left</span>';
  }

  function listingCats() {
    var seen = {}, out = [];
    (S.data.listings || []).forEach(function (l) {
      if (l.cat && !seen[l.cat]) { seen[l.cat] = 1; out.push(l.cat); }
    });
    return out.sort();
  }

  function filteredListings() {
    var ls = (S.data.listings || []).slice();
    if (S.listCat !== 'all') ls = ls.filter(function (l) { return l.cat === S.listCat; });
    if (S.listQuery) {
      var q = S.listQuery.toLowerCase();
      ls = ls.filter(function (l) {
        return ((l.title || '') + ' ' + (l.org || '') + ' ' + (l.posts || '') + ' ' + (l.qual || '')).toLowerCase().indexOf(q) !== -1;
      });
    }
    var key = S.listSort;
    ls.sort(function (a, b) {
      if (key === 'org') return (a.org || '').localeCompare(b.org || '');
      if (key === 'title') return (a.title || '').localeCompare(b.title || '');
      if (key === 'verified') return (b.verifyNote || '').localeCompare(a.verifyNote || '');
      // deadline: open soonest first; closed and dateless sink to the bottom
      var da = daysLeft(a.deadline), db = daysLeft(b.deadline);
      var ca = (da === null || da < 0), cb = (db === null || db < 0);
      if (ca && !cb) return 1;
      if (!ca && cb) return -1;
      if (da === null && db === null) return 0;
      if (da === null) return 1;
      if (db === null) return -1;
      return da - db;
    });
    return ls;
  }

  function specRow(dt, dd) {
    if (!dd || !String(dd).trim()) return '';
    return '<dt>' + esc(dt) + '</dt><dd>' + esc(dd) + '</dd>';
  }

  function renderListings() {
    var ls = filteredListings();
    var total = (S.data.listings || []).length;
    var open = (S.data.listings || []).filter(function (l) { var n = daysLeft(l.deadline); return n === null || n >= 0; }).length;

    var h = '<div class="toolbar">';
    h += '<select id="lCat" aria-label="Filter by category"><option value="all">All categories (' + total + ')</option>';
    listingCats().forEach(function (c) {
      var n = (S.data.listings || []).filter(function (l) { return l.cat === c; }).length;
      h += '<option value="' + esc(c) + '"' + (S.listCat === c ? ' selected' : '') + '>' + esc(c) + ' (' + n + ')</option>';
    });
    h += '</select>';
    h += '<select id="lSort" aria-label="Sort listings">'
      + '<option value="deadline"' + (S.listSort === 'deadline' ? ' selected' : '') + '>Sort: deadline (soonest)</option>'
      + '<option value="org"' + (S.listSort === 'org' ? ' selected' : '') + '>Sort: organisation A–Z</option>'
      + '<option value="title"' + (S.listSort === 'title' ? ' selected' : '') + '>Sort: title A–Z</option>'
      + '<option value="verified"' + (S.listSort === 'verified' ? ' selected' : '') + '>Sort: recently verified</option>'
      + '</select>';
    h += '<input id="lSearch" type="search" placeholder="Search vacancies…" value="' + esc(S.listQuery) + '" aria-label="Search vacancies">';
    h += '</div>';

    h += '<div class="stats"><span>Open: <b class="good">' + open + '</b></span>'
      + '<span>Showing <b>' + ls.length + '</b> of ' + total + '</span></div>';

    if (!ls.length) h += '<p class="empty">No vacancies match your filter.</p>';
    ls.forEach(function (l) {
      h += '<article class="card" id="l-' + esc(l.id || '') + '">';
      h += '<div class="qmeta">' + deadlineBadge(l)
        + (l.cat ? '<span class="chip">' + esc(l.cat) + '</span>' : '')
        + (l.state ? '<span class="chip dim">' + esc(l.state) + '</span>' : '') + '</div>';
      h += '<h3 class="captitle">' + esc(l.title || '') + '</h3>';
      h += '<div class="capbody"><b>' + esc(l.org || '') + '</b>' + (l.posts ? ' — ' + esc(l.posts) : '') + '</div>';
      h += '<dl class="specs">'
        + specRow('Qualification', l.qual)
        + specRow('Age limit', l.age)
        + specRow('Fee', l.fee)
        + specRow('Selection', l.sel)
        + specRow('Last date', l.deadlineNote || l.deadline)
        + specRow('Advt no.', l.advt)
        + '</dl>';
      h += '<div class="links">';
      if (l.apply) h += '<a class="btn" href="' + esc(l.apply) + '" target="_blank" rel="noopener">Apply online</a>';
      if (l.notify && l.notify !== l.apply) h += '<a class="btn ghost" href="' + esc(l.notify) + '" target="_blank" rel="noopener">Official notification</a>';
      h += '</div>';
      if (l.verifyNote) h += '<div class="vnote">' + esc(l.verifyNote) + '</div>';
      h += '</article>';
    });

    var pipe = S.data.pipeline || [];
    if (pipe.length) {
      h += '<h2 class="secttl">In the pipeline (' + pipe.length + ')</h2>';
      pipe.forEach(function (p) {
        h += '<article class="card slim"><div class="qmeta"><span class="chip dim">' + esc(p.stage || '') + '</span></div>'
          + '<div class="capbody"><b>' + esc(p.title || '') + '</b>' + (p.org ? ' — ' + esc(p.org) : '') + '</div>'
          + (p.note ? '<div class="capbody dim">' + esc(p.note) + '</div>' : '')
          + (p.link ? '<div class="links"><a class="btn ghost" href="' + esc(p.link) + '" target="_blank" rel="noopener">Details</a></div>' : '')
          + '</article>';
      });
    }

    var dir = S.data.directory || [];
    if (dir.length) {
      h += '<h2 class="secttl">Official source directory</h2><div class="dirgrid">';
      dir.forEach(function (g) {
        h += '<div class="card slim"><h3 class="captitle">' + esc(g.cat || '') + '</h3><ul class="dirlist">';
        (g.items || []).forEach(function (it) {
          if (Array.isArray(it)) h += '<li><a href="' + esc(it[1] || '#') + '" target="_blank" rel="noopener">' + esc(it[0] || '') + '</a></li>';
          else h += '<li>' + esc(String(it)) + '</li>';
        });
        h += '</ul></div>';
      });
      h += '</div>';
    }

    el('tabBody').innerHTML = h;

    el('lCat').addEventListener('change', function (e) { S.listCat = e.target.value; renderListings(); });
    el('lSort').addEventListener('change', function (e) { S.listSort = e.target.value; renderListings(); });
    var deb = null;
    el('lSearch').addEventListener('input', function (e) {
      clearTimeout(deb);
      deb = setTimeout(function () { S.listQuery = e.target.value.trim(); renderListings(); }, 250);
    });
  }

  /* ---------- videos tab (v1.1.0) ---------- */
  function renderVideos() {
    var vs = S.data.videos || [];
    var h = '<div class="stats"><span>Total videos: <b>' + vs.length + '</b></span></div>';
    h += '<div class="vidgrid">';
    vs.forEach(function (v) {
      h += '<article class="vidcard" data-vid="' + esc(v.youtube_id || '') + '" tabindex="0" role="button" aria-label="Play video: ' + esc(v.title || '') + '">';
      h += '<div class="vidthumb"><img loading="lazy" src="https://i.ytimg.com/vi/' + esc(v.youtube_id || '') + '/hqdefault.jpg" alt="">'
        + '<span class="play">▶</span></div>';
      h += '<div class="vidmeta">'
        + (v.subject ? '<span class="chip">' + esc(v.subject) + '</span>' : '')
        + '<div class="vidtitle">' + esc(v.title || '') + '</div></div>';
      h += '</article>';
    });
    h += '</div>';
    h += '<p class="empty dim">Tap a thumbnail to play it right here.</p>';
    el('tabBody').innerHTML = h;

    Array.prototype.forEach.call(document.querySelectorAll('.vidcard[data-vid]'), function (card) {
      function play() {
        var id = card.getAttribute('data-vid');
        if (!id || card.getAttribute('data-playing')) return;
        card.setAttribute('data-playing', '1');
        var thumb = card.querySelector('.vidthumb');
        if (thumb) thumb.innerHTML = '<iframe src="https://www.youtube-nocookie.com/embed/' + encodeURIComponent(id)
          + '?autoplay=1&rel=0" title="Video player" frameborder="0"'
          + ' allow="accelerometer; autoplay; encrypted-media; picture-in-picture" allowfullscreen></iframe>';
      }
      card.addEventListener('click', play);
      card.addEventListener('keydown', function (e) {
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); play(); }
      });
    });
  }

  /* ---------- resources tab (v1.1.0) ---------- */
  function renderResources() {
    var rs = S.data.resources || [];
    var h = '<div class="stats"><span>Total resources: <b>' + rs.length + '</b></span></div>';
    h += '<div class="caps">';
    rs.forEach(function (r) {
      h += '<article class="card"><div class="qmeta"><span class="chip">' + esc(r.subject || '') + '</span></div>'
        + '<h3 class="captitle">' + esc(r.title || '') + '</h3>'
        + '<div class="capbody">' + (r.body || '') + '</div></article>';
    });
    h += '</div>';
    el('tabBody').innerHTML = h;
  }

  function availableTabs(data) {
    var t = [];
    if ((data.questions || []).length) t.push(['practice', 'Practice (' + data.questions.length + ')']);
    if ((data.oneliners || []).length) t.push(['oneliners', 'One-liners (' + data.oneliners.length + ')']);
    if ((data.capsules || []).length) t.push(['capsules', 'Capsules (' + data.capsules.length + ')']);
    if ((data.listings || []).length) t.push(['listings', 'Vacancies (' + data.listings.length + ')']);
    if ((data.videos || []).length) t.push(['videos', 'Videos (' + data.videos.length + ')']);
    if ((data.resources || []).length) t.push(['resources', 'Resources (' + data.resources.length + ')']);
    return t;
  }

  function renderTab() {
    Array.prototype.forEach.call(document.querySelectorAll('.tabbtn'), function (b) {
      b.classList.toggle('active', b.getAttribute('data-tab') === S.tab);
    });
    if (S.tab === 'practice') renderPractice();
    else if (S.tab === 'oneliners') renderOneliners();
    else if (S.tab === 'capsules') renderCapsules();
    else if (S.tab === 'listings') renderListings();
    else if (S.tab === 'videos') renderVideos();
    else renderResources();
    window.scrollTo(0, 0);
  }

  function boot(data) {
    S.data = data;
    document.title = data.title + ' — ExamPrep';
    var ttl = el('examTitle'); if (ttl) ttl.textContent = data.title;

    var parts = [];
    if ((data.questions || []).length) parts.push(data.questions.length + ' MCQs');
    if ((data.oneliners || []).length) parts.push(data.oneliners.length + ' one-liners');
    if ((data.capsules || []).length) parts.push(data.capsules.length + ' capsules');
    if ((data.listings || []).length) parts.push(data.listings.length + ' vacancies');
    if ((data.videos || []).length) parts.push(data.videos.length + ' videos');
    if ((data.resources || []).length) parts.push(data.resources.length + ' resources');
    var sub = el('examSub');
    if (sub) sub.textContent = parts.join(' · ') || 'Content coming soon';

    var tabs = availableTabs(data);
    if (!tabs.some(function (t) { return t[0] === S.tab; })) S.tab = tabs.length ? tabs[0][0] : 'practice';
    var th = '';
    tabs.forEach(function (t) { th += '<button class="tabbtn" data-tab="' + t[0] + '">' + esc(t[1]) + '</button>'; });
    el('tabs').innerHTML = th;
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
