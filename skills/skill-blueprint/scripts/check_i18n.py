#!/usr/bin/env python3
"""設計図の翻訳(i18n/<スキルid or スキル名>.<ja|en>.md)が、原文と行数・構造で対応しているか検査する。

usage: python check_i18n.py <blueprints/設計図名>
  ・行数が原文と違う、コードフェンス(```)の位置・数が違う、見出し(#)の位置・段数が違う、を報告する。
  ・翻訳ファイルが対応するスキルを持たない(名前の誤り)も報告する。
  ・問題があれば終了コード1。翻訳フォルダが無いときは何もしない。
"""
import json, os, re, sys


def norm(name):
    return (name or "").strip().lstrip("/").split(":")[-1]


def source_path(spec, s, found):
    p = s.get("path") or found.get(s["id"]) or found.get(s.get("name", ""))
    return p if p and os.path.isfile(p) else None


def structure(lines):
    fences = [i for i, l in enumerate(lines, 1) if l.lstrip().startswith("```")]
    heads = []
    fence = False
    for i, l in enumerate(lines, 1):
        if l.lstrip().startswith("```"):
            fence = not fence
        m = None if fence else re.match(r"^(#{1,6})\s", l)
        if m:
            heads.append((i, len(m.group(1))))
    return fences, heads


def main(bp):
    d = os.path.join(bp, "i18n")
    if not os.path.isdir(d):
        print("i18n フォルダがありません(翻訳なし)")
        return 0
    spec = json.load(open(os.path.join(bp, "spec.json"), encoding="utf-8"))
    found = {}
    base = spec.get("base")
    if base and os.path.isdir(base):
        for root, _, files in os.walk(base):
            if "SKILL.md" in files:
                found[os.path.basename(root)] = os.path.join(root, "SKILL.md")
    keys = {}
    for s in spec["skills"]:
        p = source_path(spec, s, found)
        if p:
            keys.setdefault(s["id"], p)
            keys.setdefault(norm(s.get("skill", s["id"])), p)
    bad = 0
    n = 0
    for fn in sorted(os.listdir(d)):
        m = re.fullmatch(r"(.+)\.(ja|en)\.md", fn)
        if not m:
            continue
        n += 1
        key = m.group(1)
        if key not in keys:
            print(f"NG {fn}: 対応するスキルがありません(スキルid / スキル名と一致させてください)")
            bad += 1
            continue
        src = open(keys[key], encoding="utf-8", errors="replace").read().splitlines()
        tr = open(os.path.join(d, fn), encoding="utf-8", errors="replace").read().splitlines()
        probs = []
        if len(src) != len(tr):
            probs.append(f"行数が違う(原文 {len(src)} / 翻訳 {len(tr)})")
        else:
            fs, hs = structure(src)
            ft, ht = structure(tr)
            if fs != ft:
                probs.append(f"コードフェンスの位置が違う(原文 {fs[:6]}… / 翻訳 {ft[:6]}…)")
            if hs != ht:
                diff = [a for a, b in zip(hs, ht) if a != b][:3]
                probs.append(f"見出しの位置/段数が違う(例: 原文 {diff} / 翻訳 {[b for a, b in zip(hs, ht) if a != b][:3]}、見出し数 {len(hs)}/{len(ht)})")
        if probs:
            bad += 1
            print(f"NG {fn}: " + " / ".join(probs))
        else:
            print(f"OK {fn}: {len(src)} 行")
    if not n:
        print("翻訳ファイルがありません")
    return 1 if bad else 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main(os.path.abspath(sys.argv[1])))
