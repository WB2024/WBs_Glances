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

  /* ------------------------------------------------------------------ CAMERA detection search (Cameras page)
     Type + camera + date/time range -> glance-admin /api/cameras/events -> a scrollable strip of thumbnails straight from Frigate. */
  function initCamEvents(node) {
    var FR = node.getAttribute('data-frigate') || '';
    var UI = node.getAttribute('data-frigate-ui') || FR;
    var form = h('form', 'wb-chan-add wb-cam-search');
    var selType = h('select'), selCam = h('select'), selRange = h('select');
    [['1', 'Last hour'], ['6', 'Last 6 hours'], ['24', 'Last 24 hours'], ['168', 'Last 7 days'], ['custom', 'Custom range...']].forEach(function (r) {
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
    [selType, selCam, selRange, from, to, go].forEach(function (e) { form.appendChild(e); });
    var msg = h('div', 'size-h6 color-subdue wb-chan-msg');
    var strip = h('div', 'wb-strip');
    node.appendChild(form); node.appendChild(msg); node.appendChild(strip);

    function opt(sel, value, text) { var o = h('option', '', text); o.value = value; sel.appendChild(o); }
    opt(selType, '', 'All types'); opt(selCam, '', 'All cameras');
    fetch(API + '/api/cameras/summary').then(function (r) { return r.json(); }).then(function (d) {
      (d.label_names || []).forEach(function (l) { opt(selType, l, l); });
      (d.cameras || []).forEach(function (c) { opt(selCam, c.name, c.name); });
    }).catch(function () { /* the filters simply stay on "all" */ });
    selRange.addEventListener('change', function () { var c = selRange.value === 'custom'; from.hidden = !c; to.hidden = !c; });

    function fmt(ts) { return new Date(ts * 1000).toLocaleString('en-GB', { weekday: 'short', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }); }
    function card(e) {
      var c = h('div', 'wb-card'); c.style.flexBasis = '12rem';
      var a = h('a'); a.href = FR + '/api/events/' + e.id + '/snapshot.jpg'; a.target = '_blank';
      var img = h('img'); img.src = FR + '/api/events/' + e.id + '/thumbnail.jpg'; img.alt = ''; img.loading = 'lazy'; img.style.aspectRatio = '16/10';
      a.appendChild(img);
      a.appendChild(h('div', 'wb-title', e.sub || e.label));
      a.appendChild(h('div', 'wb-sub', e.camera + ' · ' + fmt(e.start) + (e.seconds ? ' · ' + e.seconds + 's' : '') + (e.score ? ' · ' + e.score + '%' : '')));
      c.appendChild(a);
      if (e.clip) { var cl = h('a', 'size-h6 color-subdue', 'clip'); cl.href = FR + '/api/events/' + e.id + '/clip.mp4'; cl.target = '_blank'; c.appendChild(cl); }
      return c;
    }
    function search() {
      var after, before = 0;
      if (selRange.value === 'custom') {
        after = Math.floor(new Date(from.value).getTime() / 1000); before = Math.floor(new Date(to.value).getTime() / 1000);
        if (!after || !before || after >= before) { msg.className = 'size-h6 wb-chan-msg color-negative'; msg.textContent = 'Pick a start that is before the end.'; return; }
      } else { after = Math.floor(Date.now() / 1000) - parseInt(selRange.value, 10) * 3600; }
      var q = '?limit=120&after=' + after + (before ? '&before=' + before : '') + (selType.value ? '&label=' + encodeURIComponent(selType.value) : '') + (selCam.value ? '&camera=' + encodeURIComponent(selCam.value) : '');
      go.disabled = true; msg.className = 'size-h6 wb-chan-msg color-subdue'; msg.textContent = 'Searching...';
      fetch(API + '/api/cameras/events' + q).then(function (r) { return r.json().then(function (d) { if (!r.ok) throw new Error(d.error || ('HTTP ' + r.status)); return d; }); })
        .then(function (d) {
          strip.textContent = '';
          d.events.forEach(function (e) { strip.appendChild(card(e)); });
          strip.scrollLeft = 0; strip.dispatchEvent(new Event('scroll'));
          msg.textContent = d.count ? (d.count + ' detection' + (d.count === 1 ? '' : 's') + (d.capped ? ' (showing the newest 120: narrow the range to see others)' : '') + '  ·  newest first, scroll sideways for more') : 'Nothing detected in that range.';
        })
        .catch(function (e) { msg.className = 'size-h6 wb-chan-msg color-negative'; msg.textContent = e.message; })
        .then(function () { go.disabled = false; });
    }
    form.addEventListener('submit', function (ev) { ev.preventDefault(); search(); });
    search();
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

  /* ------------------------------------------------------------------ boot */
  var INIT = { find: initFind, search: initSearch, notes: initNotes, todo: initTodo, channels: initChannels, news: initNews, 'cam-events': initCamEvents, bookmarks: initBookmarks };
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
