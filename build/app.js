/* London Field Guide — page behaviour.
   Works for both the guide (lines of stops) and the events calendar (months
   of cards); it binds to whichever structure is on the page. */
(function () {
  'use strict';

  var root = document.documentElement;
  var body = document.body;
  var $ = function (sel, ctx) { return (ctx || document).querySelector(sel); };
  var $$ = function (sel, ctx) {
    return Array.prototype.slice.call((ctx || document).querySelectorAll(sel));
  };

  /* ------------------------------------------------------------ theme --- */

  var themeBtn = $('#theme-toggle');
  if (themeBtn) {
    var syncLabel = function () {
      var dark = root.getAttribute('data-theme') === 'dark' ||
        (!root.getAttribute('data-theme') &&
          window.matchMedia('(prefers-color-scheme: dark)').matches);
      themeBtn.setAttribute('aria-label', dark ? 'Switch to light theme' : 'Switch to dark theme');
      themeBtn.setAttribute('title', dark ? 'Switch to light theme' : 'Switch to dark theme');
    };
    themeBtn.addEventListener('click', function () {
      var dark = root.getAttribute('data-theme') === 'dark' ||
        (!root.getAttribute('data-theme') &&
          window.matchMedia('(prefers-color-scheme: dark)').matches);
      var next = dark ? 'light' : 'dark';
      root.setAttribute('data-theme', next);
      try { localStorage.setItem('lfg-theme', next); } catch (e) {}
      syncLabel();
    });
    window.matchMedia('(prefers-color-scheme: dark)')
      .addEventListener('change', syncLabel);
    syncLabel();
  }

  /* ------------------------------------------------- scroll affordances - */

  var toolbar = $('.toolbar');
  var toTop = $('#to-top');
  var ticking = false;

  function onScroll() {
    if (ticking) return;
    ticking = true;
    requestAnimationFrame(function () {
      var y = window.scrollY;
      if (toolbar) toolbar.classList.toggle('is-stuck', y > 8);
      body.classList.toggle('is-scrolled', y > 600);
      ticking = false;
    });
  }

  document.addEventListener('scroll', onScroll, { passive: true });
  onScroll();

  if (toTop) {
    toTop.addEventListener('click', function () {
      window.scrollTo({ top: 0, behavior: 'smooth' });
      var input = $('#search');
      if (input) input.focus({ preventScroll: true });
    });
  }

  /* ------------------------------------------------- pill overflow ------ */

  var pillRow = $('.pills');
  if (pillRow) {
    var syncPillEdges = function () {
      var slack = pillRow.scrollWidth - pillRow.clientWidth;
      pillRow.classList.toggle('is-scrollable', slack > 4);
      pillRow.classList.toggle('at-end', pillRow.scrollLeft >= slack - 4);
    };
    pillRow.addEventListener('scroll', syncPillEdges, { passive: true });
    window.addEventListener('resize', syncPillEdges);
    syncPillEdges();
  }

  /* -------------------------------------------------------- highlight --- */

  function unhighlight(scope) {
    $$('mark[data-hl]', scope).forEach(function (m) {
      m.parentNode.replaceChild(document.createTextNode(m.textContent), m);
    });
    scope.normalize();
  }

  function highlight(scope, needle) {
    if (!needle) return;
    var walker = document.createTreeWalker(scope, NodeFilter.SHOW_TEXT, {
      acceptNode: function (n) {
        return n.nodeValue.trim() ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT;
      }
    });
    var nodes = [];
    var n;
    while ((n = walker.nextNode())) nodes.push(n);

    nodes.forEach(function (node) {
      var text = node.nodeValue;
      var lower = text.toLowerCase();
      var i = lower.indexOf(needle);
      if (i === -1) return;
      var frag = document.createDocumentFragment();
      var last = 0;
      while (i !== -1) {
        frag.appendChild(document.createTextNode(text.slice(last, i)));
        var mark = document.createElement('mark');
        mark.setAttribute('data-hl', '');
        mark.textContent = text.slice(i, i + needle.length);
        frag.appendChild(mark);
        last = i + needle.length;
        i = lower.indexOf(needle, last);
      }
      frag.appendChild(document.createTextNode(text.slice(last)));
      node.parentNode.replaceChild(frag, node);
    });
  }

  /* ----------------------------------------------------------- filter --- */

  var groups = $$('[data-group]');
  if (!groups.length) return;

  // cache the searchable text once, before any <mark> gets injected
  groups.forEach(function (group) {
    $$('[data-item]', group).forEach(function (item) {
      item.setAttribute('data-text', item.textContent.toLowerCase().replace(/\s+/g, ' '));
      $$('[data-leaf]', item).forEach(function (leaf) {
        leaf.setAttribute('data-text', leaf.textContent.toLowerCase().replace(/\s+/g, ' '));
      });
    });
  });

  var input = $('#search');
  var pills = $$('.pill');
  var calendar = null;  // set below on the events page
  var resultCount = $('#result-count');
  var resultNoun = $('#result-noun');
  var emptyQuery = $('#empty-query');
  var totalLeaves = $$('[data-leaf]').length ||
    $$('[data-item]').length;
  var category = 'all';
  var query = '';

  function countable(group) {
    var leaves = $$('[data-leaf]:not([hidden])', group);
    return leaves.length || $$('[data-item]:not([hidden])', group).length;
  }

  function apply() {
    var needle = query.trim().toLowerCase();
    var shown = 0;

    groups.forEach(function (group) {
      unhighlight(group);

      var inCategory = category === 'all' || group.getAttribute('data-group') === category;
      if (!inCategory) {
        group.hidden = true;
        return;
      }

      var items = $$('[data-item]', group);
      var visibleItems = 0;

      items.forEach(function (item) {
        var leaves = $$('[data-leaf]', item);
        var itemHit = !needle || item.getAttribute('data-text').indexOf(needle) !== -1;

        if (!leaves.length) {
          item.hidden = !itemHit;
          if (itemHit) { visibleItems++; shown++; }
          return;
        }

        // a stop label match keeps the whole stop; otherwise keep the venues that match
        var labelEl = $('[data-label]', item);
        var labelHit = !!needle && !!labelEl &&
          labelEl.textContent.toLowerCase().indexOf(needle) !== -1;
        var kept = 0;

        leaves.forEach(function (leaf) {
          var hit = !needle || labelHit ||
            leaf.getAttribute('data-text').indexOf(needle) !== -1;
          leaf.hidden = !hit;
          if (hit) kept++;
        });

        item.hidden = kept === 0;
        if (kept) { visibleItems++; shown += kept; }
      });

      // a group with nothing in it (an empty month) still belongs on the page,
      // but it has nothing to offer a search
      group.hidden = items.length ? visibleItems === 0 : Boolean(needle);

      var counter = $('[data-count]', group);
      if (counter && !group.hidden) counter.textContent = countable(group);

      if (needle && !group.hidden) highlight(group, needle);
    });

    body.classList.toggle('is-empty', shown === 0);
    body.classList.toggle('is-searching', query.length > 0);

    if (resultCount) resultCount.textContent = shown;
    if (resultNoun) {
      resultNoun.textContent = (needle || category !== 'all')
        ? (shown === 1 ? 'match' : 'matches')
        : resultNoun.getAttribute('data-default');
    }
    if (emptyQuery) emptyQuery.textContent = query.trim();
    if (calendar) calendar.render();
  }

  if (input) {
    var debounce;
    input.addEventListener('input', function () {
      clearTimeout(debounce);
      debounce = setTimeout(function () {
        query = input.value;
        apply();
      }, 90);
    });
    input.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') { input.value = ''; query = ''; apply(); }
    });
  }

  var clearBtn = $('#search-clear');
  if (clearBtn) {
    clearBtn.addEventListener('click', function () {
      if (input) { input.value = ''; input.focus(); }
      query = '';
      apply();
    });
  }

  function setCategory(next, scroll) {
    category = next;
    pills.forEach(function (p) {
      p.setAttribute('aria-pressed', String(p.getAttribute('data-filter') === next));
    });
    apply();
    if (scroll) {
      var anchor = $('.lines') || $('.timeline');
      if (anchor && window.scrollY > anchor.offsetTop - 140) {
        window.scrollTo({ top: anchor.offsetTop - 130, behavior: 'smooth' });
      }
    }
  }

  pills.forEach(function (pill) {
    pill.addEventListener('click', function () {
      var value = pill.getAttribute('data-filter');
      // in the month grid a month pill is navigation, not a filter
      if (calendar && calendar.active() && value !== 'all') {
        calendar.goto(value);
        return;
      }
      setCategory(category === value && value !== 'all' ? 'all' : value, true);
    });
  });

  var resetBtn = $('#reset');
  if (resetBtn) {
    resetBtn.addEventListener('click', function () {
      if (input) input.value = '';
      query = '';
      setCategory('all', false);
      if (input) input.focus();
    });
  }

  /* --------------------------------------------------------- calendar --- */

  // Month-grid view of the events page. The cards stay the source of truth:
  // build.py stamps each one with data-start/data-end (and data-days for
  // "Sat 17 & Sat 24"), and the grid is drawn from those.
  var calRoot = $('#cal');
  if (calRoot) calendar = (function () {
    var YEAR = 2026;
    var LONG = 14;  // runs longer than this show on their first and last day only
    var MONTH_IDS = ['m-jan', 'm-feb', 'm-mar', 'm-apr', 'm-may', 'm-jun',
      'm-jul', 'm-aug', 'm-sep', 'm-oct', 'm-nov', 'm-dec'];
    var MONTH_NAMES = ['January', 'February', 'March', 'April', 'May', 'June', 'July',
      'August', 'September', 'October', 'November', 'December'];
    var DAY_NAMES = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];

    var grid = $('#cal-grid');
    var title = $('#cal-title');
    var dayPanel = $('#cal-day');
    var ongoingPanel = $('#cal-ongoing');
    var prev = $('#cal-prev');
    var next = $('#cal-next');
    var timeline = $('.timeline');
    var viewBtns = $$('.view-btn');

    function parse(iso) {
      if (!iso) return null;
      var p = iso.split('-');
      return new Date(+p[0], +p[1] - 1, +p[2]);
    }
    function key(d) { return d.getFullYear() * 10000 + (d.getMonth() + 1) * 100 + d.getDate(); }
    function spanDays(a, b) { return Math.round((b - a) / 86400000) + 1; }
    function esc(s) {
      return s.replace(/[&<>"]/g, function (c) {
        return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c];
      });
    }
    function shortDate(d) { return d.getDate() + ' ' + MONTH_NAMES[d.getMonth()].slice(0, 3); }

    var events = $$('.event-card[data-item]').map(function (card) {
      var link = $('h3 a', card);
      var group = card.closest('[data-group]');
      var days = card.getAttribute('data-days');
      var start = parse(card.getAttribute('data-start'));
      var end = parse(card.getAttribute('data-end'));
      return {
        card: card,
        name: link ? link.textContent.replace('↗', '').trim() : $('h3', card).textContent.trim(),
        url: link ? link.getAttribute('href') : '',
        when: $('.event-date', card).textContent.trim(),
        desc: ($('p', card) || { textContent: '' }).textContent.trim(),
        style: group ? (group.getAttribute('style') || '') : '',
        month: group ? MONTH_IDS.indexOf(group.getAttribute('data-group')) : -1,
        start: start,
        end: end,
        days: days ? days.split(',').map(function (d) { return key(parse(d)); }) : null,
        opens: card.hasAttribute('data-opens'),
        kenny: (card.getAttribute('data-kenny') || '').split(' ').filter(Boolean),
        undated: card.hasAttribute('data-undated'),
        long: start && end && spanDays(start, end) > LONG
      };
    });

    var today = new Date();
    today = new Date(today.getFullYear(), today.getMonth(), today.getDate());
    var month = today.getFullYear() === YEAR ? today.getMonth()
      : (today.getFullYear() > YEAR ? 11 : 0);
    var selected = null;

    function matches(ev) {
      var needle = query.trim().toLowerCase();
      return !needle || ev.card.getAttribute('data-text').indexOf(needle) !== -1;
    }

    // what a single day holds, with a tag for runs seen only at their ends
    function on(day) {
      var k = key(day);
      var out = [];
      events.forEach(function (ev) {
        if (ev.undated || !ev.start || !matches(ev)) return;
        if (ev.days) {
          if (ev.days.indexOf(k) !== -1) out.push({ ev: ev, tag: '' });
        } else if (ev.opens) {
          if (key(ev.start) === k) out.push({ ev: ev, tag: 'Opens' });
        } else if (ev.long) {
          if (key(ev.start) === k) out.push({ ev: ev, tag: 'Starts' });
          else if (key(ev.end) === k) out.push({ ev: ev, tag: 'Last day' });
        } else if (k >= key(ev.start) && k <= key(ev.end)) {
          out.push({ ev: ev, tag: '' });
        }
      });
      // Kenny's picks first, so a busy day never hides them behind "+n more"
      function rank(e) { return e.ev.kenny.indexOf('rec') !== -1 ? 0 : (e.ev.kenny.length ? 1 : 2); }
      return out.sort(function (a, b) { return rank(a) - rank(b); });
    }

    var BADGES = {
      rec: ['\u2605 Kenny recommends', 'Kenny has been and loved it'],
      featured: ['\u25c6 Featured', 'On Kenny\u2019s want-to-do list']
    };

    function badges(ev) {
      return ['rec', 'featured'].filter(function (t) { return ev.kenny.indexOf(t) !== -1; })
        .map(function (t) {
          return '<span class="kenny kenny--' + t + '" title="' + BADGES[t][1] + '">' + BADGES[t][0] + '</span>';
        }).join('');
    }

    function chip(entry) {
      var label = (entry.tag ? entry.tag + ': ' : '') + entry.ev.name;
      var mark = entry.ev.kenny.indexOf('rec') !== -1 ? '\u2605 '
        : (entry.ev.kenny.indexOf('featured') !== -1 ? '\u25c6 ' : '');
      return '<span class="cal-chip" style="' + esc(entry.ev.style) + '" title="' + esc(label) + '">' +
        (entry.tag ? '<b>' + esc(entry.tag) + '</b> ' : '') + mark + esc(entry.ev.name) + '</span>';
    }

    function item(entry, when) {
      var ev = entry.ev;
      var name = ev.url
        ? '<a href="' + esc(ev.url) + '" target="_blank" rel="noopener">' + esc(ev.name) +
          '<span aria-hidden="true">&#8599;</span></a>'
        : esc(ev.name);
      return '<li class="cal-item" style="' + esc(ev.style) + '">' +
        '<span class="cal-item-when">' + esc(when || ev.when) + '</span>' +
        '<div><h4>' + name + badges(ev) + '</h4>' + (ev.desc ? '<p>' + esc(ev.desc) + '</p>' : '') + '</div></li>';
    }

    function renderDay() {
      if (!selected) { dayPanel.innerHTML = ''; return; }
      var list = on(selected);
      var head = DAY_NAMES[selected.getDay()] + ' ' + selected.getDate() + ' ' +
        MONTH_NAMES[selected.getMonth()];
      dayPanel.innerHTML = '<h3>' + head + '</h3>' + (list.length
        ? '<ul>' + list.map(function (e) {
            return item(e, e.tag ? e.tag + ' · ' + e.ev.when : e.ev.when);
          }).join('') + '</ul>'
        : '<p class="cal-none">Nothing dated for this day &mdash; see what&rsquo;s running all month below.</p>');
    }

    function render() {
      if (!active()) return;
      var first = new Date(YEAR, month, 1);
      var last = new Date(YEAR, month + 1, 0);
      title.textContent = MONTH_NAMES[month] + ' ' + YEAR;
      calRoot.setAttribute('style', $('#' + MONTH_IDS[month]).getAttribute('style') || '');
      prev.disabled = month === 0;
      next.disabled = month === 11;
      pills.forEach(function (p) {
        p.setAttribute('aria-pressed', String(p.getAttribute('data-filter') === MONTH_IDS[month]));
      });

      if (!selected || selected.getMonth() !== month) {
        selected = today.getMonth() === month && today.getFullYear() === YEAR ? today : null;
        for (var d = 1; !selected && d <= last.getDate(); d++) {
          if (on(new Date(YEAR, month, d)).length) selected = new Date(YEAR, month, d);
        }
        if (!selected) selected = first;
      }

      var lead = (first.getDay() + 6) % 7;  // weeks start on Monday
      var cells = [];
      for (var i = 0; i < lead; i++) cells.push('<span class="cal-cell is-out" aria-hidden="true"></span>');
      for (var day = 1; day <= last.getDate(); day++) {
        var date = new Date(YEAR, month, day);
        var list = on(date);
        var cls = 'cal-cell';
        if (key(date) === key(today)) cls += ' is-today';
        if (key(date) === key(selected)) cls += ' is-selected';
        if (list.length) cls += ' has-events';
        var shown = list.slice(0, 3).map(chip).join('');
        var more = list.length > 3 ? '<span class="cal-more">+' + (list.length - 3) + ' more</span>' : '';
        cells.push('<button type="button" class="' + cls + '" data-day="' + day + '" aria-label="' +
          DAY_NAMES[date.getDay()] + ' ' + day + ' ' + MONTH_NAMES[month] + ', ' + list.length +
          (list.length === 1 ? ' event' : ' events') + '"' +
          (key(date) === key(selected) ? ' aria-pressed="true"' : ' aria-pressed="false"') + '>' +
          '<span class="cal-num">' + day + '</span>' +
          '<span class="cal-chips">' + shown + more + '</span></button>');
      }
      while (cells.length % 7) cells.push('<span class="cal-cell is-out" aria-hidden="true"></span>');
      grid.innerHTML = cells.join('');
      renderDay();

      // long runs that overlap the month, and this month's undated entries
      var ongoing = events.filter(function (ev) {
        if (!matches(ev)) return false;
        if (ev.undated) return ev.month === month;
        return ev.long && !ev.days && ev.start <= last && ev.end >= first;
      });
      ongoingPanel.innerHTML = ongoing.length
        ? '<h3>Running through ' + MONTH_NAMES[month] + '</h3><ul>' + ongoing.map(function (ev) {
            var when = ev.undated ? ev.when
              : shortDate(ev.start) + ' – ' + shortDate(ev.end);
            return item({ ev: ev, tag: '' }, when);
          }).join('') + '</ul>'
        : '';
    }

    grid.addEventListener('click', function (e) {
      var cell = e.target.closest('.cal-cell[data-day]');
      if (!cell) return;
      selected = new Date(YEAR, month, +cell.getAttribute('data-day'));
      render();
      if (window.matchMedia('(max-width: 640px)').matches) {
        dayPanel.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
      }
    });
    prev.addEventListener('click', function () { if (month > 0) { month--; render(); } });
    next.addEventListener('click', function () { if (month < 11) { month++; render(); } });
    $('#cal-today').addEventListener('click', function () {
      if (today.getFullYear() === YEAR) { month = today.getMonth(); selected = today; }
      render();
    });

    function active() { return body.classList.contains('view-cal'); }

    function setView(view, remember) {
      var cal = view === 'cal';
      body.classList.toggle('view-cal', cal);
      calRoot.hidden = !cal;
      if (timeline) timeline.hidden = cal;
      viewBtns.forEach(function (b) {
        b.setAttribute('aria-pressed', String(b.getAttribute('data-view') === view));
      });
      if (remember) { try { localStorage.setItem('lfg-events-view', view); } catch (e) {} }
      if (cal) {
        category = 'all';  // the grid navigates by month instead of filtering
        render();
      } else {
        setCategory('all', false);
      }
    }

    viewBtns.forEach(function (b) {
      b.addEventListener('click', function () { setView(b.getAttribute('data-view'), true); });
    });

    var saved = null;
    try { saved = localStorage.getItem('lfg-events-view'); } catch (e) {}

    var api = {
      active: active,
      render: render,
      goto: function (monthId) {
        var i = MONTH_IDS.indexOf(monthId);
        if (i !== -1) { month = i; render(); }
      }
    };
    if (saved === 'cal') setTimeout(function () { setView('cal', false); }, 0);
    return api;
  })();

  /* -------------------------------------------------------- pick mode --- */

  // "Pick together": chips and event cards tick instead of opening, across the
  // guide and events pages, then the picks go to swipe.html to share or match.
  // A partner arrives on london-guide.html#pick=<picked ids>/<name>, with those
  // picks carried along but never shown.
  var pickBar = $('#pick-bar');
  if (pickBar) (function () {
    var KEY = 'lfg-picks', ON = 'lfg-picking', PARTNER = 'lfg-pick-partner';
    var toggle = $('#pick-toggle');

    function get(k) { try { return sessionStorage.getItem(k); } catch (e) { return null; } }
    function put(k, v) {
      try { if (v == null) sessionStorage.removeItem(k); else sessionStorage.setItem(k, v); } catch (e) {}
    }
    function escHTML(s) {
      return String(s).replace(/[&<>"]/g, function (c) {
        return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c];
      });
    }

    var picked = (get(KEY) || '').match(/.{5}/g) || [];
    var arrived = location.hash.match(/^#pick(?:=([a-z0-9]*)\/?(.*))?$/);
    if (arrived) {
      if (arrived[1]) {  // a partner's link: start fresh, their picks ride along
        put(PARTNER, arrived[1] + '/' + (arrived[2] || ''));
        picked = [];
      }
      put(ON, '1');
      history.replaceState(null, '', location.pathname);
    }
    var partner = null;
    var stored = get(PARTNER);
    if (stored) {
      var cut = stored.indexOf('/');
      partner = { ids: stored.slice(0, cut), name: decodeURIComponent(stored.slice(cut + 1)) };
    }

    function sync() {
      $$('[data-pick]').forEach(function (el) {
        el.classList.toggle('is-ticked', picked.indexOf(el.getAttribute('data-pick')) !== -1);
      });
      $('#pick-count').textContent = picked.length + ' picked';
      $('#pick-done').disabled = !picked.length;
      put(KEY, picked.length ? picked.join('') : null);
    }

    function start() {
      put(ON, '1');
      body.classList.add('is-picking');
      pickBar.hidden = false;
      if (toggle) toggle.innerHTML = '&#10005; Stop picking';
      $('#pick-note').innerHTML = partner
        ? '<b>' + escHTML(partner.name || 'Your partner') + '</b> has picked &mdash; your turn. ' +
          'Their picks stay hidden until you&rsquo;re done.'
        : 'Tap everything you&rsquo;d be up for. Picks carry over between the Guide and Events pages.';
      sync();
    }

    function stop() {
      put(ON, null); put(KEY, null); put(PARTNER, null);
      picked = []; partner = null;
      body.classList.remove('is-picking');
      pickBar.hidden = true;
      if (toggle) toggle.innerHTML = '&#10003; Pick together';
      sync();
    }

    // capture phase, so a tick never also follows the venue link
    document.addEventListener('click', function (e) {
      if (!body.classList.contains('is-picking')) return;
      var el = e.target.closest('[data-pick]');
      if (!el) return;
      e.preventDefault();
      var id = el.getAttribute('data-pick');
      var i = picked.indexOf(id);
      if (i === -1) picked.push(id); else picked.splice(i, 1);
      sync();
    }, true);

    if (toggle) {
      toggle.addEventListener('click', function () {
        if (body.classList.contains('is-picking')) stop(); else start();
      });
    }
    $('#pick-cancel').addEventListener('click', stop);
    $('#pick-done').addEventListener('click', function () {
      var name = '';
      try { name = localStorage.getItem('lfg-swipe-name') || ''; } catch (e) {}
      if (!name) {
        name = (window.prompt('Your name, so your partner knows who picked:') || '').trim();
        try { localStorage.setItem('lfg-swipe-name', name); } catch (e) {}
      }
      var mine = picked.join('');
      var url = 'swipe.html#p/' + (partner
        ? partner.ids + '/' + encodeURIComponent(partner.name) + '/' + mine + '/' + encodeURIComponent(name)
        : mine + '/' + encodeURIComponent(name));
      stop();
      location.href = url;
    });

    if (get(ON) === '1') start(); else sync();
  })();

  /* --------------------------------------------------------- surprise --- */

  var surprise = $('#surprise');
  if (surprise) {
    surprise.addEventListener('click', function () {
      var pool = $$('a[data-leaf]:not([hidden])').filter(function (el) {
        return !el.closest('[hidden]');
      });
      if (!pool.length) return;
      var pick = pool[Math.floor(Math.random() * pool.length)];
      $$('.is-picked').forEach(function (el) { el.classList.remove('is-picked'); });
      pick.scrollIntoView({ block: 'center', behavior: 'smooth' });
      pick.classList.add('is-picked');
      pick.focus({ preventScroll: true });
      setTimeout(function () { pick.classList.remove('is-picked'); }, 2600);
    });
  }

  /* --------------------------------------------------------- keyboard --- */

  document.addEventListener('keydown', function (e) {
    if (e.metaKey || e.ctrlKey || e.altKey) return;
    var tag = (e.target.tagName || '').toLowerCase();
    var typing = tag === 'input' || tag === 'textarea' || e.target.isContentEditable;
    if (e.key === '/' && !typing && input) {
      e.preventDefault();
      input.focus();
      input.select();
    }
    if (e.key === 'Escape' && !typing && (query || category !== 'all')) {
      if (input) input.value = '';
      query = '';
      setCategory('all', false);
    }
  });

  apply();
})();
