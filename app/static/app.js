/* 관찰 작업창 — 머무르는 설교 코치 v1.0.0
 * Stage 3 원어관찰: 헬라어 구문성경 「구문 묵상 뷰어」와 같은 틀(references/syntax-analysis.md)
 *   절마다 [위] 원어 전체 절 · [왼쪽] 구문별 5중 인터리니어 · [가운데] 주동사 구문 해설 · [오른쪽] 묵상 노트
 * 화면에 넣는 글은 모두 textContent로 넣습니다(innerHTML 없음).
 * 묵상 노트는 입력이 멈추고 1초 뒤 저장합니다. 다른 창이 먼저 고쳤으면 서버가 409로 알려 줍니다.
 */
(function () {
  'use strict';
  var TOKEN = document.querySelector('meta[name="dsc-token"]').getAttribute('content');
  var S = { weeks: [], week: null, prog: null, passage: null, syntax: {}, notes: {}, orphans: [], readonly: true,
            tab: 'syntax', focus: null, dirty: {}, timers: {}, retry: {}, backoff: {}, inflight: null, draftBase: {}, rejected: [],
            conflicts: {}, extraGen: 0, askDraft: '', asking: null, toolMsg: null };

  // ------------------------------------------------------------ 도구
  function el(tag, attrs) {
    var n = document.createElement(tag);
    if (attrs) Object.keys(attrs).forEach(function (k) {
      var v = attrs[k];
      if (v === null || v === undefined || v === false) return;
      if (k === 'text') n.textContent = v;
      else if (k === 'cls') n.className = v;
      else if (k.slice(0, 2) === 'on') n.addEventListener(k.slice(2), v);
      else n.setAttribute(k, v === true ? '' : v);
    });
    for (var i = 2; i < arguments.length; i++) {
      var c = arguments[i];
      if (c === null || c === undefined || c === false) continue;
      n.appendChild(typeof c === 'string' ? document.createTextNode(c) : c);
    }
    return n;
  }
  function $(id) { return document.getElementById(id); }
  function clear(n) { while (n.firstChild) n.removeChild(n.firstChild); return n; }
  function ai() { return el('span', { cls: 'ai-badge', text: '【AI】' }); }
  function hhmm() { var d = new Date(); return d.toTimeString().slice(0, 8); }
  function vid(ref) { return 'v-' + ref.replace(':', '-'); }
  function keys(o) { return Object.keys(o).filter(function (k) { return o[k]; }); }

  function api(method, path, body) {
    var opt = { method: method, headers: { 'X-DSC-Token': TOKEN }, credentials: 'same-origin', cache: 'no-store' };
    if (body !== undefined) { opt.headers['Content-Type'] = 'application/json'; opt.body = JSON.stringify(body); }
    return fetch(path, opt).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (d) { return { ok: r.ok, status: r.status, data: d }; });
    }, function () { return { ok: false, status: 0, data: { error: '작업창 서버에 연결하지 못했습니다. 서버가 켜져 있는지 확인하십시오.' } }; });
  }
  function W(p) { return '/api/weeks/' + encodeURIComponent(S.week) + p; }

  // ------------------------------------------------------------ 주간
  function loadWeeks() {
    return api('GET', '/api/weeks').then(function (r) {
      var sel = clear($('week'));
      if (!r.ok) { showError(r.data.error); return; }
      S.weeks = r.data.weeks;
      if (!S.weeks.length) { showError('vault_root에 주간 폴더(S_YYYYMMDD)가 없습니다. 감독에게 주간 폴더를 만들어 달라고 하십시오.'); return; }
      S.weeks.forEach(function (w) { sel.appendChild(el('option', { value: w.id, text: weekLabel(w) })); });
      var want = decodeURIComponent((location.hash || '').slice(1));
      var pick = S.weeks.some(function (w) { return w.id === want; }) ? want : S.weeks[0].id;
      sel.value = pick;
      return openWeek(pick);
    });
  }
  function weekLabel(w) { return w.id + ' · ' + (w.legacy ? '구판 (읽기 전용)' : (w.text + ' · Stage ' + w.current_stage)); }

  function openWeek(id) {
    return flush().then(function (ok) {
      if (!ok) {                                     // 저장하지 못한 노트가 있으면 주간을 바꾸지 않습니다
        $('week').value = S.week;
        if (location.hash.slice(1) !== S.week) history.replaceState(null, '', '#' + S.week);
        notice('저장하지 못한 노트가 있어 주간을 바꾸지 않았습니다. 먼저 정리하십시오');
        return null;
      }
      S.week = id; S.readonly = true; S.askDraft = ''; S.toolMsg = null; S.focus = null;
      S.passage = null; S.syntax = {}; S.notes = {}; S.orphans = []; S.conflicts = {}; S.dirty = {}; S.draftBase = {};
      Object.keys(S.retry).forEach(function (k) { clearTimeout(S.retry[k]); }); S.retry = {}; S.backoff = {};
      if (location.hash.slice(1) !== id) history.replaceState(null, '', '#' + id);
      return Promise.all([api('GET', W('/progress')), api('GET', W('/passage')), api('GET', W('/notes')), api('GET', W('/syntax'))]);
    }).then(function (rs) {
      if (!rs) return;
      if (!rs[0].ok) { showError(rs[0].data.error); return; }
      S.prog = rs[0].data;
      S.passage = rs[1].ok ? rs[1].data : null;
      S.passageError = rs[1].ok ? null : rs[1].data.error;
      if (rs[2].ok) { S.notes = rs[2].data.verses || {}; S.orphans = rs[2].data.orphans || []; S.readonly = !!rs[2].data.readonly; }
      S.readonly = S.readonly || S.prog.legacy;
      S.syntax = {}; S.rejected = [];
      if (rs[3].ok) {
        (rs[3].data.verses || []).forEach(function (v) { if (v && v.ref) S.syntax[v.ref] = v; });
        S.rejected = rs[3].data.rejected || [];
      }
      var refs = verseRefs();
      S.focus = refs[0] || null;
      renderAll();
    });
  }

  function refreshProgress() {
    if (!S.week) return Promise.resolve();
    var key = function (p) { return p ? p.current_stage + '|' + JSON.stringify(p.render || null) : ''; };
    var before = key(S.prog);
    return api('GET', W('/progress')).then(function (r) {
      if (!r.ok) return;
      S.prog = r.data;
      renderTop();
      if (key(r.data) !== before) renderExtra();      // 열어 둔 주석을 30초마다 닫지 않도록, 바뀌었을 때만
    });
  }

  // ------------------------------------------------------------ 본문 자료
  function original() {
    if (!S.passage || !S.passage.original) return null;
    var k = Object.keys(S.passage.original)[0];
    return k ? S.passage.original[k] : null;
  }
  function isOT() { return S.passage && S.passage.book && S.passage.book.testament === 'OT'; }
  function langCls() { return isOT() ? 'hebrew' : 'greek'; }
  function verseRefs() {
    var o = original() || (S.passage && S.passage.translations && S.passage.translations.NKRV);
    return o ? o.verses.map(function (v) { return v.ref; }) : [];
  }
  function verseText(abbr, ref) {
    var t = abbr === 'orig' ? original() : (S.passage.translations || {})[abbr];
    var hit = t && t.verses.filter(function (v) { return v.ref === ref; })[0];
    return hit ? hit.text : '';
  }
  function clausesOf(ref) { return ((S.passage && S.passage.clauses) || []).filter(function (c) { return c.verse === ref; }); }
  function headingBefore(ref) {
    var nk = S.passage && S.passage.translations && S.passage.translations.NKRV;
    var h = nk && (nk.headings || []).filter(function (x) { return x.before === ref; })[0];
    return h ? h.title : '';
  }
  function strip(s) { return (s || '').normalize('NFC').replace(/[\s.,;:··;—–\-()[\]⸀-⸅"“”‘«»֑-ֽ֯־׀׃]/g, '').replace(/[’᾽'᾿]/g, 'ʼ'); }

  // ------------------------------------------------------------ 그리기
  function renderAll() { renderTop(); renderTabs(); renderMain(); renderExtra(); }

  function renderTop() {
    var rail = clear($('rail')), gate = clear($('gate')), bar = clear($('stagebar'));
    var p = S.prog;
    gate.className = 'gate';
    if (p.legacy) {
      gate.appendChild(el('b', { text: '구판(v0.4) 주간입니다. ' }));
      gate.appendChild(document.createTextNode('작업창에서는 읽기만 합니다. 이름과 파일을 바꾸지 않습니다.'));
      return;
    }
    p.stages.forEach(function (s) {
      rail.appendChild(el('span', { cls: s.state, 'aria-current': s.state === 'now' ? 'step' : null, text: s.key + ' ' + s.name }));
    });
    if (p.commentary_open) {
      gate.className = 'gate open';
      gate.appendChild(el('b', { text: '주석이 열려 있습니다. ' }));
      gate.appendChild(document.createTextNode('Stage ' + p.current_stage + ' ' + p.name + ' — 아래에서 수집된 주석을 볼 수 있습니다.'));
    } else if (p.current_stage === '7A') {
      gate.appendChild(el('b', { text: '🔒 Stage 7A 자기적용 — 주석이 다시 닫혀 있습니다. ' }));
      gate.appendChild(document.createTextNode('Stage 7B 회중적용에서 다시 엽니다.'));
    } else {
      gate.appendChild(el('b', { text: '🔒 주석은 아직 닫혀 있습니다. ' }));
      gate.appendChild(document.createTextNode('Stage 4 1차청중에 들어설 때 모읍니다.'));
    }
    bar.appendChild(el('span', { cls: 'meta', text: p.text + ' · 지금 Stage ' + p.current_stage + ' ' + p.name + '  ' }));
    if (p.next_stage) {
      bar.appendChild(el('button', { cls: 'btn primary', type: 'button', onclick: enterNext,
        text: 'Stage ' + p.next_stage.key + ' ' + p.next_stage.name + ' 시작' }));
    }
  }

  function renderTabs() {
    var t = clear($('tabs'));
    if (!S.passage) return;
    [['syntax', '구문 묵상'], ['compare', '번역 대조'], ['peri', '앞·뒤 페리코페']].forEach(function (x) {
      t.appendChild(el('button', { type: 'button', role: 'tab', 'aria-selected': S.tab === x[0] ? 'true' : 'false',
        text: x[1], onclick: function () { S.tab = x[0]; renderTabs(); showTab(); } }));
    });
  }
  function showTab() {                               // 탭은 숨기기만 합니다(노트 입력칸을 다시 만들지 않음)
    ['syntax', 'compare', 'peri'].forEach(function (k) { var n = $('tab-' + k); if (n) n.hidden = S.tab !== k; });
  }

  function renderMain() {
    var v = clear($('textview'));
    if (!S.passage) {
      v.appendChild(el('div', { cls: 'card' }, el('div', { cls: 'empty', text: S.passageError || '본문 수집본이 없습니다.' }),
        S.prog && S.prog.legacy ? legacyFiles() : null));
      return;
    }
    var refs = verseRefs();
    var syn = el('section', { id: 'tab-syntax' });
    var toc = el('nav', { cls: 'toc', 'aria-label': '절 목차' });
    refs.forEach(function (r) {
      toc.appendChild(el('a', { href: '#', text: r, onclick: function (e) { e.preventDefault(); var n = $(vid(r)); if (n) n.scrollIntoView({ block: 'start' }); } }));
    });
    syn.appendChild(toc);
    var have = refs.filter(function (r) { return S.syntax[r]; }).length;
    syn.appendChild(el('div', { cls: 'legend-bar' },
      el('span', null, el('span', { cls: 'sw sw-src' }), '원어·새한글·ESV = 수집본 글자 그대로'),
      el('span', null, ai(), '분해·직역·동사 계단·해설 = 감독(클로드)'),
      el('span', { text: '구문 분석 ' + have + ' / ' + refs.length + '절' + (have < refs.length ? ' — 나머지 절은 수집본만 보입니다' : '') })));
    if (S.rejected.length) syn.appendChild(el('div', { cls: 'notice warn',
      text: '구문 분석 중 ' + S.rejected.join(', ') + '절은 지금 수집본과 맞지 않아 보이지 않습니다. 감독에게 다시 만들어 달라고 하십시오.' }));
    refs.forEach(function (r) { syn.appendChild(verseBlock(r)); });
    v.appendChild(syn);
    v.appendChild(compareTab());
    v.appendChild(periTab());
    var miss = (S.passage.missing || []).map(function (m) { return m.item + ' — ' + m.reason; }).concat(S.passage.notes || []);
    if (miss.length) {
      var box = el('div', { cls: 'notice' }, el('b', { text: '수집 안내' }));
      var ul = el('ul', { cls: 'files' });
      miss.forEach(function (m) { ul.appendChild(el('li', { text: m })); });
      box.appendChild(ul);
      v.appendChild(box);
    }
    showTab();
  }

  // ---- 절 블록: 위 원어 전체 절 · 아래 3분할
  function verseBlock(ref) {
    var sv = S.syntax[ref];
    var block = el('article', { cls: 'verse-block', id: vid(ref) });
    var title = (sv && sv.title) || headingBefore(ref);
    var top = el('div', { cls: 'verse-top' }, el('span', { cls: 'vnum', text: (S.passage.book ? S.passage.book.ko + ' ' : '') + ref + (title ? ' · ' + title : '') }));
    top.appendChild(greekFull(verseText('orig', ref), sv ? sv.main_verbs || [] : []));
    block.appendChild(top);
    var grid = el('div', { cls: 'verse-grid' });
    grid.appendChild(interlinear(ref, sv));
    grid.appendChild(commentaryPane(ref, sv));
    grid.appendChild(notePane(ref));
    block.appendChild(grid);
    return block;
  }

  function greekFull(text, mainVerbs) {
    var want = mainVerbs.map(strip);              // 서버가 수집본 글자로 바꿔 보낸 주동사
    var d = el('div', { cls: 'greek-full ' + langCls() + ' preacher-text', dir: isOT() ? 'rtl' : null, lang: isOT() ? 'he' : 'grc' });
    (text || '').split(/(\s+)/).forEach(function (tok) {
      if (!tok) return;
      if (/^\s+$/.test(tok)) { d.appendChild(document.createTextNode(tok)); return; }
      d.appendChild(want.indexOf(strip(tok)) >= 0 && strip(tok) ? el('span', { cls: 'mv', text: tok }) : document.createTextNode(tok));
    });
    if (!text) d.appendChild(el('span', { cls: 'missing', text: '[원어 미제공]' }));
    return d;
  }

  function interlinear(ref, sv) {
    var pane = el('div', { cls: 'pane left' }, el('h4', { text: '① 구문별 5중 인터리니어' }));
    if (!sv) {                                       // 구문 분석 전: 수집본만으로 구문(문장부호 분할)과 번역을 보여 줍니다
      clausesOf(ref).forEach(function (c) {
        pane.appendChild(el('div', { cls: 'chunk' }, el('span', { cls: 'clabel fam-etc', text: c.id + ' · 문장부호 분할' }),
          el('div', { cls: 'g-line ' + langCls() + ' preacher-text', dir: isOT() ? 'rtl' : null, text: c.text })));
      });
      pane.appendChild(row('nk', '새한글', verseText('NKT', ref)));
      pane.appendChild(row('esv', 'ESV', verseText('ESV', ref)));
      pane.appendChild(el('div', { cls: 'meta pending', text: '구문 분석(분해·직역·라벨)은 감독이 올리면 여기에 보입니다.' }));
      return pane;
    }
    (sv.clauses || []).forEach(function (c) {
      var ch = el('div', { cls: 'chunk ind-' + Math.max(0, Math.min(3, c.indent | 0)) });
      ch.appendChild(el('span', { cls: 'clabel fam-' + (c.family || 'etc'), text: c.label + ' · ' + c.id }));
      var gw = el('div', { cls: 'gwords', dir: isOT() ? 'rtl' : null });
      (c.words || []).forEach(function (w) {
        gw.appendChild(w.gap
          ? el('span', { cls: 'gw gap claude-text' }, el('span', { cls: 'g', text: w.g }),
               el('span', { cls: 'ab', dir: 'ltr' }, ai(), w.p || '생략된 자리'))
          : el('span', { cls: 'gw' },
               el('span', { cls: 'g ' + langCls() + ' preacher-text', text: w.g, lang: isOT() ? 'he' : 'grc' }),
               el('span', { cls: 'ab claude-text', dir: 'ltr', text: w.p || '' })));
      });
      ch.appendChild(gw);
      ch.appendChild(row('own', '직역', c.literal || '', true));
      ch.appendChild(row('nk', '새한글', c.nk || ''));
      ch.appendChild(row('esv', 'ESV', c.esv || ''));
      pane.appendChild(ch);
    });
    return pane;
  }
  function row(kind, tag, text, isAI) {
    return el('div', { cls: 'row ' + kind + (isAI ? ' claude-text' : ' preacher-text') }, isAI ? ai() : null,
      el('span', { cls: 'tag', text: tag }), text ? text : el('span', { cls: 'missing', text: '—' }));
  }

  function commentaryPane(ref, sv) {
    var pane = el('div', { cls: 'pane center' }, el('h4', null, ai(), '② 주동사 구문 해설'));
    if (!sv) { pane.appendChild(el('p', { cls: 'meta', text: '아직 구문 분석이 없습니다.' })); return pane; }
    if ((sv.chain || []).length) {
      var ch = el('div', { cls: 'vchain claude-text' }, el('b', { text: '동사 계단' }));
      (sv.chain || []).forEach(function (x, i) {
        ch.appendChild(el('div', null, (i ? '↓ ' : ''), el('span', { cls: 'gk ' + langCls(), text: x.verb }), ' ', el('span', { cls: 'dim', text: x.note || '' })));
      });
      pane.appendChild(ch);
    }
    (sv.commentary || []).forEach(function (p) { if (typeof p === 'string') pane.appendChild(el('p', { cls: 'claude-text', text: p })); });
    if (typeof sv.variant === 'string' && sv.variant) pane.appendChild(el('div', { cls: 'variant claude-text', text: sv.variant }));
    return pane;
  }

  function notePane(ref) {
    var n = S.notes[ref] || {};
    var pane = el('div', { cls: 'pane right' }, el('h4', { text: '③ 묵상 노트 · ' + ref + ' · 설교자' }));
    var ta = el('textarea', { cls: 'medi', id: 'note-' + vid(ref), 'data-ref': ref, 'aria-label': ref + ' 묵상 노트',
      readonly: S.readonly ? true : null, placeholder: S.readonly ? '' : '이 절 앞에서 머문 것을 적으십시오.',
      oninput: function () { onInput(ref); }, onfocus: function () { setFocus(ref); } });
    ta.value = n.note || '';
    var dr = S.readonly ? null : getDraft(ref);
    var draft = dr ? dr.v : null;
    if (draft !== null && draft !== (n.note || '')) {   // 새로 고치기 전 저장하지 못한 입력을 되살립니다
      ta.value = draft;
      S.dirty[ref] = true;
      S.draftBase[ref] = dr.base;                    // 그 글을 쓸 때 본 판으로 저장 → 그사이 다른 창이 고쳤으면 409로 알려 줌
      setTimeout(function () { setState(ref, '저장하지 못했던 입력을 되살렸습니다. 저장합니다…'); schedule(ref, 300); }, 0);
    } else if (draft !== null) dropDraft(ref);
    pane.appendChild(ta);
    pane.appendChild(el('div', { id: 'conf-' + vid(ref) }));
    pane.appendChild(el('div', { cls: 'st medi-hint', id: 'st-' + vid(ref),
      text: S.readonly ? '읽기 전용' : (n.updated ? '저장된 노트' : '입력하면 1초 뒤 저장합니다') }));
    return pane;
  }

  function compareTab() {
    var sec = el('section', { id: 'tab-compare', cls: 'card' });
    var tr = S.passage.translations || {};
    var o = original();
    verseRefs().forEach(function (ref) {
      var h = headingBefore(ref);
      if (h) sec.appendChild(el('div', { cls: 'heading', text: h }));
      var box = el('div', { cls: 'cmp' }, el('div', { cls: 'vref', text: ref }));
      if (o) box.appendChild(el('div', { cls: 'cmp-row' }, el('span', { cls: 'tr', text: o.name }),
        el('span', { cls: langCls() + ' preacher-text', dir: isOT() ? 'rtl' : null, text: verseText('orig', ref) })));
      Object.keys(tr).forEach(function (k) {
        box.appendChild(el('div', { cls: 'cmp-row' }, el('span', { cls: 'tr', text: tr[k].name }), el('span', { cls: 'preacher-text', text: verseText(k, ref) })));
      });
      sec.appendChild(box);
    });
    sec.appendChild(el('div', { cls: 'notice', text: Object.keys(tr).map(function (k) { return tr[k].name + ': ' + tr[k].source; }).join(' · ') }));
    return sec;
  }
  function periTab() {
    var sec = el('section', { id: 'tab-peri', cls: 'card' });
    var adj = S.passage.adjacent_pericopes || {};
    [['before', '앞 페리코페 (그늘)'], ['after', '뒤 페리코페 (빛)']].forEach(function (x) {
      var a = adj[x[0]];
      sec.appendChild(el('div', { cls: 'heading', text: x[1] + (a ? ' — ' + a.title + ' · ' + a.range : '') }));
      if (!a) { sec.appendChild(el('div', { cls: 'empty', text: '찾지 못했거나 책의 처음·끝입니다.' })); return; }
      (a.verses || []).forEach(function (vv) {
        sec.appendChild(el('div', { cls: 'verse-line preacher-text' }, el('span', { cls: 'vref', text: vv.ref }), vv.text));
      });
    });
    return sec;
  }
  function legacyFiles() {
    var ul = el('ul', { cls: 'files' });
    (S.prog.files || []).forEach(function (f) { ul.appendChild(el('li', { text: f })); });
    return ul;
  }

  function renderExtra() {
    var x = clear($('extra'));
    var r = S.prog && S.prog.render;
    if (r && r.issues && r.issues.length) {
      var box = el('div', { cls: 'notice warn' }, el('b', { text: '생성본(03_원어관찰_…md)을 다시 만들지 않았습니다' }));
      var ul = el('ul', { cls: 'files' });
      r.issues.forEach(function (i) { ul.appendChild(el('li', { text: i })); });
      box.appendChild(ul);
      x.appendChild(box);
    }
    if (S.orphans.length) {
      var oc = el('div', { cls: 'card' }, el('div', { cls: 'card-h', text: '짝 없는 기록 (지금 본문의 절 목록에 없음 · 읽기 전용)' }));
      S.orphans.forEach(function (o) {
        oc.appendChild(el('div', { cls: 'card-b' }, el('div', { cls: 'vref', text: o.ref || '' }), el('div', { cls: 'preacher-text pre', text: o.note || '' })));
      });
      x.appendChild(oc);
    }
    if (S.prog && !S.prog.legacy && S.passage) x.appendChild(askPanel());
    if (S.prog && !S.prog.legacy) x.appendChild(toolsCard());
    var gen = ++S.extraGen;
    if (S.prog && S.prog.commentary_open) {
      api('GET', W('/commentary')).then(function (rr) {
        if (gen !== S.extraGen) return;              // 더 늦게 시작한 그리기가 있으면 버립니다
        var card = el('div', { cls: 'card comm' });
        card.appendChild(el('div', { cls: 'card-h' }, el('span', { text: '주석 (수집본)' }),
          el('span', { cls: 'meta', text: rr.ok ? rr.data.items.length + '개' : '' })));
        if (!rr.ok) card.appendChild(el('div', { cls: 'empty', text: rr.data.error }));
        else if (!rr.data.items.length) card.appendChild(el('div', { cls: 'empty', text: '아직 모은 주석이 없습니다. 감독에게 주석 수집을 부탁하십시오.' }));
        else rr.data.items.forEach(function (it) {
          card.appendChild(el('details', null, el('summary', { text: it.name }), el('pre', { text: it.text })));
        });
        x.appendChild(card);
      });
    }
  }

  // ------------------------------------------------------------ 묵상 노트 저장
  function draftKey(ref) { return 'dsc-draft|' + S.week + '|' + ref; }
  function putDraft(ref, v) {
    var base = ref in S.draftBase ? S.draftBase[ref] : ((S.notes[ref] && S.notes[ref].updated) || '');
    try { sessionStorage.setItem(draftKey(ref), JSON.stringify({ v: v, base: base })); } catch (e) { /* 저장소 없음 */ }
  }
  function dropDraft(ref) { try { sessionStorage.removeItem(draftKey(ref)); } catch (e) { /* 저장소 없음 */ } }
  function getDraft(ref) {
    try {
      var d = JSON.parse(sessionStorage.getItem(draftKey(ref)) || 'null');
      return d && typeof d.v === 'string' && typeof d.base === 'string' ? d : null;
    } catch (e) { return null; }
  }
  function noteEl(ref) { return $('note-' + vid(ref)); }
  function setState(ref, text, kind) {
    var s = $('st-' + vid(ref));
    if (s) { s.textContent = text; s.className = 'st medi-hint' + (kind ? ' ' + kind : ''); }
  }
  function notice(text) { var b = $('stagebar'); if (b) { b.appendChild(el('span', { cls: 'warn', text: ' ' + text })); } }
  function setFocus(ref) {
    S.focus = ref;
    var a = $('askfocus');
    if (a) a.textContent = ref;
  }

  function onInput(ref) {
    if (S.readonly) return;
    var ta = noteEl(ref);
    if (S.focus !== ref) setFocus(ref);
    S.dirty[ref] = true;
    putDraft(ref, ta ? ta.value : '');             // 새로 고쳐도 이 창의 입력이 남도록
    setState(ref, '입력 중…');
    schedule(ref, 1000);
  }
  function schedule(ref, ms) {
    clearTimeout(S.timers[ref]);
    S.timers[ref] = setTimeout(function () { save(ref); }, ms);
  }

  // 결과: true = 저장할 것이 없거나 저장됨, false = 저장하지 못함(충돌·오류)
  function save(ref) {
    clearTimeout(S.timers[ref]); clearTimeout(S.retry[ref]);
    if (S.conflicts[ref]) return Promise.resolve(false);
    if (!S.dirty[ref] || S.readonly) return Promise.resolve(true);
    if (S.inflight) return S.inflight.then(function () { return save(ref); });
    var ta = noteEl(ref);
    if (!ta) return Promise.resolve(false);
    var sent = ta.value;
    var base = ref in S.draftBase ? S.draftBase[ref] : ((S.notes[ref] && S.notes[ref].updated) || '');
    S.dirty[ref] = false;
    setState(ref, '저장 중…');
    var week = S.week;
    S.inflight = api('PUT', W('/notes/' + encodeURIComponent(ref)), { note: sent, base: base }).then(function (r) {
      S.inflight = null;
      if (week !== S.week) return false;
      if (r.ok) {
        S.notes[ref] = { note: sent, updated: r.data.updated };
        delete S.draftBase[ref]; delete S.backoff[ref];
        var now = noteEl(ref);
        if (now && now.value !== sent) { S.dirty[ref] = true; schedule(ref, 300); }   // 저장하는 사이 더 적은 글
        else { dropDraft(ref); setState(ref, '저장됨 ' + hhmm(), 'ok'); }
        return true;
      }
      S.dirty[ref] = true;
      if (r.status === 409 && r.data.current) {
        delete S.draftBase[ref];
        S.conflicts[ref] = { mine: noteEl(ref) ? noteEl(ref).value : sent, theirs: r.data.current };
        setState(ref, '충돌 — 다른 창에서 먼저 고쳤습니다', 'bad');
        renderConflict(ref);
        return false;
      }
      if (r.status === 401) {
        setState(ref, '작업창 서버가 다시 켜졌습니다. 이 페이지를 새로 고치십시오 — 입력한 글은 새로 고친 뒤 되살립니다', 'bad');
        return false;
      }
      if (r.status >= 400 && r.status < 500 && r.status !== 423 && r.status !== 429) {
        setState(ref, '저장하지 못했습니다: ' + (r.data.error || r.status) + ' — 이 글은 이 창에 남아 있습니다', 'bad');
        return false;                                // 다시 보내도 같은 답(잘못된 요청)이라 되풀이하지 않습니다
      }
      var wait = S.backoff[ref] || 2000;              // 절마다 따로 다시 시도합니다
      setState(ref, '저장하지 못했습니다: ' + (r.data.error || r.status) + ' — ' + Math.round(wait / 1000) + '초 뒤 다시 시도합니다', 'bad');
      clearTimeout(S.retry[ref]);
      S.retry[ref] = setTimeout(function () { save(ref); }, wait);
      S.backoff[ref] = Math.min(wait * 2, 30000);
      return false;
    });
    return S.inflight;
  }

  // 모든 노트를 저장해 봅니다. 하나라도 못 하면 false
  function flush() {
    if (keys(S.conflicts).length) return Promise.resolve(false);
    var refs = keys(S.dirty);
    var p = S.inflight ? S.inflight.then(function () { return true; }) : Promise.resolve(true);
    refs.forEach(function (ref) { p = p.then(function (ok) { return save(ref).then(function (o) { return ok && o; }); }); });
    return p.then(function (ok) { return ok && !keys(S.dirty).length && !keys(S.conflicts).length; });
  }

  function renderConflict(ref) {
    var box = $('conf-' + vid(ref));
    if (!box) return;
    clear(box);
    var c = S.conflicts[ref];
    if (!c) return;
    box.appendChild(el('div', { cls: 'conflict' }, el('b', { text: '다른 창(또는 다른 기기)에서 이 절의 노트를 먼저 고쳤습니다.' }),
      el('div', { cls: 'tr', text: '저쪽 노트' }), el('pre', { text: c.theirs.note || '(비어 있음)' }),
      el('div', { cls: 'nav' },
        el('button', { cls: 'btn', type: 'button', text: '저쪽 글 불러오기', onclick: function () {
          S.notes[ref] = c.theirs; delete S.conflicts[ref]; S.dirty[ref] = false; dropDraft(ref);
          var ta = noteEl(ref); if (ta) ta.value = c.theirs.note || '';
          clear(box); setState(ref, '저쪽 글을 불러왔습니다', 'ok');
        } }),
        el('button', { cls: 'btn primary', type: 'button', text: '내 글로 저장', onclick: function () {
          S.notes[ref] = { note: (S.notes[ref] || {}).note || '', updated: c.theirs.updated || '' };
          delete S.conflicts[ref]; S.dirty[ref] = true; clear(box); save(ref);
        } }))));
  }

  // ------------------------------------------------------------ 감독에게 묻기 · 버튼 일
  function askPanel() {
    var box = el('div', { cls: 'card ask', id: 'askcard' });
    box.appendChild(el('div', { cls: 'card-h' }, el('span', null, '감독에게 묻기 · ', el('span', { id: 'askfocus', text: S.focus || '' })),
      el('span', { cls: 'meta', text: '읽기 전용 · ' + (S.prog.commentary_open ? '주석 열림' : '주석 없음') + ' · 관찰 질문 하나로 답합니다' })));
    var q = el('textarea', { id: 'askq', rows: '2', maxlength: '1000', 'aria-label': '질문',
      placeholder: '예: 이 동사는 신약에서 또 어디에 쓰였습니까?',
      oninput: function (e) { S.askDraft = e.target.value; } });
    q.value = S.askDraft || '';
    var busy = !!S.asking;
    q.readOnly = busy;
    box.appendChild(el('div', { cls: 'ask-row' }, q, el('button', { cls: 'btn primary', type: 'button', id: 'askbtn',
      text: busy ? '묻는 중…' : '묻기', disabled: busy ? true : null, onclick: doAsk })));
    var note = S.prog.current_stage === '7A' ? '자기적용 단계의 질문과 답은 기록에 남기지 않습니다.' : '질문과 답은 ask_log.jsonl에 남습니다.';
    box.appendChild(el('div', { cls: 'ask-st meta', id: 'askst',
      text: busy ? '감독에게 묻는 중입니다… (최대 60초)' : '마지막으로 고른 절을 함께 보냅니다. ' + note }));
    box.appendChild(el('div', { id: 'asklist' }));
    loadAsks();
    return box;
  }
  function answerBlock(it) {
    var b = el('div', { cls: 'qa' });
    b.appendChild(el('div', { cls: 'q preacher-text', text: '묻기 · ' + (it.verse || it.clause || '') + ' — ' + it.question }));
    if (it.answer) b.appendChild(el('div', { cls: 'a claude-text' }, ai(), it.answer));
    else b.appendChild(el('div', { cls: 'a warn', text: '답하지 못했습니다: ' + (it.error || '') }));
    return b;
  }
  function loadAsks() {
    var week = S.week;
    api('GET', W('/ask')).then(function (r) {
      var l = $('asklist');
      if (!l || week !== S.week || !r.ok) return;
      clear(l);
      r.data.items.slice().reverse().forEach(function (it) { l.appendChild(answerBlock(it)); });
    });
  }
  function doAsk() {
    var q = $('askq'), st = $('askst');
    var text = (q.value || '').trim();
    if (!text || S.asking) { if (!text) st.textContent = '질문을 적어 주십시오.'; return; }
    S.asking = { week: S.week, stage: S.prog.current_stage };
    renderAskBusy();
    api('POST', W('/ask'), { question: text, verse: S.focus }).then(function (r) {
      var from = S.asking;
      S.asking = null;
      var here = from && from.week === S.week && S.prog && from.stage === S.prog.current_stage;
      if (r.ok && here) S.askDraft = '';
      if (!here) return;                             // 다른 주간·단계로 옮겼으면 그 화면에 끼워 넣지 않습니다
      renderAskBusy();
      var st2 = $('askst');
      if (!st2) return;
      if (!r.ok) { st2.textContent = r.data.error || ('오류 ' + r.status); st2.className = 'ask-st meta warn'; return; }
      st2.className = 'ask-st meta';
      st2.textContent = r.data.seconds + '초' + (r.data.stage === '7A' ? ' · 기록에 남기지 않았습니다.' : ' · ask_log.jsonl에 남겼습니다.');
      var qq = $('askq'); if (qq) qq.value = '';
      var l = $('asklist');
      if (l) l.insertBefore(answerBlock(r.data), l.firstChild);
    });
  }
  function renderAskBusy() {
    var btn = $('askbtn'), q = $('askq'), st = $('askst');
    if (btn) { btn.disabled = !!S.asking; btn.textContent = S.asking ? '묻는 중…' : '묻기'; }
    if (q) q.readOnly = !!S.asking;
    if (st && S.asking) { st.className = 'ask-st meta'; st.textContent = '감독에게 묻는 중입니다… (보통 10~20초, 최대 60초)'; }
  }

  function toolsCard() {
    var out = el('div', { id: 'toolout' });
    if (S.toolMsg && S.toolMsg.week === S.week) out.appendChild(S.toolMsg.node);   // 다시 그려도 마지막 결과를 남깁니다
    return el('div', { cls: 'card' }, el('div', { cls: 'card-h' }, el('span', { text: '도구' })),
      el('div', { cls: 'card-b tools' },
        el('button', { cls: 'btn', type: 'button', text: '본문 다시 수집', onclick: recollect }),
        el('button', { cls: 'btn', type: 'button', text: '진행 상황 점검', onclick: checkWeek })), out);
  }
  function keepKids(o) {                             // id 없이 결과 내용만 복사합니다
    var d = el('div');
    Array.prototype.forEach.call(o.childNodes, function (c) { d.appendChild(c.cloneNode(true)); });
    return d;
  }
  function toolBusy(on, msg) {
    document.querySelectorAll('.tools button').forEach(function (b) { b.disabled = on; });
    var o = $('toolout');
    if (o && msg !== undefined) { clear(o); o.appendChild(el('div', { cls: 'card-b meta', text: msg })); }
  }
  function listInto(o, lines) {
    if (!lines.length) return;
    var ul = el('ul', { cls: 'files' });
    lines.forEach(function (n) { ul.appendChild(el('li', { text: n })); });
    o.appendChild(ul);
  }
  function recollect() {
    var week = null;
    if (!window.confirm('본문을 공식 출처에서 다시 받을까요?\n\n1~3분 걸릴 수 있습니다. 묵상 노트와 구문 분석은 그대로 둡니다.')) return;
    flush().then(function (ok) {
      if (!ok) { toolBusy(false, '저장하지 못한 노트가 있어 다시 수집하지 않았습니다.'); return null; }
      toolBusy(true, '본문을 다시 받는 중입니다…');
      week = S.week;
      return api('POST', W('/recollect'), { confirm: true });
    }).then(function (r) {
      if (!r) return;
      if (week !== S.week) { toolBusy(false); return; }   // 그사이 주간을 바꿨으면 결과를 다른 주간에 보이지 않습니다
      toolBusy(false);
      var o = clear($('toolout'));
      if (!r.ok) { o.appendChild(el('div', { cls: 'card-b warn', text: r.data.error || r.data.reason || ('오류 ' + r.status) })); return; }
      var d = r.data;
      o.appendChild(el('div', { cls: 'card-b', text: '결과: ' + d.status + (d.reason ? ' — ' + d.reason : '') +
        (d.counts ? ' · 역본 ' + d.counts.translations + ' · 원어 ' + d.counts.original : '') }));
      listInto(o, (d.missing || []).map(function (m) { return '빠짐: ' + m; }).concat(d.notes || []));
      S.toolMsg = { week: S.week, node: keepKids(o) };
      if (d.status !== 'refused') openWeek(S.week);
    });
  }
  function checkWeek() {
    toolBusy(true, '점검하는 중입니다…');
    var week = S.week;
    api('POST', W('/check')).then(function (r) {
      toolBusy(false);
      if (week !== S.week) return;
      var o = clear($('toolout'));
      if (!r.ok) { o.appendChild(el('div', { cls: 'card-b warn', text: r.data.error || ('오류 ' + r.status) })); return; }
      var lines = r.data.issues.map(function (i) { return i.file + ' — ' + i.problem + (i.suggestion ? ' (' + i.suggestion + ')' : ''); })
        .concat(r.data.privacy.messages);
      o.appendChild(el('div', { cls: 'card-b', text: lines.length ? '살펴볼 것 ' + lines.length + '건 (비공개 오류 ' + r.data.privacy.errors + '건)' :
        '파일 이름·YAML·비공개 점검 모두 통과했습니다.' }));
      listInto(o, lines);
      S.toolMsg = { week: S.week, node: keepKids(o) };
    });
  }

  // ------------------------------------------------------------ 단계
  function enterNext() {
    var nx = S.prog.next_stage;
    if (!nx) return;
    var msg = 'Stage ' + nx.key + ' ' + nx.name + '을(를) 시작할까요?\n\n설교자가 직접 확인할 때만 누르십시오. 단계는 되돌릴 수 없습니다.';
    if (nx.key === '4') msg += '\n\nStage 4부터 주석이 열립니다.';
    if (S.prog.current_stage === '3') msg += '\n\n원어관찰 생성본(md)을 지금 만듭니다.';
    if (!window.confirm(msg)) return;
    var locked = [];
    flush().then(function (ok) {
      if (!ok) { window.alert('저장하지 못한 노트가 있습니다. 먼저 정리한 뒤 단계를 올리십시오.'); return null; }
      document.querySelectorAll('textarea.medi').forEach(function (t) { if (!t.readOnly) { t.readOnly = true; locked.push(t); } });
      return api('POST', W('/stage/enter'), { to: nx.key, confirm: true });   // 그동안 노트를 잠가 생성본과 어긋나지 않게
    }).then(function (r) {
      locked.forEach(function (t) { t.readOnly = false; });
      if (!r) return;
      if (!r.ok) { window.alert(r.data.error || '단계를 올리지 못했습니다'); return; }
      return refreshProgress().then(loadWeeksQuiet);
    });
  }
  function loadWeeksQuiet() {
    return api('GET', '/api/weeks').then(function (r) {
      if (!r.ok) return;
      var sel = $('week');
      r.data.weeks.forEach(function (w) {
        var o = sel.querySelector('option[value="' + w.id + '"]');
        if (o) o.textContent = weekLabel(w);
      });
    });
  }

  function showError(msg) {
    var v = clear($('textview'));
    v.appendChild(el('div', { cls: 'card' }, el('div', { cls: 'empty warn', text: msg || '알 수 없는 오류' })));
  }

  // ------------------------------------------------------------ 시작
  $('week').addEventListener('change', function (e) { openWeek(e.target.value); });
  window.addEventListener('beforeunload', function (e) {
    if (keys(S.dirty).length || S.inflight || keys(S.conflicts).length) { e.preventDefault(); e.returnValue = ''; }
  });
  window.addEventListener('hashchange', function () {
    var id = decodeURIComponent(location.hash.slice(1));
    if (id !== S.week && S.weeks.some(function (w) { return w.id === id; })) { $('week').value = id; openWeek(id); }
  });
  window.addEventListener('focus', refreshProgress);
  setInterval(refreshProgress, 30000);
  loadWeeks();
})();
