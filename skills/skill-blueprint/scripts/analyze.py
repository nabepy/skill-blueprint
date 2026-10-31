#!/usr/bin/env python3
"""設計図フォルダのログ (logs/events.jsonl) と会話ログ(transcript)から、
  ・セッションごとのスキル経路(正確: hooksの記録)
  ・通った項目(見出し)の推定(推定: 会話ログの文面と見出しの照合)
  ・全セッション累計の統計
を求めて stats.json に書く。

usage: python analyze.py <blueprints/設計図名>
"""
import json, math, os, re, sys, tempfile

GENERIC = {"overview", "概要", "example", "examples", "notes", "メモ"}
THRESH = 0.40


def norm(name):
    return (name or "").strip().lstrip("/").split(":")[-1]


def load_spec(bp):
    return json.load(open(os.path.join(bp, "spec.json"), encoding="utf-8"))


def card_skill(s):
    return norm(s.get("skill", s["id"]))


def parse_headings(lines):
    out, fence = [], False
    for i, ln in enumerate(lines, 1):
        if ln.lstrip().startswith("```"):
            fence = not fence
        m = None if fence else re.match(r"^(#{1,6})\s+(.+?)\s*$", ln)
        if m:
            out.append((i, len(m.group(1)), m.group(2)))
    return out


def skill_headings(spec):
    """スキル名 -> {path, lines, sections:[{line,title,text}]}  (設計図に出している見出しだけ)"""
    res = {}
    found = {}
    base = spec.get("base")
    if base and os.path.isdir(base):
        for root, _, files in os.walk(base):
            if "SKILL.md" in files:
                found[os.path.basename(root)] = os.path.join(root, "SKILL.md")
    for s in spec["skills"]:
        if s.get("items") not in (None, "headings"):
            continue
        s = dict(s, path=s.get("path") or found.get(s["id"]) or found.get(s.get("name", "")))
        if not s["path"] or not os.path.isfile(s["path"]):
            continue
        sk = card_skill(s)
        lines = open(s["path"], encoding="utf-8", errors="replace").read().splitlines()
        hs = parse_headings(lines)
        maxlv = int(s.get("heading_levels", spec.get("heading_levels", 2)))
        lo, hi = s.get("range", [1, 10**9])
        ent = res.setdefault(sk, {"path": s["path"], "total": len(lines), "sections": {}})
        for idx, (ln, lv, title) in enumerate(hs):
            if not (lo <= ln <= hi) or lv > maxlv or (lv == 1 and maxlv > 1):
                continue
            end = len(lines)
            for ln2, lv2, _ in hs[idx + 1:]:
                if lv2 <= lv:
                    end = ln2 - 1
                    break
            ent["sections"][ln] = {"line": ln, "end": end, "title": title, "text": "\n".join(lines[ln:end])}
    return res


def tokens(text):
    t = text.lower()
    toks = set(re.findall(r"[a-z][a-z0-9_\-]{2,}", t))
    for run in re.findall(r"[぀-ヿ一-鿿]+", t):
        toks.update(run[i:i + 2] for i in range(len(run) - 1))
    return toks


def read_events(bp):
    p = os.path.join(bp, "logs", "events.jsonl")
    evs = []
    if os.path.isfile(p):
        for ln in open(p, encoding="utf-8", errors="replace"):
            try:
                evs.append(json.loads(ln))
            except ValueError:
                pass
    return evs


def transcript_chunks(path):
    """アシスタントの発言とツール呼び出し(入力)を [(ts, text)] で返す。ユーザー入力・ツール結果は除く。"""
    chunks = []
    if not path or not os.path.isfile(path):
        return chunks
    for ln in open(path, encoding="utf-8", errors="replace"):
        try:
            d = json.loads(ln)
        except ValueError:
            continue
        m = d.get("message")
        if d.get("type") != "assistant" or not isinstance(m, dict) or not isinstance(m.get("content"), list):
            continue
        parts = []
        for b in m["content"]:
            if b.get("type") == "text":
                parts.append(b.get("text", ""))
            elif b.get("type") == "tool_use" and b.get("name") != "Skill":
                parts.append(b.get("name", "") + " " + json.dumps(b.get("input", {}), ensure_ascii=False))
        if parts:
            chunks.append((d.get("timestamp", ""), "\n".join(parts)))
    return chunks


def infer_items(sections, seg_text, reads):
    """見出しごとに通過の確からしさ(0-1)と根拠を返す。"""
    if not sections:
        return {}
    seg_low, seg_tok = seg_text.lower(), tokens(seg_text)
    toks = {ln: tokens(s["text"] + " " + s["title"]) for ln, s in sections.items()}
    df = {}
    for ts in toks.values():
        for t in ts:
            df[t] = df.get(t, 0) + 1
    n = len(sections)
    out = {}
    for ln, s in sections.items():
        best, why = 0.0, ""
        title = s["title"].strip()
        for cand in {title.lower(), title.split(":")[-1].strip().lower(), title.split("(")[0].strip().lower()}:
            if len(cand) >= 4 and cand not in GENERIC and cand in seg_low:
                best, why = 1.0, "見出しの文言が出力に登場"
                break
        if not why:
            w = {t: math.log(1 + n / df[t]) for t in toks[ln]}
            top = sorted(w, key=w.get, reverse=True)[:15]
            den = sum(w[t] for t in top)
            if den > 0:
                sc = sum(w[t] for t in top if t in seg_tok) / den
                if sc > best:
                    best, why = sc, "文面が節の内容に近い"
        for lo, hi in reads:
            if s["line"] <= hi and s["end"] >= lo and best < 0.7:
                best, why = 0.7, "その行範囲を読み込み"
        if best >= THRESH:
            out[ln] = {"score": round(best, 2), "why": why}
    return out


def build_sessions(spec, evs):
    heads = skill_headings(spec)
    by = {}
    for e in evs:
        by.setdefault(e.get("session", ""), []).append(e)
    sessions = []
    for sid, es in by.items():
        visits = []
        for e in es:
            if e["type"] in ("skill", "prompt_skill"):
                if visits and visits[-1]["skill"] == e["skill"] and e["ts"][:19] <= visits[-1]["ts"][:19]:
                    continue
                if visits and visits[-1]["skill"] == e["skill"] and e["type"] == "skill" and visits[-1]["via"] == "prompt":
                    continue  # /name のあとの Skill 呼び出しは同じ訪問
                visits.append({"skill": e["skill"], "ts": e["ts"], "via": "prompt" if e["type"] == "prompt_skill" else "tool",
                               "listed": e.get("listed", True)})
        if not visits:
            continue
        transcript = next((e["transcript"] for e in es if e.get("transcript")), "")
        chunks = transcript_chunks(transcript)
        for i, v in enumerate(visits):
            end = visits[i + 1]["ts"] if i + 1 < len(visits) else "9999"
            seg = "\n".join(t for ts, t in chunks if v["ts"] <= ts < end)
            reads = []
            for e in es:
                if e["type"] == "read" and e.get("skill") == v["skill"] and v["ts"] <= e["ts"] < end and e.get("offset") and e.get("limit"):
                    reads.append((int(e["offset"]), int(e["offset"]) + int(e["limit"]) - 1))
            h = heads.get(v["skill"])
            v["items"] = infer_items(h["sections"], seg, reads) if h and (seg or reads) else {}
        sessions.append({
            "id": sid, "start": es[0]["ts"], "end": es[-1]["ts"],
            "ended": any(e["type"] == "session_end" for e in es),
            "turns": sum(1 for e in es if e["type"] == "turn_end"),
            "path": visits,
        })
    sessions.sort(key=lambda s: s["start"])
    return sessions


def aggregate(spec, sessions):
    card_of = {s["id"]: card_skill(s) for s in spec["skills"]}
    planned = {(card_of[e["from"]], card_of[e["to"]]) for e in spec.get("edges", [])
               if e["from"] in card_of and e["to"] in card_of and card_of[e["from"]] != card_of[e["to"]]}
    sk, ed, un, it, ul, via = {}, {}, {}, {}, {}, {}
    for s in sessions:
        p = s["path"]
        for i, v in enumerate(p):
            listed = v.get("listed", True)
            d0 = sk if listed else ul
            d0[v["skill"]] = d0.get(v["skill"], 0) + 1
            for ln in v["items"]:
                k = f'{v["skill"]}:{ln}'
                it[k] = it.get(k, 0) + 1
            if i:
                pv = p[i - 1]
                a, b = pv["skill"], v["skill"]
                if a != b:
                    if pv.get("listed", True) and listed:
                        d = ed if (a, b) in planned else un
                    else:
                        d = via  # 設計図にないスキルをまたぐ遷移は、矢印の回数に混ぜない
                    d[f"{a}>{b}"] = d.get(f"{a}>{b}", 0) + 1
    return {"sessions": len(sessions), "skills": sk, "edges": ed, "unexpected": un, "items": it,
            "unlisted": ul, "via_unlisted": via}


def main(bp):
    spec = load_spec(bp)
    sessions = build_sessions(spec, read_events(bp))
    out = {"updated": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(timespec="seconds"),
           "item_threshold": THRESH, "sessions": sessions, "totals": aggregate(spec, sessions)}
    fd, tmp = tempfile.mkstemp(dir=bp, suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)
    os.replace(tmp, os.path.join(bp, "stats.json"))
    print(f"stats.json: {len(sessions)} sessions")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    sys.stdout.reconfigure(encoding="utf-8")
    main(os.path.abspath(sys.argv[1]))
