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
