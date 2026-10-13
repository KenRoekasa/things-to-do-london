/* Swipe Together — both people swipe the same deck blind, then see the matches.
   No server: a session travels in the URL hash as
     #<card ids, 5 chars each>/<A's answers>/<A's name>/<B's answers>/<B's name>/<when label>
   Answers are a yes/no bitmask over the deck order, written in base 36.

   Picks made by ticking the guide itself (pick mode in app.js) arrive as
     #p/<A's picked ids>/<A's name>[/<B's picked ids>/<B's name>]
   and only carry what was ticked, since the "deck" is the whole guide. */
(function () {
  'use strict';

  var $ = function (sel, ctx) { return (ctx || document).querySelector(sel); };
  var $$ = function (sel, ctx) {
    return Array.prototype.slice.call((ctx || document).querySelectorAll(sel));
  };

  var ALL = JSON.parse($('#sw-data').textContent);
  var BY_ID = {};
  ALL.forEach(function (c) { BY_ID[c.id] = c; });
  var OPEN_ENDED = 90;  // days an "Opens …" with no stated end counts as on, as in the API

  var state = {
    deck: [],        // cards for this session, in order
    answers: [],     // this swiper's yes/no, by deck position
    a: null,         // { name, mask } — the first person, once they've finished
    b: null,
    when: '',        // label for the results, e.g. "Sat 24 Oct"
    pickLink: '',    // guide pick mode: where the partner goes to make their picks
    swiper: 'a'      // who is holding the phone
  };

  /* ---------------------------------------------------------- helpers --- */

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"]/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c];
    });
  }
  function iso(d) {
    return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' +
      String(d.getDate()).padStart(2, '0');
  }
  function parse(s) { var p = s.split('-'); return new Date(+p[0], +p[1] - 1, +p[2]); }
  function addDays(d, n) { var x = new Date(d); x.setDate(x.getDate() + n); return x; }
  function today() { var t = new Date(); return new Date(t.getFullYear(), t.getMonth(), t.getDate()); }
  function nice(d) {
    return d.toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short' });
  }

  // seeded shuffle, so a deck is reproducible while testing
  function rng(seed) {
    return function () {
      seed |= 0; seed = seed + 0x6D2B79F5 | 0;
      var t = Math.imul(seed ^ seed >>> 15, 1 | seed);
      t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t;
      return ((t ^ t >>> 14) >>> 0) / 4294967296;
    };
  }

  function maskOf(bits) {
    var n = 0n;
    bits.forEach(function (b, i) { if (b) n |= 1n << BigInt(i); });
    return n.toString(36);
  }
  function bitsOf(mask, length) {
    var n = 0n;
    for (var i = 0; i < mask.length; i++) n = n * 36n + BigInt(parseInt(mask[i], 36));
    var out = [];
    for (var j = 0; j < length; j++) out.push(((n >> BigInt(j)) & 1n) === 1n);
    return out;
  }

  /* ------------------------------------------------------------- deck --- */

  // is an event on during [lo, hi]?
  function eventOn(c, lo, hi) {
    if (c.d) return c.d.some(function (x) { var d = parse(x); return d >= lo && d <= hi; });
    var start = parse(c.s);
    var end = c.e ? parse(c.e) : addDays(start, OPEN_ENDED);
    return start <= hi && end >= lo;
  }

  function buildDeck(opts) {
    var t = today();
    var lo = t, hi = addDays(t, 365);
    if (opts.when === 'weekend') {
      var dow = t.getDay();  // Sun 0 … Sat 6
      lo = dow === 0 ? addDays(t, -1) : addDays(t, (6 - dow + 7) % 7);
      hi = addDays(lo, 1);
      state.when = nice(lo) + ' – ' + nice(hi);
    } else if (opts.when === 'date' && opts.date) {
      lo = hi = parse(opts.date);
      state.when = nice(lo);
    } else {
      state.when = 'any time';
    }

    var pool = ALL.filter(function (c) {
      if (opts.cats.length && opts.cats.indexOf(c.c) === -1) return false;
      if (c.k === 'e') return eventOn(c, lo, hi);
      return true;
    });

    // weighted shuffle: Kenny's picks, and events on the chosen day, turn up more often
    var rand = rng(opts.seed);
    var dated = opts.when !== 'any';
    pool = pool.map(function (c) {
      var w = 1;
      if (c.r || c.f) w += 2;
      if (dated && c.k === 'e') w += 3;
      return { c: c, key: Math.pow(rand(), 1 / w) };
    }).sort(function (x, y) { return y.key - x.key; }).map(function (x) { return x.c; });

    return pool.slice(0, opts.size);
  }

  /* ----------------------------------------------------------- the url --- */

  function encode() {
    var parts = [state.deck.map(function (c) { return c.id; }).join('')];
    if (state.a) parts.push(state.a.mask, encodeURIComponent(state.a.name || ''));
    if (state.b) parts.push(state.b.mask, encodeURIComponent(state.b.name || ''));
    while (parts.length < 5) parts.push('');
    parts.push(encodeURIComponent(state.when || ''));
    return parts.join('/');
  }

  function link() {
    return location.href.split('#')[0] + '#' + encode();
  }

  // returns null when the text isn't a session
  function decode(text) {
    var hash = String(text || '').trim();
    var i = hash.indexOf('#');
    if (i !== -1) hash = hash.slice(i + 1);
    var p = hash.split('/');
    if (!p[0] || p[0].length % 5) return null;
    var ids = p[0].match(/.{5}/g);
    var deck = ids.map(function (id) { return BY_ID[id]; });
    var missing = deck.filter(function (c) { return !c; }).length;
    return {
      deck: deck.filter(Boolean),
      keep: deck.map(Boolean),  // positions that still exist, to realign the masks
      missing: missing,
      a: p[1] ? { mask: p[1], name: decodeURIComponent(p[2] || '') } : null,
      b: p[3] ? { mask: p[3], name: decodeURIComponent(p[4] || '') } : null,
      when: decodeURIComponent(p[5] || '')
    };
  }

  function realign(person, keep) {
    if (!person) return null;
    var bits = bitsOf(person.mask, keep.length).filter(function (_, i) { return keep[i]; });
    return { name: person.name, bits: bits, mask: maskOf(bits) };
  }

  /* ---------------------------------------------------------- screens --- */

  // while swiping, the header steps aside so the card and buttons fit on one
  // screen with nothing to scroll; the page's back-to-top button never shows
  // here, since on a phone it sat right beside the ♥ button
  document.body.classList.add('is-swipe-page');

  function show(name) {
    $$('.sw-screen').forEach(function (s) { s.hidden = s.getAttribute('data-screen') !== name; });
    document.body.classList.toggle('is-swiping', name === 'deck');
    window.scrollTo({ top: name === 'deck' ? 0 : $('#swipe').offsetTop - 20, behavior: 'instant' });
  }

  $$('[data-goto]').forEach(function (b) {
    b.addEventListener('click', function () { show(b.getAttribute('data-goto')); });
  });

  // single-choice groups
  function pick(group, attr) {
    var btns = $$('[' + attr + ']', group);
    btns.forEach(function (b) {
      b.addEventListener('click', function () {
        btns.forEach(function (x) { x.setAttribute('aria-pressed', String(x === b)); });
        if (attr === 'data-when') $('#sw-date').hidden = b.getAttribute(attr) !== 'date';
      });
    });
  }
  $$('.sw-seg').forEach(function (g) {
    pick(g, $('[data-when]', g) ? 'data-when' : 'data-size');
  });
  $$('[data-cat]').forEach(function (b) {
    b.addEventListener('click', function () {
      b.setAttribute('aria-pressed', String(b.getAttribute('aria-pressed') !== 'true'));
    });
  });
  $('#sw-date').value = iso(addDays(today(), 1));
  try { $('#sw-name').value = localStorage.getItem('lfg-swipe-name') || ''; } catch (e) {}

  $('#sw-start').addEventListener('click', function () {
    var when = $('[data-when][aria-pressed="true"]').getAttribute('data-when');
    var opts = {
      when: when,
      date: $('#sw-date').value,
      cats: $$('[data-cat][aria-pressed="true"]').map(function (b) { return b.getAttribute('data-cat'); }),
      size: +$('[data-size][aria-pressed="true"]').getAttribute('data-size'),
      seed: Math.floor(Math.random() * 2147483647)
    };
    var name = $('#sw-name').value.trim();
    try { localStorage.setItem('lfg-swipe-name', name); } catch (e) {}
    state.deck = buildDeck(opts);
    state.a = state.b = null;
    if (!state.deck.length) {
      alert('Nothing matches those choices — try another day or fewer categories.');
      return;
    }
    startSwiping('a', name);
  });

  /* ---------------------------------------------------------- swiping --- */

  var pos = 0;
  var who = '';

  function startSwiping(slot, name) {
    state.swiper = slot;
    who = name || (slot === 'a' ? 'You' : 'Your partner');
    state.answers = [];
    pos = 0;
    $('#sw-who').textContent = who + '’s turn';
    render();
    show('deck');
  }

  function cardHTML(c) {
    var badge = (c.r ? '<span class="kenny kenny--rec">★ Kenny recommends</span>' : '') +
      (c.f ? '<span class="kenny kenny--featured">◆ Featured</span>' : '');
    var meta = c.k === 'e' ? esc(c.w) : esc(c.g !== c.n ? c.g : c.c);
    return '<article class="sw-card" style="--accent: var(--' + esc(c.l) + ')">' +
      '<span class="sw-stamp sw-stamp--yes">YES</span><span class="sw-stamp sw-stamp--no">NOPE</span>' +
      '<p class="sw-cat"><i></i>' + esc(c.c) + '</p>' +
      '<h2>' + esc(c.n) + '</h2>' +
      '<p class="sw-meta">' + meta + '</p>' +
      (badge ? '<p class="sw-badges">' + badge + '</p>' : '') +
      (c.t ? '<p class="sw-text">' + esc(c.t.replace(/^\(|\)$/g, '')) + '</p>' : '') +
      (c.u ? '<a class="sw-more" href="' + esc(c.u) + '" target="_blank" rel="noopener">More info ↗</a>' : '') +
      '</article>';
  }

  function render() {
    var stack = $('#sw-stack');
    var next = state.deck.slice(pos, pos + 2);
    stack.innerHTML = next.map(cardHTML).reverse().join('');
    $('#sw-count').textContent = Math.min(pos + 1, state.deck.length) + ' / ' + state.deck.length;
    $('#sw-bar').style.width = (pos / state.deck.length * 100) + '%';
    $('#sw-undo').disabled = pos === 0;
    var top = stack.lastElementChild;
    if (top) drag(top);
  }

  function answer(yes) {
    if (pos >= state.deck.length) return;
    var top = $('#sw-stack').lastElementChild;
    state.answers[pos] = yes;
    pos++;
    if (top) {
      top.classList.add(yes ? 'is-yes' : 'is-no', 'is-leaving');
      setTimeout(next, 220);
    } else {
      next();
    }
  }

  function next() {
    if (pos < state.deck.length) return render();
    finished();
  }

  $('#sw-yes').addEventListener('click', function () { answer(true); });
  $('#sw-no').addEventListener('click', function () { answer(false); });
  $('#sw-undo').addEventListener('click', function () {
    if (pos > 0) { pos--; render(); }
  });
  document.addEventListener('keydown', function (e) {
    if ($('[data-screen="deck"]').hidden) return;
    if (e.key === 'ArrowRight') answer(true);
    if (e.key === 'ArrowLeft') answer(false);
    if (e.key === 'Backspace' && pos > 0) { e.preventDefault(); pos--; render(); }
  });

  // drag the top card; past a third of its width it counts as a swipe
  function drag(card) {
    var startX = 0, dx = 0, active = false;
    card.addEventListener('pointerdown', function (e) {
      if (e.target.closest('a')) return;
      active = true; startX = e.clientX; dx = 0;
      card.setPointerCapture(e.pointerId);
      card.classList.add('is-dragging');
    });
    card.addEventListener('pointermove', function (e) {
      if (!active) return;
      dx = e.clientX - startX;
      card.style.transform = 'translateX(' + dx + 'px) rotate(' + (dx / 18) + 'deg)';
      card.classList.toggle('lean-yes', dx > 40);
      card.classList.toggle('lean-no', dx < -40);
    });
    function end() {
      if (!active) return;
      active = false;
      card.classList.remove('is-dragging');
      if (Math.abs(dx) > card.offsetWidth / 3) {
        answer(dx > 0);
      } else {
        card.style.transform = '';
        card.classList.remove('lean-yes', 'lean-no');
      }
    }
    card.addEventListener('pointerup', end);
    card.addEventListener('pointercancel', end);
  }

  /* -------------------------------------------------------- handoffs --- */

  function finished() {
    var me = { name: who === 'You' || who === 'Your partner' ? '' : who, mask: maskOf(state.answers),
               bits: state.answers.slice() };
    if (state.swiper === 'a') {
      state.a = me;
      var yes = state.answers.filter(Boolean).length;
      $('#sw-handoff-lead').innerHTML = 'Done &mdash; you said yes to <b>' + yes + '</b> of ' +
        state.deck.length + '. Now your partner swipes the same cards.';
      show('handoff');
    } else {
      state.b = me;
      results();
    }
  }

  function shareText(url, title) {
    if (navigator.share) {
      navigator.share({ title: title, url: url }).catch(function () {});
      return;
    }
    copy(url);
  }

  function copy(text) {
    var done = function () { toast('Link copied'); };
    if (navigator.clipboard) {
      navigator.clipboard.writeText(text).then(done, function () { prompt('Copy this link:', text); });
    } else {
      prompt('Copy this link:', text);
    }
  }

  function toast(msg) {
    var t = document.createElement('div');
    t.className = 'sw-toast';
    t.textContent = msg;
    document.body.appendChild(t);
    setTimeout(function () { t.remove(); }, 1800);
  }

  $('#sw-share').addEventListener('click', function () {
    shareText(state.pickLink || link(), (state.a.name || 'Someone') + ' wants to plan something');
  });
  $('#sw-copy').addEventListener('click', function () { copy(state.pickLink || link()); });
  $('#sw-pass').addEventListener('click', function () {
    if (state.pickLink) { location.href = state.pickLink; return; }
    show('invite');
    $('#sw-invite-lead').innerHTML = 'Hand the phone over. ' +
      '<b>' + esc(state.a.name || 'They') + '</b>&rsquo;s answers stay hidden until you&rsquo;re done.';
    $('#sw-name-b').value = '';
  });
  $('#sw-invite-go').addEventListener('click', function () {
    startSwiping('b', $('#sw-name-b').value.trim());
  });

  /* ---------------------------------------------------------- results --- */

  function results() {
    var a = state.a, b = state.b;
    var nameA = a.name || 'Person 1', nameB = b.name || 'Person 2';
    var both = [], onlyA = [], onlyB = [];
    state.deck.forEach(function (c, i) {
      if (a.bits[i] && b.bits[i]) both.push(c);
      else if (a.bits[i]) onlyA.push(c);
      else if (b.bits[i]) onlyB.push(c);
    });

    function list(cards) {
      return '<ul class="sw-list">' + cards.map(function (c) {
        var badge = (c.r ? ' <span class="kenny kenny--rec">★</span>' : '') +
          (c.f ? ' <span class="kenny kenny--featured">◆</span>' : '');
        return '<li style="--accent: var(--' + esc(c.l) + ')"><a href="' + esc(c.u || '#') +
          '" target="_blank" rel="noopener">' + esc(c.n) + '</a>' + badge +
          '<span>' + esc(c.k === 'e' ? c.w : c.c) + '</span></li>';
      }).join('') + '</ul>';
    }

    var html = '<p class="eyebrow">' + esc(nameA) + ' &amp; ' + esc(nameB) +
      (state.when ? ' &middot; ' + esc(state.when) : '') + '</p>';
    html += both.length
      ? '<h2 class="sw-h">💚 ' + both.length + (both.length === 1 ? ' match' : ' matches') + '</h2>' + list(both)
      : '<h2 class="sw-h">No matches this time</h2><p class="sw-lead">Have a look at the maybes below &mdash; or start again with a different day.</p>';
    if (onlyA.length || onlyB.length) {
      html += '<h3 class="sw-h3">🤔 Maybes &mdash; one of you said yes</h3>';
      if (onlyA.length) html += '<p class="sw-who">Just ' + esc(nameA) + '</p>' + list(onlyA);
      if (onlyB.length) html += '<p class="sw-who">Just ' + esc(nameB) + '</p>' + list(onlyB);
    }
    $('#sw-results').innerHTML = html;
    show('results');
    history.replaceState(null, '', '#' + encode());
  }

  $('#sw-share-results').addEventListener('click', function () {
    shareText(link(), 'Our matches');
  });
  $('#sw-again').addEventListener('click', function () {
    history.replaceState(null, '', location.pathname);
    state.a = state.b = null;
    show('setup');
  });

  /* ------------------------------------------------------- arriving --- */

  // #p/<ids>/<name>[/<ids>/<name>] — picks ticked on the guide itself
  function loadPicks(hash) {
    var p = hash.split('/');
    if (p[0] !== 'p' || !p[1] || p[1].length % 5) return false;
    var idsA = p[1].match(/.{5}/g);
    var idsB = p[3] ? p[3].match(/.{5}/g) || [] : null;
    var nameA = decodeURIComponent(p[2] || '');
    state.when = '';
    state.pickLink = '';
    if (!idsB) {
      // first person done: hand the guide to the partner, these picks riding along hidden
      state.deck = idsA.map(function (id) { return BY_ID[id]; }).filter(Boolean);
      state.a = { name: nameA, mask: '', bits: [] };
      state.b = null;
      state.pickLink = location.href.split('#')[0].replace(/[^/]*$/, '') +
        'london-guide.html#pick=' + p[1] + '/' + (p[2] || '');
      $('#sw-handoff-lead').innerHTML = 'Done &mdash; you picked <b>' + idsA.length + '</b> thing' +
        (idsA.length === 1 ? '' : 's') + '. Now your partner ticks theirs on the same guide, without seeing yours.';
      $('#sw-handoff-small').textContent = 'Send them the link: it opens the guide in pick mode. ' +
        'When they tap Done, you\u2019ll both see the matches.';
      show('handoff');
      return true;
    }
    // both done: the deck is everything either of you ticked
    var union = [];
    idsA.concat(idsB).forEach(function (id) { if (union.indexOf(id) === -1 && BY_ID[id]) union.push(id); });
    state.deck = union.map(function (id) { return BY_ID[id]; });
    state.a = { name: nameA, bits: union.map(function (id) { return idsA.indexOf(id) !== -1; }) };
    state.b = { name: decodeURIComponent(p[4] || ''), bits: union.map(function (id) { return idsB.indexOf(id) !== -1; }) };
    state.a.mask = maskOf(state.a.bits);
    state.b.mask = maskOf(state.b.bits);
    results();
    return true;
  }

  function load(text) {
    var raw = String(text || '').trim();
    var at = raw.indexOf('#');
    if ((at === -1 ? raw : raw.slice(at + 1)).indexOf('p/') === 0) {
      return loadPicks(at === -1 ? raw : raw.slice(at + 1));
    }
    var s = decode(text);
    if (!s || !s.deck.length || !s.a) return false;
    state.deck = s.deck;
    state.when = s.when;
    state.a = realign(s.a, s.keep);
    state.b = realign(s.b, s.keep);
    if (state.b) {
      results();
    } else {
      $('#sw-invite-lead').innerHTML = '<b>' + esc(state.a.name || 'Someone') +
        '</b> wants to plan something' + (state.when && state.when !== 'any time' ? ' for <b>' + esc(state.when) + '</b>' : '') +
        '. Swipe the same ' + state.deck.length + ' cards &mdash; their answers stay hidden until you&rsquo;re done.' +
        (s.missing ? ' <small>(' + s.missing + ' card' + (s.missing === 1 ? ' has' : 's have') +
          ' since been removed from the guide.)</small>' : '');
      try { $('#sw-name-b').value = localStorage.getItem('lfg-swipe-name') || ''; } catch (e) {}
      show('invite');
    }
    return true;
  }

  $('#sw-join').addEventListener('click', function () {
    var ok = load($('#sw-code').value);
    var err = $('#sw-join-error');
    err.hidden = ok;
    if (!ok) err.textContent = 'That doesn’t look like a swipe link. Paste the whole thing they sent.';
  });

  if (location.hash.length > 1 && !load(location.hash)) {
    history.replaceState(null, '', location.pathname);
  }
})();
