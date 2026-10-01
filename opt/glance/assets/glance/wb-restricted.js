/* WB homelab - PIN-gated, collapsed-by-default widgets (any widget with css-class "wb-restricted").
   This is CASUAL privacy, not security: the widget data is still in the page source.
   The PIN is never stored here, only a salted SHA-256 (window.WB_RESTRICTED = {salt, hash} from wb-restricted-config.js).
   crypto.subtle is unavailable on plain http, so SHA-256 is implemented below. */
(function () {
  'use strict';
  var KEY = 'wbUnlocked';

  /* ---- minimal SHA-256 (UTF-8 string -> hex) ---- */
  function sha256(str) {
    var K = [0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2];
    var H = [0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19];
    var utf8 = unescape(encodeURIComponent(str));
    var bytes = [], i;
    for (i = 0; i < utf8.length; i++) bytes.push(utf8.charCodeAt(i));
    var bitLen = bytes.length * 8;
    bytes.push(0x80);
    while (bytes.length % 64 !== 56) bytes.push(0);
    for (i = 7; i >= 0; i--) bytes.push(i >= 4 ? 0 : (bitLen >>> (i * 8)) & 0xff);
    function rotr(x, n) { return (x >>> n) | (x << (32 - n)); }
    for (var off = 0; off < bytes.length; off += 64) {
      var w = new Array(64);
      for (i = 0; i < 16; i++) w[i] = (bytes[off + 4*i] << 24) | (bytes[off + 4*i + 1] << 16) | (bytes[off + 4*i + 2] << 8) | bytes[off + 4*i + 3];
      for (i = 16; i < 64; i++) {
        var s0 = rotr(w[i-15], 7) ^ rotr(w[i-15], 18) ^ (w[i-15] >>> 3);
        var s1 = rotr(w[i-2], 17) ^ rotr(w[i-2], 19) ^ (w[i-2] >>> 10);
        w[i] = (w[i-16] + s0 + w[i-7] + s1) | 0;
      }
      var a = H[0], b = H[1], c = H[2], d = H[3], e = H[4], f = H[5], g = H[6], hh = H[7];
      for (i = 0; i < 64; i++) {
        var S1 = rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25);
        var ch = (e & f) ^ (~e & g);
        var t1 = (hh + S1 + ch + K[i] + w[i]) | 0;
        var S0 = rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22);
        var mj = (a & b) ^ (a & c) ^ (b & c);
        var t2 = (S0 + mj) | 0;
        hh = g; g = f; f = e; e = (d + t1) | 0; d = c; c = b; b = a; a = (t1 + t2) | 0;
      }
      H[0] = (H[0] + a) | 0; H[1] = (H[1] + b) | 0; H[2] = (H[2] + c) | 0; H[3] = (H[3] + d) | 0;
      H[4] = (H[4] + e) | 0; H[5] = (H[5] + f) | 0; H[6] = (H[6] + g) | 0; H[7] = (H[7] + hh) | 0;
    }
    return H.map(function (x) { return ('00000000' + (x >>> 0).toString(16)).slice(-8); }).join('');
  }

  function cfg() { return window.WB_RESTRICTED || null; }
  function unlocked() { try { return sessionStorage.getItem(KEY) === '1'; } catch (e) { return false; } }
  function setUnlocked(v) { try { if (v) sessionStorage.setItem(KEY, '1'); else sessionStorage.removeItem(KEY); } catch (e) { /* ignore */ } }

  // while locked the title shows a generic label and the title link is removed, so neither the name nor the target is shown
  function maskTitle(w, open) {
    var h = w.querySelector('.widget-header h2');
    if (!h) return;
    var a = h.querySelector('a'), t = a || h;
    if (!w.__wbTitle) w.__wbTitle = { text: t.textContent, href: a ? a.getAttribute('href') : null };
    if (open) {
      t.textContent = w.__wbTitle.text;
      if (a && w.__wbTitle.href) a.setAttribute('href', w.__wbTitle.href);
    } else {
      t.textContent = 'Private';
      if (a) a.removeAttribute('href');
    }
  }

  function apply() {
    var open = unlocked();
    document.querySelectorAll('.wb-restricted').forEach(function (w) {
      w.classList.toggle('wb-locked', !open);
      maskTitle(w, open);
      var btn = w.querySelector('.wb-lock-toggle');
      if (btn) btn.textContent = open ? 'lock' : '';
      var form = w.querySelector('.wb-unlock');
      if (form && open) form.hidden = true;
      // locked rows ship images as data-src so nothing private is fetched until the PIN is entered
      if (open) w.querySelectorAll('img[data-src]').forEach(function (i) { i.src = i.getAttribute('data-src'); i.removeAttribute('data-src'); });
    });
  }

  function setup(w) {
    w.__wbRestricted = true;
    var header = w.querySelector('.widget-header');
    if (!header) { header = document.createElement('div'); header.className = 'widget-header'; w.insertBefore(header, w.firstChild); }
    var btn = document.createElement('button');
    btn.type = 'button'; btn.className = 'wb-lock-toggle';
    header.appendChild(btn);

    var form = document.createElement('form');
    form.className = 'wb-unlock'; form.hidden = true;
    var inp = document.createElement('input');
    inp.type = 'password'; inp.placeholder = 'PIN'; inp.autocomplete = 'off'; inp.inputMode = 'numeric';
    var go = document.createElement('button'); go.type = 'submit'; go.textContent = 'Unlock';
    var msg = document.createElement('span'); msg.className = 'size-h6 color-negative';
    form.appendChild(inp); form.appendChild(go); form.appendChild(msg);
    header.insertAdjacentElement('afterend', form);

    function reveal() { if (!unlocked()) { form.hidden = !form.hidden; msg.textContent = ''; if (!form.hidden) inp.focus(); } }
    header.addEventListener('click', function (ev) {
      if (ev.target === btn) { if (unlocked()) { setUnlocked(false); apply(); } return; }
      if (ev.target.closest('a')) return;           // let the title link work
      reveal();
    });
    form.addEventListener('submit', function (ev) {
      ev.preventDefault();
      var c = cfg();
      if (!c) { msg.textContent = 'not configured'; return; }
      if (sha256(c.salt + inp.value) === c.hash) { setUnlocked(true); inp.value = ''; apply(); }
      else { msg.textContent = 'wrong PIN'; inp.value = ''; }
    });
  }

  var pending = false;
  function scan() {
    pending = false;
    document.querySelectorAll('.wb-restricted').forEach(function (w) { if (!w.__wbRestricted) setup(w); });
    apply();
  }
  function schedule() { if (!pending) { pending = true; setTimeout(scan, 40); } }
  new MutationObserver(schedule).observe(document.documentElement, { childList: true, subtree: true });
  document.addEventListener('DOMContentLoaded', schedule);
  schedule();
  window.__wbSha256 = sha256;   // exposed for self-test
})();
