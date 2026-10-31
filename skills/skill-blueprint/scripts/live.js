// 実行ログの重ね表示(リアルタイム)と統計ビュー。render.py が設計図HTMLに埋め込む。
// 読むもの: logs/events.jsonl (hooksが追記・正確) / stats.json (analyze.pyが生成・項目は推定)
(function () {
  var BP = window.BP, M = BP.M;
  var TXT = {
    ja: {blueprint: '設計図', stats: '統計', latest: '最新セッション', all: '全セッション累計', analyze: '再解析',
      loadEv: 'events.jsonl を読込', loadSt: 'stats.json を読込', noLog: 'ログなし', live: 'LIVE', idle: '待機中', ended: '終了',
      session: 'セッション', sessions: 'セッション数', calls: 'スキル呼び出し', used: '使用したスキル', unexp: '想定外の遷移',
      estItems: '通過と推定した項目', skillUse: 'スキルの利用回数', edgesH: '矢印(遷移)の通過回数', itemsH: '通った項目(推定)',
      sessH: 'セッション一覧', back: '設計図に戻る', unused: '未使用', planned: '設計図の矢印', unplanned: '想定外(設計図に無い遷移)',
      share: '出口の割合', visits: '訪問', est: '推定', noData: 'まだログがありません', times: '回',
      estNote: '項目は会話ログの文面と見出しを照合した推定です(スキル・矢印の回数はhooksの記録で正確)。',
      fileNote: 'file:// で開いているため自動更新できません。ログを読み込むか、serve.py で配信してください。'},
    en: {blueprint: 'Blueprint', stats: 'Stats', latest: 'Latest session', all: 'All sessions', analyze: 'Re-analyze',
      loadEv: 'Load events.jsonl', loadSt: 'Load stats.json', noLog: 'No log', live: 'LIVE', idle: 'Idle', ended: 'Ended',
      session: 'Session', sessions: 'Sessions', calls: 'Skill calls', used: 'Skills used', unexp: 'Unexpected transitions',
      estItems: 'Items estimated', skillUse: 'Skill usage', edgesH: 'Arrow (transition) counts', itemsH: 'Items passed (estimated)',
      sessH: 'Sessions', back: 'Back to blueprint', unused: 'unused', planned: 'Blueprint arrows', unplanned: 'Unexpected (not in blueprint)',
      share: 'Share of exits', visits: 'visits', est: 'est.', noData: 'No logs yet', times: '',
      estNote: 'Items are estimated by matching the transcript with headings (skill/arrow counts are exact, from hooks).',
      fileNote: 'Opened via file:// so it cannot auto-refresh. Load the logs, or serve with serve.py.'}
  };
  var L = TXT[M.lang] || TXT.ja;
  var $ = function (s, r) { return (r || document).querySelector(s); };
  var esc = function (s) { return String(s).replace(/[&<>"]/g, function (c) { return {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]; }); };

  // ---- 設計図側の対応表 ----
  var cardIds = Object.keys(M.cards), skillOf = M.skill;
  var skillNames = []; cardIds.forEach(function (c) { if (skillNames.indexOf(skillOf[c]) < 0) skillNames.push(skillOf[c]); });
  var rep = {}; skillNames.forEach(function (s) { rep[s] = cardIds.indexOf(s) >= 0 && skillOf[s] === s ? s : cardIds.filter(function (c) { return skillOf[c] === s; })[0]; });
  var rowLabel = {};  // 'skill:line' -> 見出し
  cardIds.forEach(function (c) { M.rows[c].forEach(function (r) { rowLabel[skillOf[c] + ':' + r[0]] = r[1]; }); });

  // ---- UI ----
  var header = $('header');
  var bar = document.createElement('div'); bar.className = 'lvbar';
  bar.innerHTML = '<button id="vb" class="on">' + L.blueprint + '</button><button id="vs">' + L.stats + '</button>' +
    '<span class="chip" id="chip"><i></i><span id="chipt">' + L.noLog + '</span></span>' +
    '<select id="sel"><option value="latest">' + L.latest + '</option><option value="all">' + L.all + '</option></select>' +
    '<button id="an" style="display:none">' + L.analyze + '</button>' +
    '<label class="btn" id="fe" style="display:none">' + L.loadEv + '<input type="file" accept=".jsonl,.json,.txt"></label>' +
    '<label class="btn" id="fs" style="display:none">' + L.loadSt + '<input type="file" accept=".json"></label>' +
    '<span id="fnote" style="color:var(--sub);display:none">' + L.fileNote + '</span>';
  header.appendChild(bar);
  var sv = document.createElement('div'); sv.id = 'sv'; document.body.appendChild(sv);

  // ---- データ ----
  var events = [], stats = null, mode = 'latest', http = null, visitItems = {};

  function parseEvents(text) {
    var out = []; text.split('\n').forEach(function (l) { if (l.trim()) { try { out.push(JSON.parse(l)); } catch (e) {} } });
    return out;
  }
  function buildSessions() {
    var by = {}, order = [];
    events.forEach(function (e) { if (!by[e.session]) { by[e.session] = []; order.push(e.session); } by[e.session].push(e); });
    return order.map(function (sid) {
      var es = by[sid], visits = [];
      es.forEach(function (e) {
        if (e.type !== 'skill' && e.type !== 'prompt_skill') return;
        var last = visits[visits.length - 1];
        if (last && last.skill === e.skill && (e.ts.slice(0, 19) <= last.ts.slice(0, 19) || (e.type === 'skill' && last.via === 'prompt'))) return;
        visits.push({skill: e.skill, ts: e.ts, via: e.type === 'prompt_skill' ? 'prompt' : 'tool'});
      });
      return {id: sid, start: es[0].ts, last: es[es.length - 1].ts, ended: es.some(function (e) { return e.type === 'session_end'; }), path: visits};
    }).filter(function (s) { return s.path.length; });
  }
  function selected(sessions) {
    if (mode === 'all') return sessions;
    if (mode === 'latest') return sessions.slice(-1);
    return sessions.filter(function (s) { return s.id === mode; });
  }
  function aggregate(sel) {
    var a = {skills: {}, edges: {}, items: {}, last: null, calls: 0, unexp: {}};
    var planned = {}; M.edges.forEach(function (e) { planned[skillOf[e.a] + '>' + skillOf[e.b]] = 1; });
    sel.forEach(function (s) {
      s.path.forEach(function (v, i) {
        a.calls++; a.skills[v.skill] = (a.skills[v.skill] || 0) + 1;
        var it = visitItems[s.id + '|' + v.ts] || {};
        Object.keys(it).forEach(function (ln) { var k = v.skill + ':' + ln; (a.items[k] = a.items[k] || {n: 0, why: it[ln].why, score: it[ln].score}).n++; });
        if (i && s.path[i - 1].skill !== v.skill) {
          var k2 = s.path[i - 1].skill + '>' + v.skill, d = planned[k2] ? a.edges : a.unexp;
          d[k2] = (d[k2] || 0) + 1;
        }
      });
    });
    var ls = sel[sel.length - 1]; if (ls) a.last = ls;
    return a;
  }

  // ---- 設計図への重ね表示 ----
  var svgNS = 'http://www.w3.org/2000/svg';
  function badge(card, n) {
    var el = $('#c-' + card + ' .cnt');
    if (!el) {
      el = document.createElementNS(svgNS, 'g'); el.setAttribute('class', 'cnt');
      el.innerHTML = '<rect x="8" y="-12" width="44" height="22" rx="11"/><text x="30" y="3" text-anchor="middle"></text>';
      $('#c-' + card).appendChild(el);
    }
    el.style.display = n ? '' : 'none'; $('text', el).textContent = '×' + n;
  }
  function overlay(sessions) {
    var sel = selected(sessions), a = aggregate(sel), has = a.calls > 0;
    cardIds.forEach(function (c) {
      var g = $('#c-' + c), n = rep[skillOf[c]] === c ? (a.skills[skillOf[c]] || 0) : 0;
      g.classList.toggle('visited', n > 0); g.classList.toggle('idle', has && !(a.skills[skillOf[c]] > 0));
      g.classList.remove('cur'); badge(c, n);
    });
    var ls = a.last;
    if (ls && !ls.ended && Date.now() - Date.parse(ls.last) < 600000) {
      var cs = ls.path[ls.path.length - 1].skill; if (rep[cs]) $('#c-' + rep[cs]).classList.add('cur');
    }
    var lastEdge = null;
    if (ls && ls.path.length > 1) lastEdge = ls.path[ls.path.length - 2].skill + '>' + ls.path[ls.path.length - 1].skill;
    M.edges.forEach(function (e, i) {
      var k = skillOf[e.a] + '>' + skillOf[e.b], n = a.edges[k] || 0, p = $('#e' + i), l = $('#l' + i);
      p.classList.toggle('dim', has && !n); p.classList.toggle('hit', n > 0);
      p.classList.toggle('recent', mode === 'latest' && k === lastEdge);
      p.style.strokeWidth = n ? Math.min(9, 2.5 + n * 1.2) : '';
      if (l) l.classList.toggle('dim', has && !n);
    });
    var max = 1; Object.keys(a.items).forEach(function (k) { max = Math.max(max, a.items[k].n); });
    document.querySelectorAll('.rowbg').forEach(function (r) {
      var k = skillOf[r.dataset.card] + ':' + r.dataset.line, it = a.items[k];
      r.classList.toggle('est', !!it);
      r.style.fillOpacity = it ? (0.18 + 0.5 * it.n / max) : '';
      var t = $('title', r); if (t) t.remove();
      if (it) { t = document.createElementNS(svgNS, 'title'); t.textContent = L.est + ': ' + it.n + L.times + ' (' + it.why + ')'; r.appendChild(t); r.style.pointerEvents = 'all'; }
      else r.style.pointerEvents = 'none';
    });
    // 状態表示
    var chip = $('#chip'), tx = $('#chipt');
    if (!sessions.length) { chip.className = 'chip'; tx.textContent = L.noLog; return; }
    var cur = sessions[sessions.length - 1], fresh = !cur.ended && Date.now() - Date.parse(cur.last) < 120000;
    chip.className = 'chip' + (fresh ? ' live' : '');
    tx.textContent = (fresh ? L.live + ': ' + cur.path[cur.path.length - 1].skill : (cur.ended ? L.ended : L.idle)) + '  (' + cur.id.slice(0, 8) + ')';
  }

  // ---- 統計ビュー ----
  function pct(x, y) { return y ? Math.round(100 * x / y) + '%' : '-'; }
  function renderStats(sessions) {
    var a = aggregate(sessions), maxS = 1;
    Object.keys(a.skills).forEach(function (k) { maxS = Math.max(maxS, a.skills[k]); });
    var used = skillNames.filter(function (s) { return a.skills[s]; }).length;
    var unexpN = Object.keys(a.unexp).reduce(function (t, k) { return t + a.unexp[k]; }, 0);
    var h = '<button id="svb">← ' + L.back + '</button><h1>' + esc(M.title) + ' — ' + L.stats + '</h1><div class="note">' + esc(L.estNote) + '</div>';
    h += '<div class="tiles">' + [[sessions.length, L.sessions], [a.calls, L.calls], [used + ' / ' + skillNames.length, L.used],
      [unexpN, L.unexp], [Object.keys(a.items).length, L.estItems]].map(function (t) { return '<div class="tile"><b>' + t[0] + '</b><span>' + t[1] + '</span></div>'; }).join('') + '</div>';
    // スキル
    h += '<h2>' + L.skillUse + '</h2><table>' + skillNames.slice().sort(function (x, y) { return (a.skills[y] || 0) - (a.skills[x] || 0); }).map(function (s) {
      var n = a.skills[s] || 0;
      return '<tr><td style="width:260px">' + esc(s) + '</td><td><span class="bar" style="width:' + (n ? 8 + 300 * n / maxS : 0) + 'px"></span></td><td class="num ' + (n ? '' : 'zero') + '">' + (n ? n + L.times : L.unused) + '</td></tr>';
    }).join('') + '</table>';
    // 矢印
    var out = {}; M.edges.forEach(function (e) { var f = skillOf[e.a]; out[f] = (out[f] || 0) + (a.edges[f + '>' + skillOf[e.b]] || 0); });
    Object.keys(a.unexp).forEach(function (k) { var f = k.split('>')[0]; out[f] = (out[f] || 0) + a.unexp[k]; });
    var seen = {}, rows = '';
    M.edges.forEach(function (e) {
      var f = skillOf[e.a], t = skillOf[e.b], k = f + '>' + t; if (seen[k] || f === t) return; seen[k] = 1;
      var n = a.edges[k] || 0;
      rows += '<tr><td>' + esc(f) + ' → ' + esc(t) + '</td><td class="num ' + (n ? '' : 'zero') + '">' + n + '</td><td class="num">' + pct(n, out[f]) + '</td><td><span class="bar" style="width:' + Math.min(300, n * 30) + 'px"></span></td></tr>';
    });
    Object.keys(a.unexp).sort().forEach(function (k) {
      var p = k.split('>'), n = a.unexp[k];
      rows += '<tr><td>' + esc(p[0]) + ' → ' + esc(p[1]) + ' <small style="color:#d64545">(' + L.unplanned + ')</small></td><td class="num">' + n + '</td><td class="num">' + pct(n, out[p[0]]) + '</td><td><span class="bar bad" style="width:' + Math.min(300, n * 30) + 'px"></span></td></tr>';
    });
    h += '<h2>' + L.edgesH + '</h2><table><tr><th></th><th class="num">' + L.times + '</th><th class="num">' + L.share + '</th><th></th></tr>' + rows + '</table>';
    // 項目
    h += '<h2>' + L.itemsH + '</h2>';
    skillNames.forEach(function (s) {
      var rowsS = [], cards = cardIds.filter(function (c) { return skillOf[c] === s; }), seenL = {};
      cards.forEach(function (c) { M.rows[c].forEach(function (r) { if (!seenL[r[0]]) { seenL[r[0]] = 1; rowsS.push(r); } }); });
      var v = a.skills[s] || 0;
      h += '<details' + (v ? ' open' : '') + '><summary>' + esc(s) + ' <span class="zero">(' + v + ' ' + L.visits + ')</span></summary><table>' +
        rowsS.map(function (r) {
          var it = a.items[s + ':' + r[0]], n = it ? it.n : 0;
          return '<tr><td class="num zero" style="width:50px">L' + r[0] + '</td><td>' + esc(r[1]) + '</td><td class="num ' + (n ? '' : 'zero') + '">' + (n || '-') + '</td><td class="num">' + pct(n, v) + '</td><td><span class="bar est" style="width:' + (v ? 200 * n / v : 0) + 'px"></span></td></tr>';
        }).join('') + '</table></details>';
    });
    // セッション
    h += '<h2>' + L.sessH + '</h2><table>' + sessions.slice().reverse().map(function (s) {
      return '<tr><td style="width:150px"><a class="pick" data-sid="' + esc(s.id) + '">' + esc(s.id.slice(0, 8)) + '</a><br><small class="zero">' + esc(new Date(s.start).toLocaleString()) + '</small></td><td class="path">' +
        s.path.map(function (v) { return '<span>' + esc(v.skill) + '</span>'; }).join(' → ') + '</td><td class="num zero">' + (s.ended ? L.ended : '') + '</td></tr>';
    }).join('') + '</table>';
    if (!sessions.length) h += '<p class="zero">' + L.noData + '</p>';
    sv.innerHTML = h;
    $('#svb', sv).onclick = function () { show('bp'); };
    sv.querySelectorAll('a.pick').forEach(function (el) { el.onclick = function () { mode = el.dataset.sid; $('#sel').value = mode; refresh(); show('bp'); }; });
  }

  // ---- 切り替え・更新 ----
  var view = 'bp';
  function show(v) {
    view = v; sv.classList.toggle('on', v === 'st');
    $('#vb').classList.toggle('on', v === 'bp'); $('#vs').classList.toggle('on', v === 'st');
    if (v === 'st') renderStats(buildSessions());
  }
  function refresh() {
    var sessions = buildSessions(), sel = $('#sel'), cur = sel.value;
    var want = ['latest', 'all'].concat(sessions.map(function (s) { return s.id; }));
    if (sel.options.length !== want.length) {
      sel.innerHTML = '<option value="latest">' + L.latest + '</option><option value="all">' + L.all + '</option>' +
        sessions.slice().reverse().map(function (s) { return '<option value="' + esc(s.id) + '">' + L.session + ' ' + esc(s.id.slice(0, 8)) + ' (' + esc(new Date(s.start).toLocaleString()) + ')</option>'; }).join('');
      sel.value = cur && want.indexOf(cur) >= 0 ? cur : 'latest';
    }
    overlay(sessions);
    if (view === 'st') renderStats(sessions);
  }
  function setStats(s) {
    stats = s; visitItems = {};
    (s.sessions || []).forEach(function (se) { se.path.forEach(function (v) { visitItems[se.id + '|' + v.ts] = v.items || {}; }); });
  }
  $('#vb').onclick = function () { show('bp'); }; $('#vs').onclick = function () { show('st'); };
  $('#sel').onchange = function () { mode = this.value; refresh(); };

  var lastLen = -1;
  function poll() {
    fetch('logs/events.jsonl?' + Date.now(), {cache: 'no-store'}).then(function (r) {
      if (r.status === 404) return '';
      if (!r.ok) throw new Error('x'); return r.text();
    }).then(function (t) {
      http = true; $('#an').style.display = '';
      if (t.length !== lastLen) { lastLen = t.length; events = parseEvents(t); refresh(); pollStats(); }
      else refresh();   // 経過時間でLIVE表示を更新
    }).catch(function () {
      if (http === null) { http = false; $('#fe').style.display = ''; $('#fs').style.display = ''; $('#fnote').style.display = ''; }
    });
  }
  function pollStats() {
    fetch('stats.json?' + Date.now(), {cache: 'no-store'}).then(function (r) { return r.ok ? r.json() : null; })
      .then(function (s) { if (s) { setStats(s); refresh(); } }).catch(function () {});
  }
  $('#an').onclick = function () { fetch('/api/analyze').then(function () { pollStats(); }); };
  function fileReader(sel, fn) {
    $(sel + ' input').onchange = function () {
      var f = this.files[0]; if (!f) return; var r = new FileReader();
      r.onload = function () { fn(String(r.result)); refresh(); }; r.readAsText(f);
    };
  }
  fileReader('#fe', function (t) { events = parseEvents(t); });
  fileReader('#fs', function (t) { setStats(JSON.parse(t)); });

  // URL の # で初期表示を指定: #all(全セッション累計) #stats(統計ビュー) #all,stats
  var hs = location.hash.replace('#', '').split(',');
  if (hs.indexOf('all') >= 0) { mode = 'all'; $('#sel').value = 'all'; }
  if (hs.indexOf('stats') >= 0) show('st');
  poll(); setInterval(function () { if (http !== false && !document.hidden) poll(); }, 1000);
  setInterval(function () { if (http) pollStats(); }, 10000);
  window.BP.live = {refresh: refresh, setEvents: function (e) { events = e; refresh(); }, setStats: function (s) { setStats(s); refresh(); }};
})();
