#!/usr/bin/env python3
"""設計図のスペック(spec.json)の下書きを機械的に作る。ラベルの推敲・翻訳・誤検出の除去は AI が仕上げる。

usage: python scaffold.py <対象> --mode all|each [--skill 名前] [--out blueprints] [--force]

  対象   フォルダ名 / パス / @project(<cwd>/.claude/skills) / @user(~/.claude/skills)
  all    対象にあるスキル全部を1枚に(スキル同士の呼び出し関係)    → <out>/<対象名>/spec.json
  each   スキル1つにつき1枚(SKILL.md と references 等の関係)       → <out>/<スキル名>/spec.json
         --skill で1つだけ作る

下書きの判断はすべて機械的: 他スキル/参照ファイルの言及行を矢印にし、条件語(if/when/場合/とき...)があれば
条件つき、無ければ「必ず」とする。START は被参照ゼロのスキルから選ぶ。
"""
import argparse, json, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scan as S

COND = re.compile(r"\b(if|when|unless|only|otherwise|in case|depending)\b|場合|とき|なら|以外|必要に応じ|ない時|する時", re.I)
START = re.compile(r"(start|begin|any conversation|before any|最初|開始|会話の)", re.I)


def short(text, n=34):
    t = re.sub(r"[`*>#|]+", "", text).strip(" -–—:")
    t = re.sub(r"\s+", " ", t)
    return t if len(t) <= n else t[: n - 1] + "…"


def first_sentence(desc, n=70):
    d = re.sub(r"\s+", " ", desc or "").strip()
    m = re.search(r"。|\. ", d)
    if m and m.start() < n:
        d = d[: m.start() + (1 if d[m.start()] == "。" else 0)]
    return d if len(d) <= n else d[: n - 1] + "…"


def sid(s):
    return re.sub(r"[^\w\-]+", "-", s).strip("-")


def target_name(folder):
    if folder in ("@project", "@user"):
        return folder[1:] + "-skills"
    return os.path.basename(os.path.abspath(folder.rstrip("/\\"))) or "skills"


def write(spec, outdir, name, force):
    d = os.path.join(outdir, name)
    p = os.path.join(d, "spec.json")
    if os.path.exists(p) and not force:
        print(f"skip (exists): {p}   (--force で上書き)")
        return None
    os.makedirs(d, exist_ok=True)
    json.dump(spec, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"wrote {p}  ({len(spec['skills'])} cards, {len(spec['edges'])} edges)")
    return p


def mode_all(res, folder, outdir, force):
    skills = {s["name"]: s for s in res["skills"]}
    if not skills:
        sys.exit("SKILL.md が見つかりません")
    out_cnt = {n: len({r["to"] for r in s["refs"]}) for n, s in skills.items()}
    cands = res["entry_candidates"] or list(skills)
    entry = next((n for n in cands if START.search(skills[n]["description"] or "")), None) \
        or max(cands, key=lambda n: out_cnt[n])
    edges, seen = [], set()
    for n, s in skills.items():
        for r in sorted(s["refs"], key=lambda r: (r["file"] != "SKILL.md", r["line"])):
            if (n, r["to"]) in seen:
                continue
            seen.add((n, r["to"]))
            main = r["file"] == "SKILL.md"
            e = {"from": n, "to": r["to"],
                 "label": f"{short(r['text'])} ({'' if main else r['file'] + ':'}L{r['line']})" if True else "",
                 "kind": "conditional" if COND.search(r["text"]) else "always"}
            if main:
                e["from_item"] = f"L{r['line']}"
            edges.append(e)
    # 他から参照されず、参照もしない独立スキルには矢印を引かない(根拠のない矢印は作らない)。
    # render.py が破線の枠で描くので、spec の skills[].standalone に起動条件を書く
    ref_cards = []
    # スキル配下の .md は、フォルダ名(references など)に関係なくすべてカードにする。
    # 矢印は、SKILL.md や別の .md が実際に名指ししている行から引く(条件語があれば conditional)。
    # どこからも名指しされていない .md も「関連ファイル」として載せる(矢印なし。render.py が破線の枠で描く)
    for n, s in skills.items():
        cid_of = {"SKILL.md": n}
        for f in s["files"]:
            if f.endswith(".md"):
                cid_of[f] = f"{n}--ref-{sid(f)}"
                ref_cards.append({"id": cid_of[f], "name": f"{n}/{f}", "summary": "", "file": True,
                                  "path": os.path.join(s["dir"], f), "heading_levels": 2})
        seen_pair = set()
        for r in sorted(s.get("file_refs", []), key=lambda r: (r["from"] != "SKILL.md", r["from"], r["line"])):
            if (r["from"], r["to"]) in seen_pair:
                continue
            seen_pair.add((r["from"], r["to"]))
            edges.append({"from": cid_of[r["from"]], "from_item": f"L{r['line']}", "to": cid_of[r["to"]],
                          "label": f"{short(r['text'])} (L{r['line']})",
                          "kind": "conditional" if COND.search(r["text"]) else "always"})
    cards = [{"id": n, "summary": first_sentence(s["description"]), "path": s["path"]} for n, s in skills.items()]
    if len(skills) == 1:  # スキルが1つで SKILL.md が長いときは、節ごとのカードに分ける(1枚に見出しが並ぶだけだと流れが分からない)
        cards, edges, entry = split_sections(next(iter(skills.values())), cards, edges, entry)
    spec = {"title": f"{target_name(folder)} の設計図", "source": res["target"], "base": res["target"],
            "entry": entry, "heading_levels": 2, "skills": cards + ref_cards, "edges": edges}
    return write(spec, outdir, target_name(folder), force)


SPLIT_MIN_LINES, SPLIT_MIN_H2, LONG_SECTION, CHUNK_MIN = 100, 4, 80, 10  # 80行を超える節だけ、10行以上たまるごとに ### で分ける


def split_sections(s, cards, edges, entry):
    """1スキルの長い SKILL.md を、`##` の節(長い節は `###` の切れ目)ごとのカードに分ける。
    節どうしの矢印は、ある節の本文が別の節の見出し名に言及している行から引く(下書き。流れは原文を読んで仕上げる)。"""
    lines = open(s["path"], encoding="utf-8", errors="replace").read().splitlines()
    if len(lines) < SPLIT_MIN_LINES:
        return cards, edges, entry
    hs, fence = [], False
    for i, ln in enumerate(lines, 1):
        if ln.lstrip().startswith("```"):
            fence = not fence
        m = None if fence else re.match(r"^(#{2,3})\s+(.+?)\s*$", ln)
        if m:
            hs.append((i, len(m.group(1)), m.group(2)))
    h2 = [h for h in hs if h[1] == 2]
    if len(h2) < SPLIT_MIN_H2:
        return cards, edges, entry
    chunks = []  # [start, end, title]
    for k, (ln, _, title) in enumerate(h2):
        end = (h2[k + 1][0] - 1) if k + 1 < len(h2) else len(lines)
        subs = [h for h in hs if h[1] == 3 and ln < h[0] <= end]
        cur = [ln if k else 1, ln, title]
        for h in subs:
            if end - ln + 1 > LONG_SECTION and h[0] - cur[1] >= CHUNK_MIN and end - h[0] >= CHUNK_MIN // 2:
                chunks.append([cur[0], h[0] - 1, cur[2]])
                cur = [h[0], h[0], re.sub(r"^(Step\s*\d+\s*[:：]?\s*)", "", h[2])]
        chunks.append([cur[0], end, cur[2]])
    n = s["name"]
    ids = [f"{n}-{k + 1}" if k else n for k in range(len(chunks))]
    new_cards = [{"id": ids[k], "skill": n, "part": True, "name": f"{n} : {t}",
                  "summary": first_sentence(s["description"]) if k == 0 else "",
                  "path": s["path"], "range": [a, b], "heading_levels": 3} for k, (a, b, t) in enumerate(chunks)]

    def card_at(line):
        return next((ids[k] for k, (a, b, _) in enumerate(chunks) if a <= line <= b), ids[0])

    out = []
    for e in edges:  # SKILL.md から出ていた矢印(付属ファイル行き)は、その行を含む節のカードから出す
        if e["from"] == n and e.get("from_item", "").startswith("L"):
            e = dict(e, **{"from": card_at(int(e["from_item"][1:]))})
        out.append(e)
    keys = []
    for k, (a, b, t) in enumerate(chunks):
        key = re.split(r"[（(:：]", t)[0].strip()
        keys.append(key if len(key) >= 4 or re.search(r"[A-Z]{3}", key) else "")
    for k, (a, b, t) in enumerate(chunks):
        for j, key in enumerate(keys):
            if j == k or not key:
                continue
            hit = next(((i, lines[i - 1]) for i in range(a + 1, b + 1)
                        if key.lower() in lines[i - 1].lower() and not lines[i - 1].lstrip().startswith("#")), None)
            if hit:
                i, ln = hit
                out.append({"from": ids[k], "from_item": f"L{i}", "to": ids[j], "label": f"{short(ln)} (L{i})",
                            "kind": "conditional" if COND.search(ln) else "always"})
    return new_cards, out, ids[0]


def mode_each(res, outdir, force, only):
    made = []
    for s in res["skills"]:
        if only and s["name"] != only:
            continue
        main = sid(s["name"])
        cards = [{"id": main, "skill": s["name"], "name": "SKILL.md", "summary": first_sentence(s["description"]),
                  "path": s["path"], "heading_levels": 3}]
        lines = open(s["path"], encoding="utf-8", errors="replace").read().splitlines()
        edges = []
        for f in s["files"]:
            if not f.endswith(".md"):
                continue
            cid = "ref-" + sid(f)
            cards.append({"id": cid, "name": f, "summary": "", "path": os.path.join(s["dir"], f), "heading_levels": 2})
            pat = re.compile(r"(?<![\w/.-])" + re.escape(f) + r"|(?<![\w/.-])" + re.escape(os.path.basename(f)) + r"(?![\w.-])")
            hit = next(((i, ln) for i, ln in enumerate(lines, 1) if pat.search(ln)), None)
            if hit:
                i, ln = hit
                edges.append({"from": main, "from_item": f"L{i}", "to": cid, "label": f"{short(ln)} (L{i})",
                              "kind": "conditional" if COND.search(ln) else "always"})
        spec = {"title": f"{s['name']} の設計図", "source": s["dir"], "entry": main, "heading_levels": 2,
                "skills": cards, "edges": edges}
        p = write(spec, outdir, sid(s["name"]), force)
        if p:
            made.append(p)
    if only and not made and not any(x["name"] == only for x in res["skills"]):
        sys.exit(f"スキル '{only}' が見つかりません: " + ", ".join(x["name"] for x in res["skills"]))
    return made


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folder")
    ap.add_argument("--mode", choices=["all", "each"], default="all")
    ap.add_argument("--skill")
    ap.add_argument("--out", default="blueprints")
    ap.add_argument("--skills-dir")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    res = S.scan(a.folder, a.skills_dir)
    # このスキル自身は、他にスキルがあれば図から外す(@project / @user で自分が混ざるのを防ぐ。個別なら --skill で指定可)
    if a.mode == "all" and len(res["skills"]) > 1:
        res["skills"] = [s for s in res["skills"] if s["name"] != "skill-blueprint"]
        res["entry_candidates"] = [n for n in res["entry_candidates"] if n != "skill-blueprint"]
    if a.mode == "all":
        mode_all(res, a.folder, a.out, a.force)
    else:
        mode_each(res, a.out, a.force, a.skill)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
