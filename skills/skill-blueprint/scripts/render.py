#!/usr/bin/env python3
"""設計図スペック(JSON)を、1枚のHTML(SVG)に描画する。

usage: python render.py blueprints/<名前>          (spec.json を読み index.html を同じ場所に出力)
       python render.py spec.json out.html

spec:
{
  "title": "superpowers の設計図",
  "source": "skills/superpowers-main",          # 任意
  "entry": "using-superpowers",                 # 最初に読むスキルのid
  "skills": [
    {"id": "using-superpowers", "summary": "一行説明",
     "items": [{"id": "rule", "label": "The Rule: 先にskillを起動", "ref": "L18"}]}
  ],
  "edges": [
    {"from": "using-superpowers", "from_item": "rule",   # from_item は省略可
     "to": "brainstorming", "to_item": null,             # to_item も省略可
     "label": "新機能を作るとき", "kind": "conditional"} # kind: always | conditional | optional
  ]
}
"""
import html, json, os, pathlib, re, sys, unicodedata

CARD_W, PAD, GAP_X, GAP_Y = 310, 12, 190, 28
MARGIN_X, MARGIN_TOP, MARGIN_RIGHT = 40, 110, 170
LINE_H, F_ITEM, F_SUM = 16, 12, 11


UI = {
    "ja": {"always": "必ず次に読む", "cond": "条件つきで読む", "back": "戻り・任意",
           "items": "項目 = SKILL.md の見出し(深さはインデント)", "hot": "● 青 = 矢印の出入り口",
           "fit": "全体", "reset": "配置リセット", "copy": "パスをコピー", "vscode": "VS Codeで開く",
           "close": "閉じる", "copied": "コピーしました"},
    "en": {"always": "Always read next", "cond": "Read if condition holds", "back": "Return / optional",
           "items": "Items = SKILL.md headings (depth = indent)", "hot": "● blue = arrow endpoint",
           "fit": "Fit", "reset": "Reset layout", "copy": "Copy path", "vscode": "Open in VS Code",
           "close": "Close", "copied": "Copied"},
}


def cw(ch, size):
    return size * (1.06 if unicodedata.east_asian_width(ch) in "WF" else 0.62)


def wrap(text, width, size, max_lines=None):
    lines, cur, w = [], "", 0.0
    for ch in text:
        if ch == "\n":
            lines.append(cur)
            cur, w = "", 0.0
            continue
        c = cw(ch, size)
        if w + c > width and cur:
            lines.append(cur)
            cur, w = "", 0.0
        cur += ch
        w += c
    if cur:
        lines.append(cur)
    if max_lines and len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1][:-1] + "…"
    return lines or [""]


def esc(s):
    return html.escape(str(s), quote=True)


def resolve_line(lines, it):
    """項目の行番号: line 指定 > ref の 'L18' > ref の '§見出し' を見出しから検索。"""
    if isinstance(it.get("line"), int):
        return it["line"]
    ref = it.get("ref", "")
    m = re.search(r"\bL(\d+)", ref)
    if m:
        return int(m.group(1))
    if "§" in ref:
        key = ref.split("§", 1)[1].split("/")[0].strip().lower()
        fence = False
        for i, ln in enumerate(lines, 1):
            if ln.lstrip().startswith("```"):
                fence = not fence
            if not fence and re.match(r"#{1,4}\s", ln) and key and key in ln.lower():
                return i
    return None


def norm_skill(name):
    return str(name).strip().lstrip("/").split(":")[-1]


def file_uri(path):
    return pathlib.Path(path).as_uri()


def vscode_uri(path, line):
    return "vscode://file/" + path.replace("\\", "/") + (f":{line}" if line else "")


def main(spec_path, out_path):
    spec = json.load(open(spec_path, encoding="utf-8"))
    skills = {s["id"]: s for s in spec["skills"]}
    entry = spec.get("entry") or spec["skills"][0]["id"]
    edges = [e for e in spec.get("edges", []) if e["from"] in skills and e["to"] in skills]

    # --- 層の決定 (entry からのBFS) ---
    layer = {entry: 0}
    q = [entry]
    while q:
        n = q.pop(0)
        for e in edges:
            if e["from"] == n and e["to"] not in layer:
                layer[e["to"]] = layer[n] + 1
                q.append(e["to"])
    # 最長経路で層を押し下げる(任意・循環は無視し、上限 n-1 で打ち切り)
    bfs = dict(layer)  # 最短距離の順序で「前向きの辺」だけを残す(循環は後ろ向き扱い→DAGになる)
    fwd = [e for e in edges if e.get("kind") != "optional" and e["from"] in bfs and e["to"] in bfs
           and bfs[e["from"]] < bfs[e["to"]]]
    for _ in range(len(skills)):
        changed = False
        for e in fwd:
            if layer[e["from"]] + 1 > layer[e["to"]]:
                layer[e["to"]] = layer[e["from"]] + 1
                changed = True
        if not changed:
            break
    extra = max(layer.values()) + 1
    for sid in skills:
        layer.setdefault(sid, extra)
    nlayers = max(layer.values()) + 1

    # --- 原典リンクの解決 (SKILL.md のパスと行番号) ---
    base = spec.get("base")
    found = {}
    if base and os.path.isdir(base):
        for root, _, files in os.walk(base):
            if "SKILL.md" in files:
                found[os.path.basename(root)] = os.path.join(root, "SKILL.md")
    for sid, s in skills.items():
        p = s.get("path") or found.get(sid) or found.get(s.get("name", ""))
        s["_path"] = os.path.abspath(p) if p and os.path.isfile(p) else None
        s["_lines"] = open(s["_path"], encoding="utf-8", errors="replace").read().splitlines() if s["_path"] else []
        # items 省略 or "headings": SKILL.md の見出しをそのまま項目にする(# の数も表示)
        if not s.get("items") or s["items"] == "headings":
            maxlv = int(s.get("heading_levels", spec.get("heading_levels", 2)))
            items, fence = [], False
            lo, hi = s.get("range", [1, 10**9])  # 1つのSKILL.mdを節ごとに複数カードへ分けるとき
            for i, ln in enumerate(s["_lines"], 1):
                if ln.lstrip().startswith("```"):
                    fence = not fence
                m = None if fence or not (lo <= i <= hi) else re.match(r"^(#{1,6})\s+(.+?)\s*$", ln)
                if m and len(m.group(1)) <= maxlv and not (len(m.group(1)) == 1 and maxlv > 1):
                    orig = m.group(2)
                    tr = spec.get("translations", {}).get(sid, {})  # {"行番号": "訳した見出し"}
                    items.append({"id": f"L{i}", "label": tr.get(str(i), orig), "orig": orig, "line": i,
                                  "_auto": True, "_indent": (len(m.group(1)) - 2) * 10 if len(m.group(1)) > 2 else 0})
            s["items"] = items
        for it in s["items"]:
            it["_line"] = resolve_line(s["_lines"], it)

    # --- カード寸法 ---
    inner_w = CARD_W - 2 * PAD
    for s in skills.values():
        s["_sum"] = wrap(s.get("summary", ""), inner_w, F_SUM, 2)
        s["_head_h"] = 12 + 18 + len(s["_sum"]) * 14 + 8
        y, rows = s["_head_h"], []
        for it in s["items"]:
            auto = it.get("_auto")
            ind = it.get("_indent", 0)
            ls = wrap(it["label"], inner_w - 16 - ind - (34 if auto else 0), F_ITEM, 3)
            ref = it.get("ref", "")
            if it["_line"] and not re.search(r"\bL\d+", ref):
                ref = (ref + " · " if ref else "") + f"L{it['_line']}"
            h = len(ls) * LINE_H + (0 if auto else (13 if ref else 0)) + (8 if auto else 10)
            rows.append({"id": it.get("id"), "lines": ls, "ref": ref, "y": y, "h": h, "line": it["_line"],
                         "auto": bool(auto), "ind": ind, "orig": it.get("orig", "")})
            y += h
        s["_rows"], s["_h"] = rows, y + 8

    # --- 配置 ---
    pos = {}
    cols = {i: [sid for sid in skills if layer[sid] == i] for i in range(nlayers)}

    def find_row(sid, item_id):
        """item_id: 項目id、または 'L123'(その行以前で最も近い項目)。"""
        if not item_id:
            return None
        rows = skills[sid]["_rows"]
        for r in rows:
            if r["id"] == item_id:
                return r
        m = re.fullmatch(r"L(\d+)", str(item_id))
        if m:
            cand = [r for r in rows if r["line"] and r["line"] <= int(m.group(1))]
            if cand:
                return max(cand, key=lambda r: r["line"])
        return None

    hot = set()
    for e in edges:
        for sid, key in ((e["from"], e.get("from_item")), (e["to"], e.get("to_item"))):
            r = find_row(sid, key)
            if r:
                hot.add((sid, r["id"]))

    def anchor_y(sid, item_id):
        p, s = pos[sid], skills[sid]
        r = find_row(sid, item_id)
        if r:
            return p[1] + r["y"] + r["h"] / 2
        return p[1] + s["_head_h"] / 2

    for i in range(nlayers):
        x = MARGIN_X + i * (CARD_W + GAP_X)

        def bary(sid):
            ys = [anchor_y(e["from"], e.get("from_item")) for e in edges
                  if e["to"] == sid and e["from"] in pos and layer[e["from"]] < i]
            return sum(ys) / len(ys) if ys else 1e9

        order = sorted(cols[i], key=lambda sid: (bary(sid), list(skills).index(sid)))
        cy = MARGIN_TOP
        for sid in order:
            b = bary(sid)
            want = b - skills[sid]["_head_h"] / 2 if b < 1e8 else cy
            top = max(cy, want)
            pos[sid] = (x, top)
            cy = top + skills[sid]["_h"] + GAP_Y

    width = MARGIN_X * 2 + nlayers * CARD_W + (nlayers - 1) * GAP_X + MARGIN_RIGHT
    height = max(p[1] + skills[sid]["_h"] for sid, p in pos.items()) + 90

    # --- 描画 ---
    out = []
    labels = []
    emodel = []
    ext_x = 0
    for ei, e in enumerate(edges):  # 矢印は背面
        a, b = e["from"], e["to"]
        ax, bx = pos[a][0], pos[b][0]
        y1 = anchor_y(a, e.get("from_item"))
        y2 = anchor_y(b, e.get("to_item"))
        back = layer[b] <= layer[a]
        kind = e.get("kind", "conditional" if e.get("label") else "always")
        cls = "edge " + kind + (" back" if back else "")
        if not back:
            x1, x2 = ax + CARD_W, bx
            d = max(50, (x2 - x1) / 2)
            path = f"M{x1},{y1} C{x1+d},{y1} {x2-d},{y2} {x2},{y2}"
            pts = [(x1, y1), (x1 + d, y1), (x2 - d, y2), (x2, y2)]
            t = 0.5 if layer[b] - layer[a] == 1 else 0.5 * GAP_X / max(1, x2 - x1)
        else:
            x1, x2 = ax + CARD_W, bx + CARD_W
            far = max(x1, x2) + 70 + 8 * (layer[a] - layer[b])
            path = f"M{x1},{y1} C{far},{y1} {far},{y2} {x2},{y2}"
            pts = [(x1, y1), (far, y1), (far, y2), (x2, y2)]
            t = 0.5
        for k in range(11):  # 曲線がはみ出す範囲を実測して、図の幅・高さに反映する
            mt, tt = 1 - k / 10, k / 10
            ext_x = max(ext_x, mt**3*pts[0][0] + 3*mt*mt*tt*pts[1][0] + 3*mt*tt*tt*pts[2][0] + tt**3*pts[3][0])
        out.append(f'<path id="e{ei}" class="{cls}" d="{path}" marker-end="url(#arr)"/>')
        em = {"a": a, "b": b, "ay": y1 - pos[a][1], "by": y2 - pos[b][1], "back": back,
              "far": 70 + 8 * (layer[a] - layer[b]) if back else 0, "t": t, "dy": 0, "lab": False}
        emodel.append(em)
        if e.get("label"):
            mt = 1 - t
            px = mt**3*pts[0][0] + 3*mt*mt*t*pts[1][0] + 3*mt*t*t*pts[2][0] + t**3*pts[3][0]
            py = mt**3*pts[0][1] + 3*mt*mt*t*pts[1][1] + 3*mt*t*t*pts[2][1] + t**3*pts[3][1]
            labels.append([px, py, wrap(e["label"], GAP_X - 40, 11, 3), kind, ei, py])
            em["lab"] = True

    # ラベル衝突回避
    labels.sort(key=lambda l: l[1])
    placed = []
    for l in labels:
        h = len(l[2]) * 14 + 8
        while any(abs(l[0] - p[0]) < GAP_X and l[1] - h / 2 < p[1] + p[2] / 2 and l[1] + h / 2 > p[1] - p[2] / 2
                  for p in placed):
            l[1] += 6
        placed.append((l[0], l[1], h))
        l.append(h)
    for px, py, ls, kind, ei, py0, h in labels:
        emodel[ei]["dy"] = py - py0
        w = max(sum(cw(c, 11) for c in ln) for ln in ls) + 12
        ext_x = max(ext_x, px + w / 2)
        out.append(f'<g id="l{ei}" class="elabel {kind}" transform="translate({px:.1f},{py:.1f})"><rect x="{-w/2:.1f}" y="{-h/2:.1f}" width="{w:.1f}" height="{h}" rx="5"/>')
        for k, ln in enumerate(ls):
            out.append(f'<text x="0" y="{-h/2+14+k*14-1:.1f}" text-anchor="middle">{esc(ln)}</text>')
        out.append("</g>")

    width = max(width, ext_x + 40)
    for sid, s in skills.items():
        x, y = pos[sid]
        is_entry = sid == entry
        out.append(f'<g id="c-{esc(sid)}" class="card{" entry" if is_entry else ""}" transform="translate({x},{y})">')
        out.append(f'<rect class="box" width="{CARD_W}" height="{s["_h"]}" rx="10"/>')
        out.append(f'<rect class="head" width="{CARD_W}" height="{s["_head_h"]}" rx="10"/>'
                   f'<rect class="headfill" y="{s["_head_h"]-10}" width="{CARD_W}" height="10"/>')
        nm = f'<text class="name" x="{PAD}" y="{12+14}">{esc(s.get("name", sid))}</text>'
        if s["_path"]:
            nm = f'<g class="lnk" data-sid="{esc(sid)}" data-line="1"><title>{esc(s["_path"])}</title>{nm}</g>'
        out.append(nm)
        for k, ln in enumerate(s["_sum"]):
            out.append(f'<text class="sum" x="{PAD}" y="{12+18+14*(k+1)-2}">{esc(ln)}</text>')
        if is_entry:
            out.append(f'<g class="badge"><rect x="{CARD_W-70}" y="-12" width="62" height="22" rx="11"/>'
                       f'<text x="{CARD_W-39}" y="3" text-anchor="middle">START</text></g>')
        for r in s["_rows"]:
            ry = r["y"]
            if r["line"]:
                out.append(f'<rect class="rowbg" data-card="{esc(sid)}" data-line="{r["line"]}" x="3" y="{ry}" width="{CARD_W-6}" height="{r["h"]}"/>')
            out.append(f'<line class="sep" x1="{PAD}" x2="{CARD_W-PAD}" y1="{ry}" y2="{ry}"/>')
            is_hot = (sid, r["id"]) in hot
            top = 4 if r["auto"] else 5
            out.append(f'<circle class="dot{" hot" if is_hot else ""}" cx="{PAD+4+r["ind"]}" cy="{ry+top+LINE_H/2}" r="{3.5 if is_hot else 2.5}"/>')
            linked = bool(s["_path"] and r["line"])
            if linked:
                out.append(f'<g class="lnk" data-sid="{esc(sid)}" data-line="{r["line"]}"><title>{esc(s["_path"])}:{r["line"]}{" — " + esc(r["orig"]) if r["orig"] and r["orig"] != "".join(r["lines"]) else ""}</title>')
            for k, ln in enumerate(r["lines"]):
                out.append(f'<text class="item{" hotitem" if is_hot else ""}" x="{PAD+16+r["ind"]}" y="{ry+top+LINE_H*(k+1)-4}">{esc(ln)}</text>')
            if r["ref"] and r["auto"]:
                out.append(f'<text class="ref" x="{CARD_W-PAD}" y="{ry+top+LINE_H-4}" text-anchor="end">{esc(r["ref"])}</text>')
            elif r["ref"]:
                out.append(f'<text class="ref" x="{PAD+16}" y="{ry+5+LINE_H*len(r["lines"])+9}">{esc(r["ref"])}</text>')
            if linked:
                out.append("</g>")
        out.append("</g>")

    srcdata = {sid: {"path": s["_path"], "vscode": vscode_uri(s["_path"], 0), "lines": s["_lines"]}
               for sid, s in skills.items() if s["_path"]}
    srcjson = json.dumps(srcdata, ensure_ascii=False).replace("</", "<\\/")
    modeljson = json.dumps({"cw": CARD_W, "w": int(width), "h": int(height), "lang": spec.get("ui_lang", "ja"),
                            "skill": {sid: norm_skill(s.get("skill", sid)) for sid, s in skills.items()},
                            "rows": {sid: [[r["line"], "".join(r["lines"])] for r in s["_rows"] if r["line"]]
                                     for sid, s in skills.items()},
                            "title": spec.get("title", ""), "entry": entry,
                            "cards": {sid: [pos[sid][0], pos[sid][1], skills[sid]["_h"]] for sid in skills},
                            "edges": emodel}, ensure_ascii=False)
    ui = UI.get(spec.get("ui_lang", "ja"), UI["ja"])  # 画面の文言(ja / en)。見出しや説明の言語とは別
    title = esc(spec.get("title", "スキル設計図"))
    src = esc(spec.get("source", ""))
    body = "\n".join(out)
    doc = f"""<!doctype html>
<html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<style>
:root{{--bg:#f7f6f2;--card:#fff;--ink:#23211c;--sub:#6b665b;--line:#d9d5c8;--accent:#2f6fed;--head:#eef3ff;--cond:#b45309;--condbg:#fff4e0;--entry:#0f9d6b;--entryhead:#e3f6ee}}
@media (prefers-color-scheme:dark){{:root{{--bg:#17161a;--card:#222126;--ink:#ecebe6;--sub:#a29d90;--line:#3a3840;--accent:#7aa2ff;--head:#2a3040;--cond:#f5b25c;--condbg:#3a2e1c;--entry:#3ecf9a;--entryhead:#1f3a30}}}}
body{{margin:0;background:var(--bg);color:var(--ink);font-family:system-ui,"Hiragino Sans","Yu Gothic UI","Meiryo",sans-serif}}
header{{padding:22px 40px 0}}h1{{margin:0;font-size:22px}}.src{{color:var(--sub);font-size:12px;margin-top:4px}}
.legend{{display:flex;gap:18px;font-size:12px;color:var(--sub);margin-top:10px;flex-wrap:wrap}}
.legend i{{display:inline-block;width:26px;height:0;border-top:2px solid var(--accent);vertical-align:middle;margin-right:6px}}
.legend i.c{{border-top-color:var(--cond)}}.legend i.b{{border-top:2px dashed var(--sub)}}
.wrap{{overflow:auto;height:calc(100vh - 130px);margin-top:8px;cursor:grab;border-top:1px solid var(--line)}}.wrap.drag{{cursor:grabbing;user-select:none}}svg{{display:block;height:auto;user-select:none;-webkit-user-select:none}}
.zoom{{position:fixed;right:16px;top:14px;display:flex;gap:4px;align-items:center;z-index:5;background:var(--card);border:1px solid var(--line);border-radius:8px;padding:4px}}
.zoom button{{border:0;background:transparent;color:var(--ink);font-size:15px;min-width:32px;height:30px;border-radius:6px;cursor:pointer}}.zoom button:hover{{background:var(--head)}}.zoom span{{font-size:12px;color:var(--sub);min-width:44px;text-align:center}}
.box{{fill:var(--card);stroke:var(--line);stroke-width:1.2}}.entry .box{{stroke:var(--entry);stroke-width:2.2}}
.head,.headfill{{fill:var(--head)}}.entry .head,.entry .headfill{{fill:var(--entryhead)}}
.name{{font-size:14px;font-weight:700;fill:var(--ink)}}.sum{{font-size:11px;fill:var(--sub)}}
.item{{font-size:12px;fill:var(--ink)}}.ref{{font-size:10px;fill:var(--sub)}}
#pane{{position:fixed;top:0;right:0;bottom:0;width:min(600px,max(48vw,380px));max-width:100vw;background:var(--card);border-left:1px solid var(--line);box-shadow:-6px 0 20px #0003;display:none;flex-direction:column;z-index:10}}
#pane.on{{display:flex}}@media (max-width:700px){{#pane{{width:100vw;border-left:0}}.zoom{{top:auto;bottom:10px;right:10px}}header{{padding:14px 16px 0}}}}#ph{{padding:10px 12px;border-bottom:1px solid var(--line);font-size:12px}}#ph b{{font-size:14px}}
#ph .p{{color:var(--sub);word-break:break-all;margin:2px 0 6px}}#ph button,#ph a{{font-size:12px;border:1px solid var(--line);background:var(--head);color:var(--ink);border-radius:6px;padding:3px 8px;cursor:pointer;text-decoration:none;margin-right:4px}}
#pb{{flex:1;overflow:auto;font:12px/1.55 ui-monospace,Consolas,monospace;padding:6px 0}}
#pb div{{display:flex;white-space:pre-wrap;word-break:break-word;padding:0 10px 0 0}}#pb i{{flex:none;width:44px;text-align:right;padding-right:10px;color:var(--sub);font-style:normal;user-select:none}}
#pb div.hit{{background:var(--condbg);outline:1px solid var(--cond)}}
/*LIVECSS*/
.card,.elabel{{cursor:move}}.lnk{{cursor:pointer}}.lnk:hover text{{text-decoration:underline;fill:var(--accent)}}
.sep{{stroke:var(--line);stroke-width:1}}.dot{{fill:var(--sub);opacity:.5}}.dot.hot{{fill:var(--accent);opacity:1}}.hotitem{{font-weight:700}}
.badge rect{{fill:var(--entry)}}.badge text{{fill:#fff;font-size:11px;font-weight:700}}
.edge{{fill:none;stroke:var(--accent);stroke-width:1.8}}.edge.conditional{{stroke:var(--cond)}}
.edge.optional,.edge.back{{stroke-dasharray:6 4}}.edge.back{{stroke:var(--sub)}}
.elabel rect{{fill:var(--condbg);stroke:var(--cond);stroke-width:1}}.elabel text{{font-size:11px;fill:var(--cond)}}
.elabel.always rect{{fill:var(--card);stroke:var(--line)}}.elabel.always text{{fill:var(--sub)}}
@media print{{@page{{size:{int(width)}px {int(height)}px;margin:0}}header{{padding-top:12px}}.zoom{{display:none}}.wrap{{height:auto;overflow:visible}}svg{{width:100%!important}}}}
</style></head><body>
<header><h1>{title}</h1><div class="src">{src}</div>
<div class="legend"><span><i></i>{ui["always"]}</span><span><i class="c"></i>{ui["cond"]}</span><span><i class="b"></i>{ui["back"]}</span><span>{ui["items"]}</span><span style="color:var(--accent)">{ui["hot"]}</span></div></header>
<div class="wrap"><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {int(width)} {int(height)}">
<defs><marker id="arr" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="context-stroke"/></marker></defs>
{body}
</svg></div>
<div class="zoom"><button id="zo">−</button><span id="zv"></span><button id="zi">＋</button><button id="zf">{ui["fit"]}</button><button id="z1">100%</button><button id="zr">{ui["reset"]}</button></div>
<script id="model" type="application/json">{modeljson}</script>
<div id="pane"><div id="ph"><b id="pt"></b><div class="p" id="pp"></div><button id="pc">{ui["copy"]}</button><a id="pv" href="#">{ui["vscode"]}</a><button id="px">{ui["close"]}</button></div><div id="pb"></div></div>
<script id="srcdata" type="application/json">{srcjson}</script>
<script>
(function(){{
  var SRC=JSON.parse(document.getElementById('srcdata').textContent);
  var pane=document.getElementById('pane'), pb=document.getElementById('pb'), cur=null, moved=false;
  function show(sid,line){{
    var d=SRC[sid]; if(!d) return; cur=d;
    document.getElementById('pt').textContent=sid;
    document.getElementById('pp').textContent=d.path+':'+line;
    document.getElementById('pv').href=d.vscode+':'+line;
    pb.textContent='';
    d.lines.forEach(function(t,i){{
      var r=document.createElement('div'), n=document.createElement('i'), s=document.createElement('span');
      n.textContent=i+1; s.textContent=t||' '; r.appendChild(n); r.appendChild(s);
      if(i+1===line) r.className='hit'; pb.appendChild(r);
    }});
    pane.classList.add('on');
    var h=pb.querySelector('.hit'); if(h) pb.scrollTop=h.offsetTop-pb.clientHeight/3;
  }}
  document.getElementById('px').onclick=function(){{ pane.classList.remove('on'); }};
  document.getElementById('pc').onclick=function(){{
    if(!cur) return; var b=this, t=cur.path;
    (navigator.clipboard?navigator.clipboard.writeText(t):Promise.reject()).catch(function(){{
      var a=document.createElement('textarea'); a.value=t; document.body.appendChild(a); a.select(); try{{document.execCommand('copy');}}catch(e){{}} a.remove();
    }}).then(function(){{ b.textContent='{ui["copied"]}'; setTimeout(function(){{ b.textContent='{ui["copy"]}'; }},1500); }});
  }};
  document.querySelector('.wrap').addEventListener('click',function(e){{
    if(moved) return;
    var g=e.target.closest('.lnk'); if(g) show(g.dataset.sid, parseInt(g.dataset.line,10));
  }});
  window.addEventListener('keydown',function(e){{ if(e.key==='Escape') pane.classList.remove('on'); }});

  // --- カードのドラッグ移動(矢印・ラベルは追従) ---
  var M=JSON.parse(document.getElementById('model').textContent), P0=JSON.parse(JSON.stringify(M.cards));
  var svgEl=document.querySelector('.wrap svg');
  window.BP={{M:M, wrap:wrap, svg:svgEl}};
  function bez(p,t){{ var m=1-t; return [m*m*m*p[0][0]+3*m*m*t*p[1][0]+3*m*t*t*p[2][0]+t*t*t*p[3][0], m*m*m*p[0][1]+3*m*m*t*p[1][1]+3*m*t*t*p[2][1]+t*t*t*p[3][1]]; }}
  function layout(){{
    M.edges.forEach(function(e,i){{
      var A=M.cards[e.a], B=M.cards[e.b], y1=A[1]+e.ay, y2=B[1]+e.by, pts, x1, x2;
      if(!e.back){{ x1=A[0]+M.cw; x2=B[0]; var d=Math.max(50,(x2-x1)/2); pts=[[x1,y1],[x1+d,y1],[x2-d,y2],[x2,y2]]; }}
      else{{ x1=A[0]+M.cw; x2=B[0]+M.cw; var far=Math.max(x1,x2)+e.far; pts=[[x1,y1],[far,y1],[far,y2],[x2,y2]]; }}
      var dstr='M'+pts[0]+' C'+pts[1]+' '+pts[2]+' '+pts[3];
      if(e.lab){{
        var q=bez(pts,e.t), lx=q[0]+(e.ox||0), ly=q[1]+e.dy+(e.oy||0);
        if(e.ox||e.oy){{ // ラベルを動かしたら、矢印もラベルの中心を通るように曲げる
          var sg=lx>=x1?1:-1, d1=Math.max(40,Math.abs(lx-x1)/2), d2=Math.max(40,Math.abs(x2-lx)/2), ex=e.back?x2+d2:x2-d2;
          dstr='M'+x1+','+y1+' C'+(x1+d1)+','+y1+' '+(lx-sg*d1)+','+ly+' '+lx+','+ly+' C'+(lx+sg*d2)+','+ly+' '+ex+','+y2+' '+x2+','+y2;
        }}
        document.getElementById('l'+i).setAttribute('transform','translate('+lx.toFixed(1)+','+ly.toFixed(1)+')');
      }}
      document.getElementById('e'+i).setAttribute('d',dstr);
    }});
    fitCanvas();
  }}
  // 図の領域は内容に合わせて四方向に広がる(元の大きさより小さくはしない)
  var VB={{x:0,y:0,w:M.w,h:M.h}};
  function fitCanvas(){{
    var bb=svgEl.getBBox(), x0=Math.min(0,bb.x-40), y0=Math.min(0,bb.y-40),
        x1=Math.max(M.w,bb.x+bb.width+40), y1=Math.max(M.h,bb.y+bb.height+40);
    if(x0===VB.x&&y0===VB.y&&x1-x0===VB.w&&y1-y0===VB.h) return;
    var dx=VB.x-x0, dy=VB.y-y0;
    VB={{x:x0,y:y0,w:x1-x0,h:y1-y0}};
    svgEl.setAttribute('viewBox',VB.x+' '+VB.y+' '+VB.w+' '+VB.h);
    W=VB.w; svgEl.style.width=(W*z)+'px';
    wrap.scrollLeft+=dx*z; wrap.scrollTop+=dy*z;
  }}
  function place(sid){{ var c=M.cards[sid]; document.getElementById('c-'+sid).setAttribute('transform','translate('+c[0]+','+c[1]+')'); }}
  Object.keys(M.cards).forEach(function(sid){{
    var el=document.getElementById('c-'+sid);
    el.addEventListener('mousedown',function(e){{
      e.stopPropagation(); e.preventDefault(); moved=false;
      var sc=svgEl.getBoundingClientRect().width/VB.w, sx0=e.clientX, sy0=e.clientY, c=M.cards[sid], ox=c[0], oy=c[1];
      function mv(ev){{
        var dx=ev.clientX-sx0, dy=ev.clientY-sy0;
        if(!moved && Math.abs(dx)+Math.abs(dy)>4){{ moved=true; el.parentNode.appendChild(el); }} // 最前面へ(クリック中に付け替えるとclickが消えるので動かし始めてから)
        if(!moved) return;
        c[0]=ox+dx/sc; c[1]=oy+dy/sc; // 範囲の制限なし。はみ出したら図の領域が広がる
        place(sid); layout();
      }}
      function up(){{ window.removeEventListener('mousemove',mv); window.removeEventListener('mouseup',up); el.style.cursor=''; }}
      window.addEventListener('mousemove',mv); window.addEventListener('mouseup',up);
    }});
  }});
  // --- 矢印の中央のラベル(四角)もドラッグ移動。曲線上の位置からのズレとして保持するのでカードを動かしても追従 ---
  M.edges.forEach(function(e,i){{
    if(!e.lab) return;
    var el=document.getElementById('l'+i);
    el.addEventListener('mousedown',function(ev){{
      ev.stopPropagation(); ev.preventDefault();
      var sc=svgEl.getBoundingClientRect().width/VB.w, sx0=ev.clientX, sy0=ev.clientY, ox=e.ox||0, oy=e.oy||0;
      function mv(m){{ e.ox=ox+(m.clientX-sx0)/sc; e.oy=oy+(m.clientY-sy0)/sc; layout(); }}
      function up(){{ window.removeEventListener('mousemove',mv); window.removeEventListener('mouseup',up); }}
      window.addEventListener('mousemove',mv); window.addEventListener('mouseup',up);
    }});
  }});
  document.getElementById('zr').onclick=function(){{
    M.cards=JSON.parse(JSON.stringify(P0)); Object.keys(M.cards).forEach(place);
    M.edges.forEach(function(e){{ e.ox=0; e.oy=0; }}); layout();
  }};
  var W={int(width)}, wrap=document.querySelector('.wrap'), svg=wrap.querySelector('svg'), zv=document.getElementById('zv');
  var z=1, fit=1;
  function calcFit(){{ fit=Math.min(1, (wrap.clientWidth-16)/W); }}
  function apply(nz, cx, cy){{
    nz=Math.max(fit*0.5, Math.min(4, nz));
    var r=nz/z, px=wrap.scrollLeft+cx, py=wrap.scrollTop+cy;
    z=nz; svg.style.width=(W*z)+'px'; zv.textContent=Math.round(z*100)+'%';
    wrap.scrollLeft=px*r-cx; wrap.scrollTop=py*r-cy;
  }}
  function center(){{ return [wrap.clientWidth/2, wrap.clientHeight/2]; }}
  function fitAll(){{ calcFit(); z=fit; svg.style.width=(W*z)+'px'; zv.textContent=Math.round(z*100)+'%'; wrap.scrollLeft=0; wrap.scrollTop=0; }}
  document.getElementById('zi').onclick=function(){{ var c=center(); apply(z*1.25,c[0],c[1]); }};
  document.getElementById('zo').onclick=function(){{ var c=center(); apply(z/1.25,c[0],c[1]); }};
  document.getElementById('zf').onclick=fitAll;
  document.getElementById('z1').onclick=function(){{ var c=center(); apply(1,c[0],c[1]); }};
  wrap.addEventListener('wheel',function(e){{
    e.preventDefault();
    var b=wrap.getBoundingClientRect();
    apply(z*(e.deltaY<0?1.1:1/1.1), e.clientX-b.left, e.clientY-b.top);
  }},{{passive:false}});
  var sx,sy,sl,st,down=false;
  wrap.addEventListener('mousedown',function(e){{ e.preventDefault(); moved=false; down=true; sx=e.clientX; sy=e.clientY; sl=wrap.scrollLeft; st=wrap.scrollTop; wrap.classList.add('drag'); }});
  window.addEventListener('mouseup',function(){{ down=false; wrap.classList.remove('drag'); }});
  window.addEventListener('mousemove',function(e){{ if(!down) return; if(Math.abs(e.clientX-sx)+Math.abs(e.clientY-sy)>4) moved=true; wrap.scrollLeft=sl-(e.clientX-sx); wrap.scrollTop=st-(e.clientY-sy); }});
  window.addEventListener('keydown',function(e){{
    if(e.key==='+'||e.key==='='){{ document.getElementById('zi').click(); }}
    else if(e.key==='-'){{ document.getElementById('zo').click(); }}
    else if(e.key==='0'){{ fitAll(); }}
  }});
  window.addEventListener('resize',function(){{ var old=fit; calcFit(); if(Math.abs(z-old)<1e-6) fitAll(); }});
  fitAll();
}})();
</script>
<!--LIVEJS--></body></html>"""
    # 実行ログの重ね表示と統計ビュー(live.css / live.js をそのまま埋め込む。波括弧のエスケープを避けるため別ファイル)
    here = os.path.dirname(os.path.abspath(__file__))
    css = open(os.path.join(here, "live.css"), encoding="utf-8").read()
    js = open(os.path.join(here, "live.js"), encoding="utf-8").read()
    doc = doc.replace("/*LIVECSS*/", css).replace("<!--LIVEJS-->", "<script>\n" + js + "\n</script>")
    open(out_path, "w", encoding="utf-8").write(doc)
    print(f"wrote {out_path}  ({len(skills)} skills, {len(edges)} edges)")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) == 2 and os.path.isdir(sys.argv[1]):  # 設計図フォルダ: spec.json -> index.html
        main(os.path.join(sys.argv[1], "spec.json"), os.path.join(sys.argv[1], "index.html"))
    elif len(sys.argv) == 3:
        main(sys.argv[1], sys.argv[2])
    else:
        sys.exit(__doc__)
