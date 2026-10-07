/* WB homelab - front-end for the Home widgets (Find, Search bars, Notes, To-do).
   Glance injects page content after load, so widgets are initialised by a MutationObserver
   looking for [data-wb="..."] placeholders. Data comes from glance-admin on :3005.
   NOTE: never write a dollar-brace sequence in the YAML that embeds these placeholders. */
(function () {
  'use strict';
  var API = location.protocol + '//' + location.hostname + ':3005';
  var SS = window.sessionStorage;

  function h(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }
  function api(method, path, body) {
    var opt = { method: method, headers: {} };
    if (body !== undefined) { opt.headers['Content-Type'] = 'application/json'; opt.body = JSON.stringify(body); }
    return fetch(API + path, opt).then(function (r) {
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return r.json();
    });
  }
  function curSlug() { return (location.pathname.replace(/^\/+|\/+$/g, '').split('/')[0]) || 'home'; }
  function debounce(fn, ms) { var t; return function () { var a = arguments, s = this; clearTimeout(t); t = setTimeout(function () { fn.apply(s, a); }, ms); }; }

  /* ------------------------------------------------------------------ icons (theme-aware masks) */
  function iconEl(spec) {
    var parts = (spec || '').split(':'), kind = parts[0], name = parts[1];
    if (kind === 'si') {
      var s = h('span', 'wb-ico');
      var u = 'url(https://cdn.jsdelivr.net/npm/simple-icons@latest/icons/' + name + '.svg)';
      s.style.webkitMaskImage = u; s.style.maskImage = u;
      return s;
    }
    if (kind === 'mdi') {
      var m = h('span', 'wb-ico');
      var um = 'url(https://cdn.jsdelivr.net/npm/@mdi/svg@latest/svg/' + name + '.svg)';
      m.style.webkitMaskImage = um; m.style.maskImage = um;
      return m;
    }
    if (kind === 'di') {
      var d = h('span', 'wb-ico');
      var ud = 'url(https://cdn.jsdelivr.net/gh/homarr-labs/dashboard-icons/svg/' + name + '.svg)';
      d.style.webkitMaskImage = ud; d.style.maskImage = ud;
      return d;
    }
    return h('span', 'wb-ico');
  }

  /* ------------------------------------------------------------------ SEARCH bars */
  function initSearch(node) {
    var engines = [];
    try { engines = JSON.parse(node.getAttribute('data-engines') || '[]'); } catch (e) { return; }
    var grid = h('div', 'wb-search-grid');
    var first = null;
    engines.forEach(function (en, idx) {
      var form = h('form', 'wb-search');
      form.setAttribute('autocomplete', 'off');
      form.appendChild(iconEl(en[2]));
      var inp = h('input');
      inp.type = 'text'; inp.placeholder = en[0]; inp.spellcheck = false;
      inp.setAttribute('aria-label', 'Search ' + en[0]);
      form.appendChild(inp);
      form.addEventListener('submit', function (ev) {
        ev.preventDefault();
        var q = inp.value.trim();
        if (!q) return;
        window.open(en[1].replace('{QUERY}', encodeURIComponent(q)), '_blank', 'noopener');
        inp.value = '';
      });
      grid.appendChild(form);
      if (idx === 0) first = inp;
    });
    node.appendChild(grid);
    var ae = document.activeElement;
    if (first && (!ae || ae === document.body)) first.focus();
  }

  /* ------------------------------------------------------------------ NOTES */
  function initNotes(node) {
    var ta = h('textarea', 'wb-notes-text');
    ta.placeholder = 'Notes (saved on the server)...'; ta.spellcheck = false;
    var st = h('div', 'wb-note-status size-h6 color-subdue', 'loading...');
    node.appendChild(ta); node.appendChild(st);
    var loaded = false;
    api('GET', '/api/notes').then(function (d) { ta.value = d.text || ''; loaded = true; st.textContent = 'saved'; })
      .catch(function () { st.textContent = 'glance-admin offline'; st.className = 'wb-note-status size-h6 color-negative'; });
    var save = debounce(function () {
      if (!loaded) return;
      st.textContent = 'saving...';
      api('PUT', '/api/notes', { text: ta.value }).then(function () { st.textContent = 'saved'; st.className = 'wb-note-status size-h6 color-subdue'; })
        .catch(function () { st.textContent = 'not saved (offline)'; st.className = 'wb-note-status size-h6 color-negative'; });
    }, 700);
    ta.addEventListener('input', function () { st.textContent = 'editing...'; save(); });
  }

  /* ------------------------------------------------------------------ TO-DO */
  function initTodo(node) {
    var form = h('form', 'wb-todo-add');
    var inp = h('input'); inp.type = 'text'; inp.placeholder = 'Add a task and press Enter'; inp.maxLength = 500;
    form.appendChild(inp);
    var list = h('ul', 'wb-todo-list');
    var st = h('div', 'size-h6 color-subdue wb-todo-status');
    node.appendChild(form); node.appendChild(list); node.appendChild(st);

    function render(items) {
      list.textContent = '';
      items.forEach(function (t) {
        var li = h('li', t.done ? 'wb-done' : '');
        var cb = h('input'); cb.type = 'checkbox'; cb.checked = !!t.done;
        cb.addEventListener('change', function () { api('PATCH', '/api/todos/' + t.id, { done: cb.checked }).then(load).catch(err); });
        var tx = h('span', 'wb-todo-text', t.text);
        var del = h('button', 'wb-todo-del', '×'); del.type = 'button'; del.title = 'Delete';
        del.addEventListener('click', function () { api('DELETE', '/api/todos/' + t.id).then(load).catch(err); });
        li.appendChild(cb); li.appendChild(tx); li.appendChild(del);
        list.appendChild(li);
      });
      var open = items.filter(function (t) { return !t.done; }).length;
      st.className = 'size-h6 color-subdue wb-todo-status';
      st.textContent = items.length ? open + ' open / ' + items.length + ' total' : 'Nothing to do';
    }
    function err() { st.className = 'size-h6 color-negative wb-todo-status'; st.textContent = 'glance-admin offline'; }
    function load() { return api('GET', '/api/todos').then(function (d) { render(d.items || []); }).catch(err); }
    form.addEventListener('submit', function (ev) {
      ev.preventDefault();
      var v = inp.value.trim(); if (!v) return;
      inp.value = '';
      api('POST', '/api/todos', { text: v }).then(load).catch(err);
    });
    load();
    node.__wbTimer = setInterval(function () { if (!document.body.contains(node)) { clearInterval(node.__wbTimer); } else if (document.activeElement !== inp) { load(); } }, 60000);
  }

  /* ------------------------------------------------------------------ FIND (cross-tab) */
  // session state: { q, results:[{page,pageName,widget,text}], cur }
  function getSession() { try { return JSON.parse(SS.getItem('wbFind') || 'null'); } catch (e) { return null; } }
  function setSession(s) { try { if (s) SS.setItem('wbFind', JSON.stringify(s)); else SS.removeItem('wbFind'); } catch (e) { /* ignore */ } }

  var CAND = '.widget li, .widget tr, .wb-card, .wb-tile, .monitor-site, .docker-container, .widget a, .widget-header h2';

  function clearHits() {
    document.querySelectorAll('.wb-hit, .wb-hit-current').forEach(function (e) { e.classList.remove('wb-hit', 'wb-hit-current'); });
  }
  function matchingEls(q) {
    q = q.toLowerCase();
    var all = Array.prototype.filter.call(document.querySelectorAll(CAND), function (e) {
      return !e.closest('[data-wb-noindex], .wb-restricted') && (e.textContent || '').toLowerCase().indexOf(q) !== -1;
    });
    // keep the most specific (leaf-most) matches
    return all.filter(function (e) { return !all.some(function (o) { return o !== e && e.contains(o); }); });
  }
  function applyHighlight(s, tries) {
    if (!s) return;
    var q = s.q, r = s.results[s.cur];
    if (!r || r.page !== curSlug()) return;
    var k = 0;
    for (var i = 0; i < s.cur; i++) if (s.results[i].page === r.page) k++;
    var els = matchingEls(q);
    if (!els.length) {
      if ((tries || 0) < 40) setTimeout(function () { applyHighlight(s, (tries || 0) + 1); }, 250);
      return;
    }
    clearHits();
    els.forEach(function (e) { e.classList.add('wb-hit'); });
    var target = els[Math.min(k, els.length - 1)];
    target.classList.add('wb-hit-current');
    target.scrollIntoView({ block: 'center', behavior: 'smooth' });
  }
  function go(s, i) {
    var n = s.results.length;
    if (!n) return;
    s.cur = ((i % n) + n) % n;
    setSession(s);
    var r = s.results[s.cur];
    if (r.page === curSlug()) { applyHighlight(s); refreshUI(); }
    else { location.href = '/' + r.page; }
  }

  var ui = { widgets: [], strip: null };
  function refreshUI() {
    var s = getSession();
    ui.widgets.forEach(function (w) { w.update(s); });
    updateStrip(s);
  }

  function updateStrip(s) {
    var haveWidget = ui.widgets.some(function (w) { return document.body.contains(w.node); });
    var show = s && s.results && s.results.length && !haveWidget;
    if (!show) { if (ui.strip) { ui.strip.remove(); ui.strip = null; } return; }
    if (!ui.strip) {
      var bar = h('div', 'wb-find-strip');
      var lbl = h('span', 'wb-find-strip-label');
      var prev = h('button', '', '‹'); prev.type = 'button'; prev.title = 'Previous match';
      var next = h('button', '', '›'); next.type = 'button'; next.title = 'Next match';
      var x = h('button', '', '✕'); x.type = 'button'; x.title = 'End find';
      prev.onclick = function () { var c = getSession(); if (c) go(c, c.cur - 1); };
      next.onclick = function () { var c = getSession(); if (c) go(c, c.cur + 1); };
      x.onclick = function () { setSession(null); clearHits(); refreshUI(); };
      bar.appendChild(lbl); bar.appendChild(prev); bar.appendChild(next); bar.appendChild(x);
      bar.__lbl = lbl;
      document.body.appendChild(bar);
      ui.strip = bar;
    }
    var r = s.results[s.cur] || {};
    ui.strip.__lbl.textContent = 'Find “' + s.q + '”  ' + (s.cur + 1) + ' / ' + s.results.length + '  ·  ' + (r.pageName || '');
  }

  function initFind(node) {
    var row = h('div', 'wb-find-row');
    var inp = h('input', 'wb-find-input'); inp.type = 'text'; inp.placeholder = 'Find anywhere on the dashboard...  ( / )'; inp.spellcheck = false; inp.autocomplete = 'off';
    var prev = h('button', 'wb-find-btn', '‹'); prev.type = 'button'; prev.title = 'Previous (Shift+Enter)';
    var next = h('button', 'wb-find-btn', '›'); next.type = 'button'; next.title = 'Next (Enter)';
    var cnt = h('span', 'wb-find-count size-h6 color-subdue');
    var clr = h('button', 'wb-find-btn', '✕'); clr.type = 'button'; clr.title = 'Clear (Esc)';
    row.appendChild(inp); row.appendChild(prev); row.appendChild(next); row.appendChild(cnt); row.appendChild(clr);
    var list = h('ul', 'wb-find-list');
    node.appendChild(row); node.appendChild(list);

    var w = {
      node: node,
      update: function (s) {
        list.textContent = '';
        if (!s || !s.results) { cnt.textContent = ''; return; }
        cnt.textContent = s.results.length ? (s.cur + 1) + ' / ' + s.results.length : '0 results';
        var cp = null;
        s.results.slice(0, 120).forEach(function (r, i) {
          if (r.pageName !== cp) { var hd = h('li', 'wb-find-group', r.pageName); list.appendChild(hd); cp = r.pageName; }
          var li = h('li', 'wb-find-item' + (i === s.cur ? ' wb-find-current' : ''));
          li.appendChild(h('span', 'wb-find-widget color-subdue', r.widget || ''));
          li.appendChild(h('span', 'wb-find-text', r.text));
          li.addEventListener('click', function () { var c = getSession(); if (c) go(c, i); });
          list.appendChild(li);
        });
      }
    };
    ui.widgets.push(w);

    var run = debounce(function () {
      var q = inp.value.trim();
      if (q.length < 2) { setSession(null); clearHits(); w.update(null); return; }
      cnt.textContent = '...';
      api('GET', '/api/find?q=' + encodeURIComponent(q)).then(function (d) {
        var s = { q: q, results: d.results || [], cur: 0 };
        // start on the first match on the current page when there is one
        var here = s.results.findIndex(function (r) { return r.page === curSlug(); });
        s.cur = here >= 0 ? here : 0;
        setSession(s);
        w.update(s);
        if (s.results.length && s.results[s.cur].page === curSlug()) applyHighlight(s);
      }).catch(function () { cnt.textContent = 'glance-admin offline'; });
    }, 250);

    inp.addEventListener('input', run);
    inp.addEventListener('keydown', function (e) {
      var s = getSession();
      if (e.key === 'Enter') { e.preventDefault(); if (s) go(s, s.cur + (e.shiftKey ? -1 : 1)); else run(); }
      else if (e.key === 'Escape') { inp.value = ''; setSession(null); clearHits(); w.update(null); inp.blur(); }
    });
    prev.onclick = function () { var s = getSession(); if (s) go(s, s.cur - 1); };
    next.onclick = function () { var s = getSession(); if (s) go(s, s.cur + 1); };
    clr.onclick = function () { inp.value = ''; setSession(null); clearHits(); w.update(null); };

    var s0 = getSession();
    if (s0) { inp.value = s0.q; w.update(s0); applyHighlight(s0); }
  }

  /* ------------------------------------------------------------------ Bookmarks editor (Bookmarks page) */
  function jcall(method, path, body) {
    return fetch(API + path, { method: method, headers: body ? { 'Content-Type': 'application/json' } : {}, body: body ? JSON.stringify(body) : undefined })
      .then(function (r) { return r.json().catch(function () { return {}; }).then(function (d) { if (!r.ok) throw new Error(d.error || ('HTTP ' + r.status)); return d; }); });
  }
  function initBookmarks(node) {
    var det = h('details', 'wb-bm');
    det.appendChild(h('summary', '', 'Edit bookmarks — add, move or remove links and groups'));
    var body = h('div', 'wb-bm-body'); det.appendChild(body); node.appendChild(det);
    var data = null, loaded = false, filterText = '';
    var msg = h('div', 'size-h6 color-subdue wb-bm-msg');

    function say(t, bad) { msg.textContent = t; msg.className = 'size-h6 wb-bm-msg ' + (bad ? 'color-negative' : 'color-subdue'); }
    function done(text) { say(text + ' Reloading...'); setTimeout(function () { location.reload(); }, 2600); }
    function isOpen() { try { return SS.getItem('wbUnlocked') === '1'; } catch (e) { return false; } }
    var shownOpen = isOpen();
    // private groups are only listed (and can only be chosen as a target) while the PIN has been entered in this tab
    function groups() { var out = []; data.columns.forEach(function (c, ci) { c.groups.forEach(function (g) { if (g.private && !shownOpen) return; out.push({ g: g, col: ci }); }); }); return out; }
    function groupSelect(selected) {
      var s = h('select');
      groups().forEach(function (x) { var o = h('option', '', (x.g.private ? '\uD83D\uDD12 ' : '') + x.g.title); o.value = x.g.id; if (x.g.id === selected) o.selected = true; s.appendChild(o); });
      return s;
    }
    function render() {
      body.textContent = '';
      // add link
      var f = h('form', 'wb-bm-row');
      var gs = groupSelect(); var ti = h('input'); ti.placeholder = 'Title (optional, fetched from the page)'; var ur = h('input'); ur.placeholder = 'Address, e.g. https://example.com'; ur.className = 'wb-bm-wide';
      var b = h('button', '', 'Add link'); b.type = 'submit';
      f.appendChild(h('span', 'color-subdue size-h6', 'ADD LINK TO')); f.appendChild(gs); f.appendChild(ti); f.appendChild(ur); f.appendChild(b);
      f.addEventListener('submit', function (ev) {
        ev.preventDefault(); if (!ur.value.trim()) return; b.disabled = true; say('Fetching the page title and icon...');
        jcall('POST', '/api/bookmarks/link', { group_id: gs.value, title: ti.value, url: ur.value }).then(function (d) { done('Added "' + d.link.title + '" to ' + d.group + '.'); })
          .catch(function (e) { say(e.message, true); b.disabled = false; });
      });
      body.appendChild(f);
      // add group
      var f2 = h('form', 'wb-bm-row');
      var gn = h('input'); gn.placeholder = 'New group name'; var cs = h('select');
      ['Left column', 'Middle column', 'Right column'].forEach(function (t, i) { var o = h('option', '', t); o.value = i; if (i === 1) o.selected = true; cs.appendChild(o); });
      var b2 = h('button', '', 'Add group'); b2.type = 'submit';
      var pv = h('input'); pv.type = 'checkbox'; var pl = h('label', 'size-h6 color-subdue'); pl.appendChild(pv); pl.appendChild(document.createTextNode(' private (PIN-locked)'));
      f2.appendChild(h('span', 'color-subdue size-h6', 'NEW GROUP')); f2.appendChild(gn); f2.appendChild(cs); if (shownOpen) f2.appendChild(pl); f2.appendChild(b2);
      f2.addEventListener('submit', function (ev) {
        ev.preventDefault(); if (!gn.value.trim()) return; b2.disabled = true;
        jcall('POST', '/api/bookmarks/group', { title: gn.value, column: parseInt(cs.value, 10), private: !!pv.checked }).then(function (d) { done('Group "' + d.group.title + '" created.'); })
          .catch(function (e) { say(e.message, true); b2.disabled = false; });
      });
      body.appendChild(f2);
      body.appendChild(msg);
      if (!shownOpen && data.columns.some(function (c) { return c.groups.some(function (g) { return g.private; }); })) body.appendChild(h('div', 'size-h6 color-subdue', 'Private groups are hidden while locked. Unlock a locked widget on any page (PIN), then reopen this panel to manage them.'));
      // filter + manage
      var fi = h('input', 'wb-bm-filter'); fi.placeholder = 'Filter the list below...'; fi.value = filterText;
      fi.addEventListener('input', function () { filterText = fi.value; paint(); });
      body.appendChild(fi);
      list = h('div', 'wb-bm-list'); body.appendChild(list); paint();
    }
    var list;
    function arm(btn, label, action) {
      var armed = false, t;
      btn.addEventListener('click', function () {
        if (!armed) { armed = true; btn.textContent = 'Sure?'; btn.classList.add('wb-chan-armed'); t = setTimeout(function () { armed = false; btn.textContent = label; btn.classList.remove('wb-chan-armed'); }, 3500); return; }
        clearTimeout(t); action();
      });
    }
    function paint() {
      list.textContent = '';
      var q = filterText.trim().toLowerCase();
      groups().forEach(function (x) {
        var g = x.g;
        var links = g.links.filter(function (l) { return !q || (l.title + ' ' + l.url + ' ' + g.title).toLowerCase().indexOf(q) !== -1; });
        if (q && !links.length) return;
        var head = h('div', 'wb-bm-group');
        head.appendChild(h('span', 'color-highlight', (g.private ? '\uD83D\uDD12 ' : '') + g.title)); head.appendChild(h('span', 'color-subdue size-h6', ' ' + g.links.length + ' links'));
        if (!g.links.length) {
          var rm = h('button', 'wb-chan-del', 'Remove empty group'); rm.type = 'button';
          arm(rm, 'Remove empty group', function () { jcall('DELETE', '/api/bookmarks/group/' + g.id).then(function () { done('Group removed.'); }).catch(function (e) { say(e.message, true); }); });
          head.appendChild(rm);
        }
        list.appendChild(head);
        links.forEach(function (l) {
          var row = h('div', 'wb-bm-link');
          var a = h('a', 'color-highlight text-truncate', l.title); a.href = l.url; a.target = '_blank';
          var host = h('span', 'color-subdue size-h6 text-truncate', l.url.replace(/^https?:\/\/(www\.)?/, ''));
          var mv = groupSelect(g.id); mv.title = 'Move to another group';
          mv.addEventListener('change', function () { jcall('PATCH', '/api/bookmarks/link/' + l.id, { group_id: mv.value }).then(function () { done('Moved "' + l.title + '".'); }).catch(function (e) { say(e.message, true); }); });
          var del = h('button', 'wb-chan-del', 'Remove'); del.type = 'button';
          arm(del, 'Remove', function () { jcall('DELETE', '/api/bookmarks/link/' + l.id).then(function () { done('Removed "' + l.title + '".'); }).catch(function (e) { say(e.message, true); }); });
          row.appendChild(a); row.appendChild(host); row.appendChild(mv); row.appendChild(del); list.appendChild(row);
        });
      });
    }
    det.addEventListener('toggle', function () {
      if (det.open && loaded && shownOpen !== isOpen()) { shownOpen = isOpen(); render(); }      // lock state changed since the list was drawn
      if (!det.open || loaded) return;
      loaded = true; say('Loading...');
      jcall('GET', '/api/bookmarks').then(function (d) { data = d; say(''); render(); })
        .catch(function () { loaded = false; say('glance-admin offline: bookmarks cannot be edited right now', true); });
    });
  }

  /* ------------------------------------------------------------------ YouTube channel manager (Video News Feed page) */
  function initChannels(node) {
    var form = h('form', 'wb-chan-add');
    var inp = h('input'); inp.type = 'text'; inp.placeholder = 'Add a channel: @handle, channel link or UC... id'; inp.spellcheck = false;
    var btn = h('button', '', 'Add'); btn.type = 'submit';
    form.appendChild(inp); form.appendChild(btn);
    var msg = h('div', 'size-h6 color-subdue wb-chan-msg');
    var list = h('ul', 'wb-chan-list');
    node.appendChild(form); node.appendChild(msg); node.appendChild(list);

    function say(t, bad) { msg.textContent = t; msg.className = 'size-h6 wb-chan-msg ' + (bad ? 'color-negative' : 'color-subdue'); }
    function call(method, path, body) {
      return fetch(API + path, { method: method, headers: body ? { 'Content-Type': 'application/json' } : {}, body: body ? JSON.stringify(body) : undefined })
        .then(function (r) { return r.json().catch(function () { return {}; }).then(function (d) { if (!r.ok) throw new Error(d.error || ('HTTP ' + r.status)); return d; }); });
    }
    function render(chs) {
      list.textContent = '';
      chs.forEach(function (c) {
        var li = h('li');
        var a = h('a', 'color-highlight', c.name); a.href = 'https://www.youtube.com/channel/' + c.id; a.target = '_blank';
        var id = h('span', 'color-subdue size-h6', c.id);
        var x = h('button', 'wb-chan-del', '\u2715 Remove'); x.type = 'button';
        var armed = false, t;
        x.addEventListener('click', function () {
          if (!armed) { armed = true; x.textContent = 'Really remove?'; x.classList.add('wb-chan-armed'); t = setTimeout(function () { armed = false; x.textContent = '\u2715 Remove'; x.classList.remove('wb-chan-armed'); }, 3500); return; }
          clearTimeout(t); say('Removing ' + c.name + '...');
          call('DELETE', '/api/channels/' + c.id).then(function () { say('Removed. Reloading...'); setTimeout(function () { location.reload(); }, 2500); })
            .catch(function (e) { say(e.message, true); });
        });
        li.appendChild(a); li.appendChild(id); li.appendChild(x); list.appendChild(li);
      });
    }
    call('GET', '/api/channels').then(function (d) { render(d.channels || []); }).catch(function () { say('glance-admin offline: channels cannot be changed right now', true); });
    form.addEventListener('submit', function (ev) {
      ev.preventDefault();
      var v = inp.value.trim(); if (!v) return;
      btn.disabled = true; say('Looking that up on YouTube...');
      call('POST', '/api/channels', { input: v }).then(function (d) {
        inp.value = ''; render(d.channels || []); say('Added "' + d.channel.name + '". Reloading the page...');
        setTimeout(function () { location.reload(); }, 2500);
      }).catch(function (e) { say(e.message, true); btn.disabled = false; });
    });
  }

  /* ------------------------------------------------------------------ NEWS FEEDS editor (RSS feeds + subreddits)
     Talks to glance-admin /api/news; the page file is regenerated server-side and Glance reloads it. */
  function initNews(node) {
    var det = h('details', 'wb-fold');
    var sum = h('summary', '', 'Manage feeds and subreddits');
    det.appendChild(sum);
    var form = h('form', 'wb-chan-add wb-news-add');
    var inp = h('input'); inp.type = 'text'; inp.placeholder = 'RSS address, or a subreddit like r/selfhosted'; inp.spellcheck = false;
    var sel = h('select', 'wb-news-group');
    var ttl = h('input'); ttl.type = 'text'; ttl.placeholder = 'New group name'; ttl.hidden = true; ttl.maxLength = 40;
    var btn = h('button', '', 'Add'); btn.type = 'submit';
    form.appendChild(inp); form.appendChild(sel); form.appendChild(ttl); form.appendChild(btn);
    var msg = h('div', 'size-h6 color-subdue wb-chan-msg');
    var list = h('div', 'wb-news-list');
    det.appendChild(form); det.appendChild(msg); det.appendChild(list);
    node.appendChild(det);
    var state = { groups: [] };

    function say(t, bad) { msg.textContent = t; msg.className = 'size-h6 wb-chan-msg ' + (bad ? 'color-negative' : 'color-subdue'); }
    function call(method, path, body) {
      return fetch(API + path, { method: method, headers: body ? { 'Content-Type': 'application/json' } : {}, body: body ? JSON.stringify(body) : undefined })
        .then(function (r) { return r.json().catch(function () { return {}; }).then(function (d) { if (!r.ok) throw new Error(d.error || ('HTTP ' + r.status)); return d; }); });
    }
    function isSub(v) { v = v.trim(); return /reddit\.com\/r\//i.test(v) || /^\/?(r\/)?[A-Za-z0-9_]{2,21}$/.test(v); }
    function fillSelect() {
      var v = inp.value.trim(), kind = v ? (isSub(v) ? 'reddit' : 'rss') : null, keep = sel.value;
      sel.textContent = '';
      state.groups.forEach(function (g) {
        if (kind && g.kind !== kind) return;
        var o = h('option', '', (g.kind === 'rss' ? 'RSS: ' : 'Reddit: ') + g.title.replace(/^Reddit:\s*/, '')); o.value = g.id; sel.appendChild(o);
      });
      var n = h('option', '', '+ new ' + (kind === 'reddit' ? 'subreddit' : 'RSS') + ' group...'); n.value = '__new'; sel.appendChild(n);
      if (keep && Array.prototype.some.call(sel.options, function (o) { return o.value === keep; })) sel.value = keep;
      ttl.hidden = sel.value !== '__new';
    }
    function render() {
      list.textContent = '';
      var feeds = 0, subs = 0;
      state.groups.forEach(function (g) {
        if (g.kind === 'rss') feeds += g.items.length; else subs += g.items.length;
        var box = h('div', 'wb-news-grp');
        box.appendChild(h('div', 'size-h6 color-subdue wb-news-title', g.title + '  ·  ' + g.items.length));
        var ul = h('ul', 'wb-chan-list');
        g.items.forEach(function (it) {
          var li = h('li');
          var a = h('span', 'color-highlight', it.label); a.title = it.key;
          var x = h('button', 'wb-chan-del', '✕ Remove'); x.type = 'button';
          var armed = false, tm;
          x.addEventListener('click', function () {
            if (!armed) { armed = true; x.textContent = 'Really remove?'; x.classList.add('wb-chan-armed'); tm = setTimeout(function () { armed = false; x.textContent = '✕ Remove'; x.classList.remove('wb-chan-armed'); }, 3500); return; }
            clearTimeout(tm); say('Removing ' + it.label + '...');
            call('POST', '/api/news/remove', { group: g.id, key: it.key }).then(function (d) { state = d; render(); fillSelect(); say('Removed. Reloading...'); setTimeout(function () { location.reload(); }, 2500); })
              .catch(function (e) { say(e.message, true); });
          });
          li.appendChild(a); li.appendChild(x); ul.appendChild(li);
        });
        if (!g.items.length) ul.appendChild(h('li', 'color-subdue size-h6', 'empty (hidden on the page)'));
        box.appendChild(ul); list.appendChild(box);
      });
      sum.textContent = 'Manage feeds and subreddits  (' + feeds + ' feeds, ' + subs + ' subreddits)';
    }
    inp.addEventListener('input', debounce(fillSelect, 150));
    sel.addEventListener('change', function () { ttl.hidden = sel.value !== '__new'; if (!ttl.hidden) ttl.focus(); });
    call('GET', '/api/news').then(function (d) { state = d; render(); fillSelect(); })
      .catch(function () { say('glance-admin offline: feeds cannot be changed right now', true); });
    form.addEventListener('submit', function (ev) {
      ev.preventDefault();
      var v = inp.value.trim(); if (!v) return;
      btn.disabled = true; say('Checking it...');
      call('POST', '/api/news/add', { input: v, group: sel.value, new_title: ttl.value }).then(function (d) {
        inp.value = ''; ttl.value = ''; state = d; render(); fillSelect();
        say('Added "' + d.added + '" to ' + d.group + '. Reloading the page...');
        setTimeout(function () { location.reload(); }, 2500);
      }).catch(function (e) { say(e.message, true); }).then(function () { btn.disabled = false; });
    });
  }

  /* ------------------------------------------------------------------ CAMERA detection search + viewer (Cameras page)
     Text search (Frigate semantic search: by description or by appearance), type, camera and date/time range -> glance-admin
     /api/cameras/events -> a strip of thumbnails. Click any thumbnail on this page (search, recent, by type) to open the viewer:
     snapshot, clip, description, previous/next. Images and clips come straight from Frigate on the LAN. */
  var camViewer = null;
  function camWhen(ts) { return new Date(ts * 1000).toLocaleString('en-GB', { weekday: 'short', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }); }

  function openCamViewer(items, idx, FR, UI) {
    var cur = idx;
    if (!camViewer) {
      var ov = h('div', 'wb-modal'); ov.hidden = true;
      var box = h('div', 'wb-modal-box');
      var head = h('div', 'wb-modal-head'); var title = h('div', 'wb-modal-title'); var close = h('button', 'wb-modal-x', '✕'); close.type = 'button'; close.title = 'Close (Esc)';
      head.appendChild(title); head.appendChild(close);
      var stage = h('div', 'wb-modal-stage'); var prev = h('button', 'wb-modal-nav wb-modal-prev', '‹'); var next = h('button', 'wb-modal-nav wb-modal-next', '›');
      prev.type = 'button'; next.type = 'button';
      var bar = h('div', 'wb-modal-bar'); var desc = h('div', 'wb-modal-desc');
      box.appendChild(head); box.appendChild(stage); box.appendChild(bar); box.appendChild(desc); ov.appendChild(prev); ov.appendChild(box); ov.appendChild(next);
      document.body.appendChild(ov);
      camViewer = { ov: ov, title: title, stage: stage, bar: bar, desc: desc, prev: prev, next: next, close: close, items: [], i: 0, FR: FR, UI: UI };
      function shut() { ov.hidden = true; stage.textContent = ''; }
      close.addEventListener('click', shut);
      ov.addEventListener('click', function (ev) { if (ev.target === ov) shut(); });
      document.addEventListener('keydown', function (ev) {
        if (ov.hidden) return;
        if (ev.key === 'Escape') shut();
        else if (ev.key === 'ArrowLeft') camViewer.prev.click();
        else if (ev.key === 'ArrowRight') camViewer.next.click();
      });
      prev.addEventListener('click', function () { if (camViewer.i > 0) camViewer.show(camViewer.i - 1); });
      next.addEventListener('click', function () { if (camViewer.i < camViewer.items.length - 1) camViewer.show(camViewer.i + 1); });
      camViewer.show = function (n) {
        var V = camViewer, e = V.items[n]; V.i = n;
        V.title.textContent = (e.sub || e.label) + '  ·  ' + e.camera + '  ·  ' + camWhen(e.start) + (e.seconds ? '  ·  ' + e.seconds + 's' : '') + (e.score ? '  ·  ' + e.score + '%' : '');
        V.stage.textContent = ''; V.bar.textContent = '';
        function showImage() {
          V.stage.textContent = '';
          var im = h('img'); im.src = V.FR + '/api/events/' + e.id + (e.snapshot ? '/snapshot.jpg' : '/thumbnail.jpg'); im.alt = ''; V.stage.appendChild(im);
        }
        function showClip() {
          V.stage.textContent = '';
          var v = h('video'); v.controls = true; v.autoplay = true; v.muted = true; v.playsInline = true; v.src = API + '/api/cameras/clip?id=' + encodeURIComponent(e.id);
          v.addEventListener('error', function () { V.stage.textContent = ''; V.stage.appendChild(h('div', 'wb-modal-msg', 'The clip could not be played (it may have been cleaned up, or the browser cannot decode it). Use "Open in Frigate".')); });
          V.stage.appendChild(v);
        }
        var bImg = h('button', '', 'Snapshot'); bImg.type = 'button'; bImg.addEventListener('click', showImage);
        V.bar.appendChild(bImg);
        if (e.clip) { var bClip = h('button', '', 'Play clip'); bClip.type = 'button'; bClip.addEventListener('click', showClip); V.bar.appendChild(bClip); }
        var a1 = h('a', '', 'Open image'); a1.href = V.FR + '/api/events/' + e.id + (e.snapshot ? '/snapshot.jpg' : '/thumbnail.jpg'); a1.target = '_blank'; V.bar.appendChild(a1);
        if (e.clip) { var a2 = h('a', '', 'Download clip'); a2.href = API + '/api/cameras/clip?id=' + encodeURIComponent(e.id); a2.target = '_blank'; V.bar.appendChild(a2); }
        var a3 = h('a', '', 'Open in Frigate'); a3.href = V.UI + '/explore'; a3.target = '_blank'; V.bar.appendChild(a3);
        V.desc.textContent = e.description || 'No description for this detection (people who enter the near-camera zone get one).';
        V.desc.className = 'wb-modal-desc' + (e.description ? '' : ' color-subdue');
        V.prev.style.visibility = n > 0 ? 'visible' : 'hidden'; V.next.style.visibility = n < V.items.length - 1 ? 'visible' : 'hidden';
        showImage();
      };
    }
    camViewer.FR = FR; camViewer.UI = UI; camViewer.items = items; camViewer.ov.hidden = false; camViewer.show(idx);
  }

  function initCamEvents(node) {
    var FR = node.getAttribute('data-frigate') || '';
    var UI = node.getAttribute('data-frigate-ui') || FR;
    var list = [];
    var form = h('form', 'wb-chan-add wb-cam-search');
    var q = h('input', 'wb-cam-q'); q.type = 'search'; q.placeholder = 'Describe it: red jacket, goth, tracksuit, carrying a parcel, white van...'; q.spellcheck = false; q.maxLength = 160;
    var selMode = h('select');
    [['description', 'by description'], ['thumbnail', 'by appearance']].forEach(function (m) { var o = h('option', '', m[1]); o.value = m[0]; selMode.appendChild(o); });
    selMode.title = 'Description: matches the written description (people near the camera). Appearance: matches the picture itself (everything).';
    var selType = h('select'), selCam = h('select'), selRange = h('select');
    [['1', 'Last hour'], ['6', 'Last 6 hours'], ['24', 'Last 24 hours'], ['168', 'Last 7 days'], ['720', 'Last 30 days'], ['custom', 'Custom range...']].forEach(function (r) {
      var o = h('option', '', r[1]); o.value = r[0]; if (r[0] === '24') o.selected = true; selRange.appendChild(o);
    });
    function dt(hoursAgo) {
      var d = new Date(Date.now() - hoursAgo * 3600000), p = function (n) { return ('0' + n).slice(-2); };
      return d.getFullYear() + '-' + p(d.getMonth() + 1) + '-' + p(d.getDate()) + 'T' + p(d.getHours()) + ':' + p(d.getMinutes());
    }
    var from = h('input'), to = h('input');
    from.type = 'datetime-local'; to.type = 'datetime-local'; from.value = dt(24); to.value = dt(0);
    from.hidden = true; to.hidden = true; from.title = 'From'; to.title = 'To';
    var go = h('button', '', 'Search'); go.type = 'submit';
    var clear = h('button', '', 'Clear'); clear.type = 'button';
    [q, selMode, selType, selCam, selRange, from, to, go, clear].forEach(function (e) { form.appendChild(e); });
    var msg = h('div', 'size-h6 color-subdue wb-chan-msg');
    var strip = h('div', 'wb-results');
    node.appendChild(form); node.appendChild(msg); node.appendChild(strip);

    function opt(sel, value, text) { var o = h('option', '', text); o.value = value; sel.appendChild(o); }
    opt(selType, '', 'All types'); opt(selCam, '', 'All cameras');
    fetch(API + '/api/cameras/summary').then(function (r) { return r.json(); }).then(function (d) {
      (d.label_names || []).forEach(function (l) { opt(selType, l, l); });
      (d.cameras || []).forEach(function (c) { opt(selCam, c.name, c.name); });
    }).catch(function () { /* the filters simply stay on "all" */ });
    selRange.addEventListener('change', function () { var c = selRange.value === 'custom'; from.hidden = !c; to.hidden = !c; });
    clear.addEventListener('click', function () { q.value = ''; search(); });

    function card(e, i) {
      var c = h('div', 'wb-card');
      var a = h('a'); a.href = FR + '/api/events/' + e.id + '/snapshot.jpg'; a.target = '_blank'; a.title = e.description || '';
      a.addEventListener('click', function (ev) { if (ev.ctrlKey || ev.metaKey || ev.shiftKey || ev.button) return; ev.preventDefault(); openCamViewer(list, i, FR, UI); });
      var img = h('img'); img.alt = ''; img.style.aspectRatio = '16/10';
      img.classList.add('loaded', 'finished-transition');            // Glance hides lazy images until ITS script marks them loaded; it does not see images added later
      img.loading = 'lazy'; img.src = FR + '/api/events/' + e.id + '/thumbnail.jpg';
      a.appendChild(img);
      a.appendChild(h('div', 'wb-title', e.sub || e.label));
      var sub = e.camera + ' · ' + camWhen(e.start);
      a.appendChild(h('div', 'wb-sub', sub));
      if (e.description) { var d = e.description.replace(/^\[[^\]]+\]\s*/, ''); var tag = (e.description.match(/^\[([^\]]+)\]/) || [])[1]; if (tag) a.appendChild(h('div', 'wb-sub wb-tag', tag)); a.appendChild(h('div', 'wb-sub wb-desc', d)); }
      c.appendChild(a);
      return c;
    }
    function search() {
      var after, before = 0;
      if (selRange.value === 'custom') {
        after = Math.floor(new Date(from.value).getTime() / 1000); before = Math.floor(new Date(to.value).getTime() / 1000);
        if (!after || !before || after >= before) { msg.className = 'size-h6 wb-chan-msg color-negative'; msg.textContent = 'Pick a start that is before the end.'; return; }
      } else { after = Math.floor(Date.now() / 1000) - parseInt(selRange.value, 10) * 3600; }
      var text = q.value.trim();
      var qs = '?limit=120&after=' + after + (before ? '&before=' + before : '') + (selType.value ? '&label=' + encodeURIComponent(selType.value) : '') + (selCam.value ? '&camera=' + encodeURIComponent(selCam.value) : '')
        + (text ? '&q=' + encodeURIComponent(text) + '&mode=' + selMode.value : '');
      go.disabled = true; msg.className = 'size-h6 wb-chan-msg color-subdue'; msg.textContent = text ? 'Searching for "' + text + '"...' : 'Searching...';
      fetch(API + '/api/cameras/events' + qs).then(function (r) { return r.json().then(function (d) { if (!r.ok) throw new Error(d.error || ('HTTP ' + r.status)); return d; }); })
        .then(function (d) {
          list = d.events; strip.textContent = '';
          list.forEach(function (e, i) { strip.appendChild(card(e, i)); });
          msg.textContent = d.count
            ? (d.count + ' result' + (d.count === 1 ? '' : 's') + (text ? ', best match first (' + (d.mode === 'description' ? 'matching descriptions' : 'matching appearance') + ')' : ', newest first') + (d.capped ? ' · showing the first 120: narrow it down to see others' : '') + ' · click one to view the image or clip')
            : (text && d.mode === 'description' ? 'Nothing matched. Descriptions exist only for people near the camera: try "by appearance" for everything else.' : 'Nothing found in that range.');
        })
        .catch(function (e) { msg.className = 'size-h6 wb-chan-msg color-negative'; msg.textContent = e.message; })
        .then(function () { go.disabled = false; });
    }
    form.addEventListener('submit', function (ev) { ev.preventDefault(); search(); });

    // the other strips on this page (Recent detections, Detections by type) are rendered by Glance: open their thumbnails in the viewer too
    if (!document.__wbCamClicks) {
      document.__wbCamClicks = true;
      document.addEventListener('click', function (ev) {
        if (ev.ctrlKey || ev.metaKey || ev.shiftKey || ev.button) return;
        var a = ev.target.closest && ev.target.closest('a[href*="/api/events/"]');
        if (!a || a.closest('[data-wb=cam-events]')) return;
        var m = a.getAttribute('href').match(/\/api\/events\/([0-9.]+-[a-z0-9]+)\/snapshot\.jpg/);
        if (!m) return;
        ev.preventDefault();
        fetch(API + '/api/cameras/event?id=' + encodeURIComponent(m[1])).then(function (r) { if (!r.ok) throw 0; return r.json(); })
          .then(function (e) { openCamViewer([e], 0, FR, UI); }).catch(function () { window.open(a.href, '_blank'); });
      });
    }
    search();
  }

  /* ------------------------------------------------------------------ SHOPPING page
     Shopping list, wishlist (+ locked gift ideas), purchases and spend, deal-alert terms, saved eBay searches, price watches.
     State lives in glance-admin (/api/shopping/*), so every device sees the same lists. */
  var SHOP_CATS = ['Tech', 'Music', 'Home', 'DIY', 'Tools', 'Other'];
  function pound(n) { return n === null || n === undefined || n === '' ? '' : '£' + (Math.round(parseFloat(n) * 100) / 100).toLocaleString('en-GB', { minimumFractionDigits: (parseFloat(n) % 1 ? 2 : 0), maximumFractionDigits: 2 }); }
  function agoMin(m) { return m === null || m === undefined || m < 0 ? '' : m < 1 ? 'just now' : m < 90 ? m + 'm ago' : m < 2880 ? Math.round(m / 60) + 'h ago' : Math.round(m / 1440) + 'd ago'; }
  function shopSelect(opts, val, cls) { var s = h('select', cls || ''); opts.forEach(function (o) { var x = h('option', '', Array.isArray(o) ? o[1] : o); x.value = Array.isArray(o) ? o[0] : o; if (x.value === val) x.selected = true; s.appendChild(x); }); return s; }
  function shopInput(ph, cls, type) { var i = h('input', cls || ''); i.type = type || 'text'; i.placeholder = ph; i.spellcheck = false; return i; }
  function shopSay(msg) { return function (t, bad) { msg.textContent = t; msg.className = 'size-h6 wb-chan-msg ' + (bad ? 'color-negative' : 'color-subdue'); }; }
  var shopSummaryCache = { at: 0, data: null, pending: null };
  function shopSummary(force) {
    var now = Date.now();
    if (!force && shopSummaryCache.data && now - shopSummaryCache.at < 20000) return Promise.resolve(shopSummaryCache.data);
    if (shopSummaryCache.pending) return shopSummaryCache.pending;
    shopSummaryCache.pending = fetch(API + '/api/shopping/summary').then(function (r) { return r.ok ? r.json() : null; }).catch(function () { return null; })
      .then(function (d) { shopSummaryCache.pending = null; if (d) { shopSummaryCache.data = d; shopSummaryCache.at = Date.now(); } return d || shopSummaryCache.data; });
    return shopSummaryCache.pending;
  }

  /* ---- shopping list */
  function initShopList(node) {
    var data = [];
    var form = h('form', 'wb-shop-form');
    var text = shopInput('Add an item', 'wb-shop-grow'), qty = shopInput('Qty', 'wb-shop-qty'), store = shopInput('Shop', 'wb-shop-store');
    store.setAttribute('list', 'wb-shops'); text.maxLength = 120; qty.maxLength = 12; store.maxLength = 30;
    var dl = h('datalist'); dl.id = 'wb-shops'; ['Screwfix', 'Toolstation', 'B&Q', 'Wickes', 'Amazon', 'eBay', 'CeX', 'Tesco', 'Aldi', 'Argos'].forEach(function (s) { var o = h('option'); o.value = s; dl.appendChild(o); });
    var cat = shopSelect(SHOP_CATS, 'Other'); var add = h('button', '', 'Add'); add.type = 'submit';
    [text, qty, store, cat, add, dl].forEach(function (e) { form.appendChild(e); });
    var msg = h('div', 'size-h6 color-subdue wb-chan-msg'), say = shopSay(msg), list = h('div', 'wb-shop-list');
    node.appendChild(form); node.appendChild(msg); node.appendChild(list);
    function render() {
      list.textContent = '';
      var groups = {};
      data.forEach(function (it) { (groups[it.store || 'Anywhere'] = groups[it.store || 'Anywhere'] || []).push(it); });
      Object.keys(groups).sort().forEach(function (g) {
        list.appendChild(h('div', 'size-h6 color-subdue wb-shop-group', g + '  ·  ' + groups[g].filter(function (i) { return !i.done; }).length));
        groups[g].forEach(function (it) {
          var row = h('label', 'wb-shop-row' + (it.done ? ' wb-done' : ''));
          var cb = h('input'); cb.type = 'checkbox'; cb.checked = it.done;
          cb.addEventListener('change', function () { it.done = cb.checked; render(); jcall('PATCH', '/api/shopping/list/' + it.id, { done: cb.checked }).catch(function (e) { say(e.message, true); }); });
          var t = h('span', 'wb-shop-text', it.text); var q = h('span', 'color-subdue size-h6', (it.qty ? it.qty + ' · ' : '') + it.cat);
          var x = h('button', 'wb-chan-del', '✕'); x.type = 'button'; x.title = 'Remove';
          x.addEventListener('click', function (ev) { ev.preventDefault(); data = data.filter(function (i) { return i.id !== it.id; }); render(); jcall('DELETE', '/api/shopping/list/' + it.id).catch(function (e) { say(e.message, true); }); });
          [cb, t, q, x].forEach(function (e) { row.appendChild(e); }); list.appendChild(row);
        });
      });
      var done = data.filter(function (i) { return i.done; }).length;
      if (!data.length) list.appendChild(h('div', 'color-subdue size-h6', 'Nothing on the list.'));
      else {
        var foot = h('div', 'size-h6 color-subdue wb-shop-foot', (data.length - done) + ' to get');
        if (done) { var cl = h('button', 'wb-chan-del', 'Clear ' + done + ' ticked'); cl.type = 'button'; cl.addEventListener('click', function () { jcall('POST', '/api/shopping/list/clear', {}).then(load).catch(function (e) { say(e.message, true); }); }); foot.appendChild(cl); }
        list.appendChild(foot);
      }
    }
    function load() { jcall('GET', '/api/shopping/state').then(function (d) { data = d.list || []; render(); }).catch(function () { say('glance-admin offline', true); }); }
    form.addEventListener('submit', function (ev) {
      ev.preventDefault(); if (!text.value.trim()) return;
      jcall('POST', '/api/shopping/list', { text: text.value, qty: qty.value, store: store.value, cat: cat.value }).then(function (d) { data.push(d.result); text.value = ''; qty.value = ''; render(); text.focus(); say(''); })
        .catch(function (e) { say(e.message, true); });
    });
    load();
  }

  /* ---- wishlist and (locked) gift ideas */
  function initShopWish(node) {
    var gifts = node.getAttribute('data-gifts') === '1';
    var items = [], watches = {};
    var form = h('form', 'wb-shop-form');
    var title = shopInput(gifts ? 'Gift idea' : 'What do you want?', 'wb-shop-grow'), url = shopInput('Link (optional)', 'wb-shop-link'), target = shopInput('Target £', 'wb-shop-qty', 'number');
    target.step = '0.01'; target.min = '0';
    var prio = shopSelect([['3', '★★★ must'], ['2', '★★ want'], ['1', '★ maybe']], '2'); var cat = shopSelect(SHOP_CATS, 'Tech');
    var notes = shopInput('Notes (optional)', 'wb-shop-grow'); var add = h('button', '', 'Add'); add.type = 'submit';
    [title, url, target, prio, cat, notes, add].forEach(function (e) { form.appendChild(e); });
    var msg = h('div', 'size-h6 color-subdue wb-chan-msg'), say = shopSay(msg), list = h('div', 'wb-shop-list');
    node.appendChild(form); node.appendChild(msg); node.appendChild(list);
    function render() {
      list.textContent = '';
      var mine = items.filter(function (w) { return !!w.gift === gifts; }).sort(function (a, b) { return b.priority - a.priority || b.added - a.added; });
      if (!mine.length) list.appendChild(h('div', 'color-subdue size-h6', gifts ? 'No gift ideas yet.' : 'Nothing on the wishlist.'));
      mine.forEach(function (w) {
        var row = h('div', 'wb-wish');
        var top = h('div', 'flex justify-between gap-10 items-center');
        var left = h('span', 'text-truncate');
        left.appendChild(h('span', 'color-primary wb-stars', '★★★'.slice(0, w.priority)));
        if (w.url) { var a = h('a', 'color-highlight', ' ' + w.title); a.href = w.url; a.target = '_blank'; left.appendChild(a); } else left.appendChild(h('span', 'color-highlight', ' ' + w.title));
        var right = h('span', 'shrink-0 size-h6 color-subdue', w.cat + (w.target ? ' · target ' + pound(w.target) : ''));
        top.appendChild(left); top.appendChild(right); row.appendChild(top);
        var wt = w.watch && watches[w.watch];
        if (wt) {
          var st = h('div', 'size-h6 ' + (wt.at_target ? 'color-positive' : 'color-subdue'));
          st.textContent = wt.error ? 'watching: ' + wt.error : 'watching: ' + (wt.price !== null ? pound(wt.price) : 'price not found') + (wt.in_stock === false ? ' · out of stock' : '') + (wt.at_target ? '  ✓ at or below your target' : '');
          row.appendChild(st);
        }
        if (w.notes) row.appendChild(h('div', 'size-h6 color-subdue', w.notes));
        var acts = h('div', 'wb-shop-acts');
        var bought = h('button', 'wb-chan-del', 'Bought'); bought.type = 'button';
        bought.addEventListener('click', function () {
          acts.textContent = '';
          var pf = h('form', 'wb-shop-form'); var pr = shopInput('Paid £', 'wb-shop-qty', 'number'); pr.step = '0.01'; pr.min = '0'; if (w.target) pr.value = w.target; var sh = shopInput('Shop', 'wb-shop-store');
          var ok = h('button', '', 'Save'); ok.type = 'submit'; var no = h('button', 'wb-chan-del', 'Cancel'); no.type = 'button';
          [pr, sh, ok, no].forEach(function (e) { pf.appendChild(e); }); acts.appendChild(pf); pr.focus();
          no.addEventListener('click', render);
          pf.addEventListener('submit', function (ev) { ev.preventDefault(); jcall('POST', '/api/shopping/wish/' + w.id + '/bought', { price: pr.value, store: sh.value }).then(function () { items = items.filter(function (i) { return i.id !== w.id; }); render(); say('Moved to your purchases.'); }).catch(function (e) { say(e.message, true); }); });
        });
        acts.appendChild(bought);
        if (w.url && !w.watch) {
          var wb = h('button', 'wb-chan-del', 'Watch price'); wb.type = 'button';
          wb.addEventListener('click', function () { wb.disabled = true; say('Adding a price watch...'); jcall('POST', '/api/shopping/wish/' + w.id + '/watch', {}).then(function (d) { w.watch = d.result.watch; shopSummary(true).then(function (s) { indexWatches(s); render(); }); say('Watching: checked every 6 hours (see Price watches).'); }).catch(function (e) { say(e.message, true); wb.disabled = false; }); });
          acts.appendChild(wb);
        }
        var rm = h('button', 'wb-chan-del', '✕ Remove'); rm.type = 'button';
        var armed = false, tm;
        rm.addEventListener('click', function () {
          if (!armed) { armed = true; rm.textContent = 'Sure?'; rm.classList.add('wb-chan-armed'); tm = setTimeout(function () { armed = false; rm.textContent = '✕ Remove'; rm.classList.remove('wb-chan-armed'); }, 3000); return; }
          clearTimeout(tm); items = items.filter(function (i) { return i.id !== w.id; }); render(); jcall('DELETE', '/api/shopping/wish/' + w.id).catch(function (e) { say(e.message, true); });
        });
        acts.appendChild(rm); row.appendChild(acts); list.appendChild(row);
      });
    }
    function indexWatches(s) { watches = {}; ((s && s.watches && s.watches.items) || []).forEach(function (x) { watches[x.id] = x; }); }
    function load() {
      jcall('GET', '/api/shopping/state').then(function (d) { items = d.wishlist || []; render(); return shopSummary(); }).then(function (s) { indexWatches(s); render(); })
        .catch(function () { say('glance-admin offline', true); });
    }
    form.addEventListener('submit', function (ev) {
      ev.preventDefault(); if (!title.value.trim()) return;
      jcall('POST', '/api/shopping/wish', { title: title.value, url: url.value, target: target.value, priority: parseInt(prio.value, 10), cat: cat.value, notes: notes.value, gift: gifts })
        .then(function (d) { items.push(d.result); title.value = ''; url.value = ''; target.value = ''; notes.value = ''; render(); say(''); }).catch(function (e) { say(e.message, true); });
    });
    load(); setInterval(function () { shopSummary().then(function (s) { indexWatches(s); render(); }); }, 120000);
  }

  /* ---- deal-alert terms */
  function initShopTerms(node) {
    var terms = [];
    var form = h('form', 'wb-shop-form'); var t = shopInput('Add a word or phrase to watch for, e.g. "ddr3" or "quadro t1000"', 'wb-shop-grow'); var b = h('button', '', 'Add'); b.type = 'submit';
    form.appendChild(t); form.appendChild(b);
    var msg = h('div', 'size-h6 color-subdue wb-chan-msg'), say = shopSay(msg), chips = h('div', 'wb-pillrow');
    node.appendChild(form); node.appendChild(chips); node.appendChild(msg);
    function render() {
      chips.textContent = '';
      terms.forEach(function (x) {
        var c = h('span', 'wb-pill'); c.appendChild(document.createTextNode(x + ' '));
        var rm = h('button', 'wb-chan-del', '✕'); rm.type = 'button'; rm.title = 'Stop watching for this';
        rm.addEventListener('click', function () { terms = terms.filter(function (y) { return y !== x; }); render(); jcall('DELETE', '/api/shopping/terms/' + encodeURIComponent(x)).catch(function (e) { say(e.message, true); }); });
        c.appendChild(rm); chips.appendChild(c);
      });
      if (!terms.length) chips.appendChild(h('span', 'color-subdue size-h6', 'No alert words yet.'));
    }
    jcall('GET', '/api/shopping/state').then(function (d) { terms = d.terms || []; render(); }).catch(function () { say('glance-admin offline', true); });
    form.addEventListener('submit', function (ev) {
      ev.preventDefault(); if (!t.value.trim()) return;
      jcall('POST', '/api/shopping/terms', { term: t.value }).then(function (d) { terms.push(d.result.term); t.value = ''; render(); say('Added. Matching deals appear at the top of the Deals box within a minute.'); shopSummaryCache.at = 0; }).catch(function (e) { say(e.message, true); });
    });
  }

  /* ---- purchases and spend */
  function initShopSpend(node) {
    var buys = [];
    var form = h('form', 'wb-shop-form');
    var title = shopInput('What did you buy?', 'wb-shop-grow'), price = shopInput('£', 'wb-shop-qty', 'number'), store = shopInput('Shop', 'wb-shop-store'), cat = shopSelect(SHOP_CATS, 'Tech'), date = shopInput('', 'wb-shop-date', 'date');
    price.step = '0.01'; price.min = '0'; date.value = new Date().toISOString().slice(0, 10); date.title = 'Date bought';
    var add = h('button', '', 'Log'); add.type = 'submit';
    [title, price, store, cat, date, add].forEach(function (e) { form.appendChild(e); });
    var msg = h('div', 'size-h6 color-subdue wb-chan-msg'), say = shopSay(msg), chart = h('div', 'wb-spend'), list = h('div', 'wb-shop-list');
    node.appendChild(form); node.appendChild(msg); node.appendChild(chart); node.appendChild(list);
    function render() {
      var months = [], now = new Date();
      for (var i = 5; i >= 0; i--) { var d = new Date(now.getFullYear(), now.getMonth() - i, 1); months.push({ key: d.getFullYear() + '-' + ('0' + (d.getMonth() + 1)).slice(-2), label: d.toLocaleString('en-GB', { month: 'short' }), total: 0, cats: {} }); }
      buys.forEach(function (b) { var m = months.filter(function (x) { return b.date.slice(0, 7) === x.key; })[0]; if (m) { m.total += b.price; m.cats[b.cat] = (m.cats[b.cat] || 0) + b.price; } });
      var max = Math.max.apply(null, months.map(function (m) { return m.total; }).concat([1]));
      var cur = months[months.length - 1], avg = months.reduce(function (s, m) { return s + m.total; }, 0) / 6;
      var topCat = Object.keys(cur.cats).sort(function (a, b) { return cur.cats[b] - cur.cats[a]; })[0];
      chart.textContent = '';
      var stats = h('div', 'wb-stats margin-bottom-10');
      [[pound(cur.total) || '£0', 'THIS MONTH'], [pound(avg) || '£0', 'AVERAGE / MONTH'], [topCat || '-', 'TOP CATEGORY']].forEach(function (s) { var d = h('div'); d.appendChild(h('div', 'size-h3 color-highlight', s[0])); d.appendChild(h('div', 'size-h6', s[1])); stats.appendChild(d); });
      chart.appendChild(stats);
      var bars = h('div', 'wb-spend-bars');
      months.forEach(function (m) {
        var col = h('div', 'wb-spend-col'); col.title = m.label + ': ' + (pound(m.total) || '£0');
        var stack = h('div', 'wb-spend-stack'); stack.style.height = Math.max(2, Math.round(m.total / max * 100)) + '%';
        SHOP_CATS.forEach(function (c) { if (m.cats[c]) { var seg = h('div', 'wb-cat wb-cat-' + c.toLowerCase()); seg.style.flex = String(m.cats[c]); seg.title = c + ' ' + pound(m.cats[c]); stack.appendChild(seg); } });
        col.appendChild(stack); col.appendChild(h('div', 'size-h6 color-subdue', m.label)); bars.appendChild(col);
      });
      chart.appendChild(bars);
      var key = h('div', 'wb-pillrow margin-top-5'); SHOP_CATS.forEach(function (c) { var p = h('span', 'size-h6 color-subdue'); var dot = h('i', 'wb-dot wb-cat-' + c.toLowerCase()); p.appendChild(dot); p.appendChild(document.createTextNode(c + '  ')); key.appendChild(p); }); chart.appendChild(key);
      list.textContent = '';
      buys.slice().sort(function (a, b) { return b.date < a.date ? -1 : b.date > a.date ? 1 : 0; }).slice(0, 8).forEach(function (b) {
        var row = h('div', 'flex justify-between gap-10 size-h6');
        row.appendChild(h('span', 'text-truncate', b.title + (b.store ? '  ·  ' + b.store : '')));
        var r = h('span', 'shrink-0 color-subdue'); r.appendChild(document.createTextNode(pound(b.price) + '  ·  ' + b.cat + '  ·  ' + b.date.slice(5) + '  '));
        var x = h('button', 'wb-chan-del', '✕'); x.type = 'button'; x.title = 'Remove this entry';
        x.addEventListener('click', function () { buys = buys.filter(function (i) { return i.id !== b.id; }); render(); jcall('DELETE', '/api/shopping/purchase/' + b.id).catch(function (e) { say(e.message, true); }); });
        r.appendChild(x); row.appendChild(r); list.appendChild(row);
      });
    }
    jcall('GET', '/api/shopping/state').then(function (d) { buys = d.purchases || []; render(); }).catch(function () { say('glance-admin offline', true); });
    form.addEventListener('submit', function (ev) {
      ev.preventDefault(); if (!title.value.trim()) return;
      jcall('POST', '/api/shopping/purchase', { title: title.value, price: price.value, store: store.value, cat: cat.value, date: date.value }).then(function (d) { buys.push(d.result); title.value = ''; price.value = ''; render(); say(''); }).catch(function (e) { say(e.message, true); });
    });
  }

  /* ---- saved eBay searches (official API: needs EBAY_APP_ID / EBAY_CERT_ID) */
  function initShopEbay(node) {
    var state = { ebay: [] };
    var form = h('form', 'wb-shop-form');
    var q = shopInput('Saved search, e.g. "ddr3 8gb udimm"', 'wb-shop-grow'), mx = shopInput('Max £', 'wb-shop-qty', 'number');
    mx.step = '1'; mx.min = '0';
    var cond = shopSelect([['any', 'any condition'], ['new', 'new'], ['used', 'used']], 'any'), opts = shopSelect([['any', 'buy now or auction'], ['bin', 'buy it now'], ['auction', 'auctions']], 'any');
    var add = h('button', '', 'Save search'); add.type = 'submit';
    [q, mx, cond, opts, add].forEach(function (e) { form.appendChild(e); });
    var msg = h('div', 'size-h6 color-subdue wb-chan-msg'), say = shopSay(msg), out = h('div', 'wb-ebay');
    node.appendChild(form); node.appendChild(msg); node.appendChild(out);
    function card(i) {
      var c = h('div', 'wb-card'); var a = h('a'); a.href = i.url; a.target = '_blank'; a.title = i.title;
      var img = h('img'); img.alt = ''; img.classList.add('loaded', 'finished-transition'); img.loading = 'lazy'; img.src = i.img; img.style.aspectRatio = '1/1'; a.appendChild(img);
      a.appendChild(h('div', 'wb-title', i.title));
      a.appendChild(h('div', 'wb-sub wb-tag', pound(i.price) + (i.ship && parseFloat(i.ship) > 0 ? ' + ' + pound(i.ship) + ' p&p' : (i.ship === '0.00' ? ' + free p&p' : ''))));
      a.appendChild(h('div', 'wb-sub', (i.auction ? 'auction' : 'buy it now') + (i.cond ? ' · ' + i.cond : '') + (i.age_min !== null && i.age_min >= 0 ? ' · listed ' + agoMin(i.age_min) : '')));
      c.appendChild(a); return c;
    }
    function render(sum) {
      out.textContent = '';
      var res = {}; ((sum && sum.ebay && sum.ebay.searches) || []).forEach(function (s) { res[s.id] = s; });
      var configured = sum && sum.ebay_configured;
      if (!configured) {
        var n = h('div', 'wb-ebay-note size-h6');
        n.appendChild(document.createTextNode('eBay needs free developer keys before it can show listings: create an application at developer.ebay.com, then add EBAY_APP_ID (the App ID) and EBAY_CERT_ID (the Cert ID) from its production keyset to the .env on the server. Your saved searches below are kept and will start filling in as soon as the keys are there.'));
        out.appendChild(n);
      } else if (sum.ebay && sum.ebay.err) out.appendChild(h('div', 'color-negative size-h6', sum.ebay.err));
      state.ebay.forEach(function (s) {
        var box = h('div', 'wb-ebay-search'); var head = h('div', 'flex justify-between gap-10 items-center margin-bottom-5');
        var r = res[s.id] || {};
        head.appendChild(h('span', 'color-highlight', s.q + '  ' + (s.max ? '· up to ' + pound(s.max) : '') + (s.cond !== 'any' ? ' · ' + s.cond : '') + (s.opts !== 'any' ? ' · ' + (s.opts === 'bin' ? 'buy it now' : 'auctions') : '')));
        var right = h('span', 'size-h6 color-subdue'); right.appendChild(document.createTextNode((r.total !== undefined ? r.total + ' listings  ' : '')));
        var x = h('button', 'wb-chan-del', '✕'); x.type = 'button'; x.title = 'Remove this saved search';
        x.addEventListener('click', function () { state.ebay = state.ebay.filter(function (i) { return i.id !== s.id; }); render(sum); jcall('DELETE', '/api/shopping/ebay/' + s.id).catch(function (e) { say(e.message, true); }); });
        right.appendChild(x); head.appendChild(right); box.appendChild(head);
        if (r.err) box.appendChild(h('div', 'color-negative size-h6', r.err));
        else if (r.items && r.items.length) { var g = h('div', 'wb-results'); r.items.forEach(function (i) { g.appendChild(card(i)); }); box.appendChild(g); }
        else if (configured) box.appendChild(h('div', 'color-subdue size-h6', 'No listings match right now.'));
        out.appendChild(box);
      });
      if (!state.ebay.length) out.appendChild(h('div', 'color-subdue size-h6', 'No saved searches yet.'));
    }
    function load() { return jcall('GET', '/api/shopping/state').then(function (d) { state.ebay = d.ebay || []; return shopSummary(); }).then(render).catch(function () { say('glance-admin offline', true); }); }
    form.addEventListener('submit', function (ev) {
      ev.preventDefault(); if (!q.value.trim()) return;
      jcall('POST', '/api/shopping/ebay', { q: q.value, max: mx.value, cond: cond.value, opts: opts.value }).then(function (d) { state.ebay.push(d.result); q.value = ''; mx.value = ''; say('Saved. Results appear after the next refresh (up to 15 minutes).'); shopSummary().then(render); }).catch(function (e) { say(e.message, true); });
    });
    load(); setInterval(function () { shopSummary().then(render); }, 300000);
  }

  /* ---- price and stock watches (changedetection.io) */
  function initShopWatch(node) {
    var form = h('form', 'wb-shop-form');
    var url = shopInput('Product page address (https://...)', 'wb-shop-grow'), name = shopInput('Name (optional)', 'wb-shop-link');
    var lab = h('label', 'size-h6 color-subdue'); var br = h('input'); br.type = 'checkbox'; lab.appendChild(br); lab.appendChild(document.createTextNode(' use a real browser (for shops that need JavaScript)'));
    var add = h('button', '', 'Watch'); add.type = 'submit';
    [url, name, lab, add].forEach(function (e) { form.appendChild(e); });
    var msg = h('div', 'size-h6 color-subdue wb-chan-msg'), say = shopSay(msg), out = h('div', 'wb-watches');
    node.appendChild(form); node.appendChild(msg); node.appendChild(out);
    function render(sum) {
      out.textContent = '';
      var w = sum && sum.watches;
      if (!w || w.configured === false) { out.appendChild(h('div', 'color-subdue size-h6', 'changedetection.io is not set up yet.')); return; }
      if (w.ok === false) { out.appendChild(h('div', 'color-negative size-h6', w.err)); return; }
      if (!w.items.length) { out.appendChild(h('div', 'color-subdue size-h6', 'No watches yet. Paste a product page above, or press "Watch price" on a wishlist item.')); return; }
      w.items.forEach(function (it) {
        var row = h('div', 'wb-watch' + (it.at_target ? ' wb-watch-hit' : '') + (it.error ? ' wb-watch-bad' : ''));
        var top = h('div', 'flex justify-between gap-10 items-center'); var a = h('a', 'color-highlight text-truncate', it.title); a.href = it.url; a.target = '_blank';
        var pr = h('span', 'shrink-0 size-h3 ' + (it.at_target ? 'color-positive' : 'color-highlight'), it.price !== null ? pound(it.price) : (it.error ? '–' : '...'));
        top.appendChild(a); top.appendChild(pr); row.appendChild(top);
        var meta = [];
        if (it.in_stock === true) meta.push('in stock'); else if (it.in_stock === false) meta.push('out of stock');
        if (it.prev !== null && it.price !== null && it.prev !== it.price) meta.push((it.price < it.prev ? '▼ ' : '▲ ') + pound(Math.abs(it.price - it.prev)) + ' (' + it.change_pct + '%) since last change');
        if (it.target) meta.push('target ' + pound(it.target) + (it.at_target ? ' ✓' : ''));
        meta.push(it.age_min !== null ? 'checked ' + agoMin(it.age_min) : 'not checked yet');
        row.appendChild(h('div', 'size-h6 ' + (it.error ? 'color-negative' : 'color-subdue'), it.error ? it.error : meta.join('  ·  ')));
        var acts = h('div', 'wb-shop-acts');
        var rc = h('button', 'wb-chan-del', 'Check now'); rc.type = 'button'; rc.addEventListener('click', function () { rc.disabled = true; jcall('POST', '/api/shopping/watch/' + it.id + '/recheck', {}).then(function () { say('Checking... refresh in a minute.'); setTimeout(function () { shopSummary(true).then(render); }, 20000); }).catch(function (e) { say(e.message, true); }); });
        var rm = h('button', 'wb-chan-del', '✕ Remove'); rm.type = 'button'; var armed = false, tm;
        rm.addEventListener('click', function () { if (!armed) { armed = true; rm.textContent = 'Sure?'; rm.classList.add('wb-chan-armed'); tm = setTimeout(function () { armed = false; rm.textContent = '✕ Remove'; rm.classList.remove('wb-chan-armed'); }, 3000); return; } clearTimeout(tm); jcall('DELETE', '/api/shopping/watch/' + it.id).then(function () { shopSummary(true).then(render); }).catch(function (e) { say(e.message, true); }); });
        acts.appendChild(rc); acts.appendChild(rm); row.appendChild(acts); out.appendChild(row);
      });
    }
    form.addEventListener('submit', function (ev) {
      ev.preventDefault(); if (!url.value.trim()) return; add.disabled = true; say('Adding the watch...');
      jcall('POST', '/api/shopping/watch', { url: url.value, title: name.value, browser: br.checked }).then(function () { url.value = ''; name.value = ''; say('Watching. The first check runs within a minute; then every 6 hours.'); setTimeout(function () { shopSummary(true).then(render); }, 25000); })
        .catch(function (e) { say(e.message, true); }).then(function () { add.disabled = false; });
    });
    shopSummary().then(render); setInterval(function () { shopSummary().then(render); }, 120000);
  }

  /* ------------------------------------------------------------------ LIVE camera streams
     <img data-live-src="...mjpeg..." data-still="...jpg">: the still is shown by default; the MJPEG stream is attached only
     while the image is on screen AND the tab is visible, and dropped again otherwise (a live stream costs ~120 KB/s). */
  var liveImgs = [];
  function liveUpdate(img) {
    var on = img.__vis && !document.hidden;
    var want = on ? img.getAttribute('data-live-src') : img.getAttribute('data-still');
    if (img.__cur !== want) { img.__cur = want; img.src = want; }
    img.classList.toggle('wb-live-on', !!on);
  }
  function initLive(img) {
    img.__vis = false;
    liveImgs.push(img);
    if ('IntersectionObserver' in window) {
      new IntersectionObserver(function (es) { es.forEach(function (e) { img.__vis = e.isIntersecting; liveUpdate(img); }); }, { threshold: 0.25 }).observe(img);
    } else { img.__vis = true; liveUpdate(img); }
  }
  document.addEventListener('visibilitychange', function () { liveImgs = liveImgs.filter(function (i) { return document.body.contains(i); }); liveImgs.forEach(liveUpdate); });

  /* ------------------------------------------------------------------ carousel arrows
     Glance's video carousels and my cover strips scroll sideways but have no controls. Each scroller gets
     left/right buttons (shown only while there is more to scroll in that direction). */
  function addArrows(scroller) {
    scroller.__wbArrows = true;
    var host = scroller.parentNode;
    if (!scroller.classList.contains('carousel-items-container')) {        // my strips: wrap so the buttons can be positioned
      var wrap = document.createElement('div');
      Array.prototype.slice.call(scroller.classList).forEach(function (c) { if (c.indexOf('margin-') === 0) { wrap.classList.add(c); scroller.classList.remove(c); } });
      scroller.parentNode.insertBefore(wrap, scroller);
      wrap.appendChild(scroller);
      host = wrap;
    }
    host.classList.add('wb-arrows');
    function btn(dir) {
      var b = document.createElement('button');
      b.type = 'button'; b.className = 'wb-arrow wb-arrow-' + dir; b.hidden = true;
      b.textContent = dir === 'l' ? '‹' : '›';
      b.setAttribute('aria-label', dir === 'l' ? 'Scroll left' : 'Scroll right');
      b.addEventListener('click', function (ev) {
        ev.preventDefault();
        scroller.scrollBy({ left: (dir === 'l' ? -1 : 1) * Math.max(200, scroller.clientWidth * 0.8), behavior: 'smooth' });
      });
      host.appendChild(b);
      return b;
    }
    var l = btn('l'), r = btn('r');
    function update() {
      var max = scroller.scrollWidth - scroller.clientWidth;
      l.hidden = scroller.scrollLeft < 8;
      r.hidden = max < 8 || scroller.scrollLeft > max - 8;
    }
    scroller.addEventListener('scroll', debounce(update, 30), { passive: true });
    window.addEventListener('resize', debounce(update, 100));
    host.addEventListener('mouseenter', update);            // rows inside a locked widget are measured once they are visible
    update();
    setTimeout(update, 600); setTimeout(update, 2500);      // images/thumbnails settle after load
  }

  /* ------------------------------------------------------------------ VPN (per-device NordVPN control)
     Talks to glance-admin /api/vpn/*, which forwards to wbs-vpn-dashboard. Writes send X-WB-VPN (a custom header, so a
     page on another origin cannot trigger them). Each device runs a small agent; "busy" means a command is still running. */
  function initVpn(node) {
    var HDR = { 'Content-Type': 'application/json', 'X-WB-VPN': '1' };
    var stats = h('div', 'wb-stats margin-bottom-15');
    var list = h('div', 'wb-vpn-list');
    var msg = h('div', 'size-h6 color-subdue wb-vpn-msg');
    node.appendChild(stats); node.appendChild(list); node.appendChild(msg);
    var chosen = {}, data = null, timer = null;

    function say(t, bad) { msg.textContent = t; msg.className = 'size-h6 wb-vpn-msg ' + (bad ? 'color-negative' : 'color-subdue'); }
    function pretty(c) { return String(c || '').replace(/_/g, ' '); }
    function ago(s) { if (s == null) return 'never'; return s < 90 ? s + 's ago' : s < 5400 ? Math.round(s / 60) + 'm ago' : s < 172800 ? Math.round(s / 3600) + 'h ago' : Math.round(s / 86400) + 'd ago'; }
    function call(method, path, body) {
      return fetch(API + path, { method: method, headers: body ? HDR : {}, body: body ? JSON.stringify(body) : undefined })
        .then(function (r) { return r.json().catch(function () { return {}; }).then(function (d) { if (!r.ok) throw new Error(d.error || ('HTTP ' + r.status)); return d; }); });
    }
    function send(body) {
      say('Sending...');
      return call('POST', '/api/vpn/command', body).then(function () { say('Working...'); poll(1200); })
        .catch(function (e) { say(e.message, true); });
    }
    function stat(n, label, cls) {
      var d = h('div'), v = h('div', 'size-h3 ' + cls, String(n)); d.appendChild(v); d.appendChild(h('div', 'size-h6', label)); return d;
    }
    function toggle(label, on, disabled, onchange) {
      var l = h('label', 'wb-vpn-tog size-h6'), cb = h('input'); cb.type = 'checkbox'; cb.checked = on; cb.disabled = disabled;
      cb.addEventListener('change', function () { onchange(cb.checked); });
      l.appendChild(cb); l.appendChild(document.createTextNode(' ' + label)); return l;
    }

    function row(d, countries) {
      var r = h('div', 'wb-vpn-row' + (d.online ? '' : ' wb-vpn-off'));
      var top = h('div', 'wb-vpn-top');
      var dot = h('span', d.online ? (d.connected ? 'color-positive' : 'color-subdue') : 'color-negative', '●');
      var main = h('div', 'wb-vpn-main');
      main.appendChild(h('div', 'color-highlight text-truncate', d.name));
      var sub = !d.online ? 'offline · seen ' + ago(d.seen_s)
        : !d.nord ? 'NordVPN not installed'
        : d.connected ? 'Connected · ' + pretty(d.country) + (d.city ? ', ' + d.city : '') + (d.ip ? ' · ' + d.ip : '')
        : 'Disconnected';
      main.appendChild(h('div', 'size-h6 color-subdue text-truncate', sub));
      top.appendChild(dot); top.appendChild(main); r.appendChild(top);

      var usable = d.online && d.nord;
      var ctl = h('div', 'wb-vpn-ctl');
      var sel = h('select');
      countries.forEach(function (c) { var o = h('option', '', pretty(c)); o.value = c; sel.appendChild(o); });
      sel.value = chosen[d.id] || (d.country ? d.country.replace(/ /g, '_') : 'United_Kingdom');
      if (!sel.value) sel.selectedIndex = 0;
      sel.disabled = !usable;
      sel.addEventListener('change', function () { chosen[d.id] = sel.value; });
      var go = h('button', 'wb-vpn-go', d.connected ? 'Switch' : 'Connect'); go.type = 'button'; go.disabled = !usable || d.busy;
      go.addEventListener('click', function () { chosen[d.id] = sel.value; send({ id: d.id, type: 'connect', country: sel.value }); });
      var stop = h('button', '', 'Disconnect'); stop.type = 'button'; stop.disabled = !usable || d.busy || !d.connected;
      stop.addEventListener('click', function () { send({ id: d.id, type: 'disconnect' }); });
      ctl.appendChild(sel); ctl.appendChild(go); ctl.appendChild(stop); r.appendChild(ctl);

      var tg = h('div', 'wb-vpn-tgs');
      tg.appendChild(toggle('Kill switch', d.kill_switch, !usable || d.busy || (!d.connected && !d.kill_switch), function (v) { send({ id: d.id, type: 'killswitch', value: v ? 'on' : 'off' }); }));
      tg.appendChild(toggle('Tailscale', d.tailscale === 'up', !d.online || d.busy || d.tailscale === 'absent', function (v) { send({ id: d.id, type: 'tailscale', value: v ? 'on' : 'off' }); }));
      var dl = h('label', 'wb-vpn-tog size-h6'), ds = h('select', 'wb-vpn-dns');
      dl.title = 'How name lookups are handled while connected. Nord DNS: private, but local names do not resolve. Local names via Pi-hole: your local domain keeps working, the internet still uses Nord DNS. Pi-hole for everything: ad blocking everywhere, but lookups leave through your home connection.';
      [['nord', 'Nord DNS'], ['split', 'Local names via Pi-hole'], ['pihole', 'Pi-hole for everything']].forEach(function (m) { var o = h('option', '', m[1]); o.value = m[0]; ds.appendChild(o); });
      ds.value = d.dns_mode || 'nord'; ds.disabled = !usable || d.busy;
      ds.addEventListener('change', function () { send({ id: d.id, type: 'dns_mode', value: ds.value }); });
      dl.appendChild(document.createTextNode('DNS ')); dl.appendChild(ds); tg.appendChild(dl); r.appendChild(tg);

      var note = null;
      if (d.busy) note = ['Working...', false];
      else if (d.error) note = [d.error, true];
      else if (d.last) note = [d.last.message + ' · ' + ago(d.last.age_s), !d.last.ok];
      if (note) r.appendChild(h('div', 'size-h6 wb-vpn-note ' + (note[1] ? 'color-negative' : 'color-subdue'), note[0]));
      return r;
    }

    function render() {
      if (!data) return;
      stats.textContent = '';
      stats.appendChild(stat(data.online, 'ONLINE', 'color-positive'));
      stats.appendChild(stat(data.connected, 'ON VPN', 'color-highlight'));
      stats.appendChild(stat(data.total, 'DEVICES', 'color-highlight'));
      list.textContent = '';
      data.devices.forEach(function (d) { list.appendChild(row(d, data.countries)); });
      if (!data.devices.length) list.appendChild(h('div', 'size-h6 color-subdue', 'No devices yet. Add one in the VPN panel.'));
    }
    function busy() { return data && data.devices.some(function (d) { return d.busy; }); }
    function poll(ms) {
      clearTimeout(timer);
      timer = setTimeout(function () {
        if (!document.body.contains(node)) return;
        var a = document.activeElement;
        if (a && node.contains(a) && a.tagName === 'SELECT') { poll(2000); return; }      // do not close an open dropdown
        call('GET', '/api/vpn/summary').then(function (d) { data = d; render(); if (msg.className.indexOf('negative') < 0 && !busy()) say(''); })
          .catch(function () { say('VPN panel unreachable', true); })
          .then(function () { poll(busy() ? 1500 : 6000); });
      }, ms);
    }
    poll(10);
  }

  /* ------------------------------------------------------------------ REMOTE (SSH terminal + remote desktops through Termix)
     glance-admin /api/remote/hosts lists the hosts defined in Termix (add a host there and it appears here). The terminal is Termix's
     standalone terminal view in an iframe (?view=terminal&hostId=N); a desktop opens Termix's standalone viewer in a new tab
     (?view=vnc|rdp&hostId=N). Termix must be opened by the SAME hostname as Glance (its login cookie is per host), so the base URL is
     built from location.hostname. The iframe is sandboxed without allow-modals, so Termix's "leave this page?" prompt cannot appear. */
  var remoteState = { at: 0, p: null };
  function remoteHosts() {
    if (remoteState.p && Date.now() - remoteState.at < 20000) return remoteState.p;
    remoteState.at = Date.now();
    remoteState.p = api('GET', '/api/remote/hosts');
    remoteState.p.catch(function () { remoteState.p = null; });
    return remoteState.p;
  }
  function termixUrl(d, view, id) { return location.protocol + '//' + location.hostname + ':' + (d.termix_port || 8080) + '/?view=' + view + '&hostId=' + id; }
  function upClass(x) { return x.up === true ? 'color-positive' : x.up === false ? 'color-negative' : 'color-subdue'; }

  function initRemoteDesktops(node) {
    var list = h('div', 'wb-rem-list'), msg = h('div', 'size-h6 color-subdue wb-rem-msg');
    node.appendChild(list); node.appendChild(msg);
    function render(d) {
      var rows = d.hosts.filter(function (x) { return x.kind === 'desktop'; });
      list.textContent = ''; msg.textContent = '';
      rows.forEach(function (x) {
        var a = h('a', 'wb-rem-row');
        a.href = termixUrl(d, x.protocol === 'rdp' ? 'rdp' : 'vnc', x.id); a.target = '_blank'; a.rel = 'noopener';
        a.title = 'Open ' + x.name + ' in a new tab (press F11 there for full screen)';
        var main = h('div', 'wb-rem-main');
        main.appendChild(h('div', 'color-highlight text-truncate', x.name));
        main.appendChild(h('div', 'size-h6 color-subdue text-truncate', String(x.protocol).toUpperCase() + ' · ' + x.address + ':' + x.port));
        a.appendChild(h('span', upClass(x), '●')); a.appendChild(main); a.appendChild(h('span', 'size-h6 color-primary', 'Open ↗'));
        list.appendChild(a);
      });
      if (!rows.length) list.appendChild(h('div', 'size-h6 color-subdue', 'No remote desktops in Termix yet. Add a VNC or RDP host there and it appears here.'));
    }
    function load() {
      remoteHosts().then(render).catch(function (e) { msg.className = 'size-h6 color-negative wb-rem-msg'; msg.textContent = 'Termix list unavailable (' + e.message + ')'; });
    }
    load();
    node.__wbTimer = setInterval(function () { if (!document.body.contains(node)) clearInterval(node.__wbTimer); else load(); }, 30000);
  }

  function initRemoteTerminal(node) {
    var bar = h('div', 'wb-rem-bar'), sel = h('select', 'wb-rem-sel'); sel.disabled = true;
    function btn(label, cls) { var b = h('button', 'wb-rem-btn' + (cls ? ' ' + cls : ''), label); b.type = 'button'; return b; }
    var go = btn('Connect', 'wb-rem-go'), pop = btn('Pop out ↗'), files = btn('Files ↗'), full = btn('Full screen'), shut = btn('Close');
    [sel, go, pop, files, full, shut].forEach(function (e) { bar.appendChild(e); });
    var stage = h('div', 'wb-rem-stage'), hint = h('div', 'size-h6 color-subdue wb-rem-hint', 'Pick a host and press Connect.');
    stage.appendChild(hint);
    var info = h('div', 'size-h6 color-subdue wb-rem-msg');
    node.appendChild(bar); node.appendChild(stage); node.appendChild(info);
    var data = null, frame = null;

    function cur() { var id = parseInt(sel.value, 10); return data && id ? data.hosts.filter(function (x) { return x.id === id; })[0] : null; }
    function describe() { var x = cur(); info.className = 'size-h6 color-subdue wb-rem-msg'; info.textContent = x ? x.name + ' · ' + x.address + ':' + x.port + ' · ' + (x.up === true ? 'reachable' : x.up === false ? 'not answering' : 'not checked') : ''; }
    function close() { if (frame) { frame.src = 'about:blank'; frame.remove(); frame = null; } stage.textContent = ''; stage.appendChild(hint); }
    function connect() {
      var x = cur(); if (!x) return;
      close();
      frame = document.createElement('iframe');
      frame.className = 'wb-rem-frame'; frame.title = x.name;
      frame.setAttribute('sandbox', 'allow-scripts allow-same-origin allow-forms allow-popups allow-downloads');
      frame.setAttribute('allow', 'clipboard-read; clipboard-write; fullscreen');
      frame.src = termixUrl(data, 'terminal', x.id);
      stage.textContent = ''; stage.appendChild(frame);
      try { localStorage.setItem('wbRemoteHost', String(x.id)); } catch (e) { /* ignore */ }
    }
    go.addEventListener('click', connect);
    sel.addEventListener('change', function () { describe(); if (frame) connect(); });   // switching host while connected reconnects
    shut.addEventListener('click', close);
    pop.addEventListener('click', function () { var x = cur(); if (x) window.open(termixUrl(data, 'terminal', x.id), '_blank', 'noopener'); });
    files.addEventListener('click', function () { var x = cur(); if (x) window.open(termixUrl(data, 'file-manager', x.id), '_blank', 'noopener'); });
    full.addEventListener('click', function () { if (stage.requestFullscreen) stage.requestFullscreen().catch(function () { /* ignore */ }); });

    function fill(d) {
      data = d;
      var keep = sel.value, last = ''; try { last = localStorage.getItem('wbRemoteHost') || ''; } catch (e) { /* ignore */ }
      var ssh = d.hosts.filter(function (x) { return x.kind === 'ssh'; }), groups = {};
      sel.textContent = '';
      var ph = h('option', '', ssh.length ? 'Choose a host...' : 'No SSH hosts in Termix'); ph.value = ''; sel.appendChild(ph);
      ssh.forEach(function (x) {
        var key = x.folder || 'Other';
        if (!groups[key]) { groups[key] = h('optgroup'); groups[key].label = key; sel.appendChild(groups[key]); }
        var o = h('option', '', x.name + '  (' + x.address + ')'); o.value = String(x.id); groups[key].appendChild(o);
      });
      sel.value = keep || last || ''; if (sel.value === '' && last) sel.value = '';
      sel.disabled = !ssh.length; describe();
    }
    function load() { remoteHosts().then(fill).catch(function (e) { info.className = 'size-h6 color-negative wb-rem-msg'; info.textContent = 'Termix list unavailable (' + e.message + ')'; }); }
    load();
    node.__wbTimer = setInterval(function () { if (!document.body.contains(node)) { clearInterval(node.__wbTimer); } else if (document.activeElement !== sel) { remoteHosts().then(function (d) { data = d; }).catch(function () { /* keep the last list */ }); } }, 60000);
  }

  /* ------------------------------------------------------------------ boot */
  var INIT = { find: initFind, search: initSearch, notes: initNotes, todo: initTodo, channels: initChannels, news: initNews, 'cam-events': initCamEvents, 'shop-list': initShopList, 'shop-wish': initShopWish, 'shop-terms': initShopTerms, 'shop-spend': initShopSpend, 'shop-ebay': initShopEbay, 'shop-watch': initShopWatch, bookmarks: initBookmarks, vpn: initVpn, 'remote-desktops': initRemoteDesktops, 'remote-terminal': initRemoteTerminal };
  var pending = false;
  function scan() {
    pending = false;
    document.querySelectorAll('[data-wb]').forEach(function (n) {
      if (n.__wb) return;
      n.__wb = true;
      var f = INIT[n.getAttribute('data-wb')];
      if (f) { try { f(n); } catch (e) { console.error('wb init failed', e); } }
    });
    document.querySelectorAll('img[data-live-src]').forEach(function (i) { if (!i.__live) { i.__live = true; initLive(i); } });
    document.querySelectorAll('.carousel-items-container, .wb-strip').forEach(function (s) { if (!s.__wbArrows) { try { addArrows(s); } catch (e) { console.error('wb arrows failed', e); } } });
    // arriving on another tab mid-find: keep the strip and the highlight alive
    var s = getSession();
    if (s) { updateStrip(s); if (!ui.__applied || ui.__appliedFor !== location.pathname) { ui.__applied = true; ui.__appliedFor = location.pathname; applyHighlight(s); } }
  }
  function schedule() { if (!pending) { pending = true; setTimeout(scan, 40); } }  // not requestAnimationFrame: it is paused in background tabs
  new MutationObserver(schedule).observe(document.documentElement, { childList: true, subtree: true });
  document.addEventListener('DOMContentLoaded', schedule);
  schedule();

  // '/' focuses the Find box on Home
  document.addEventListener('keydown', function (e) {
    var t = (document.activeElement && document.activeElement.tagName) || '';
    if (e.key === '/' && t !== 'INPUT' && t !== 'TEXTAREA') {
      var f = document.querySelector('.wb-find-input');
      if (f) { e.preventDefault(); f.focus(); }
    }
  });
})();
