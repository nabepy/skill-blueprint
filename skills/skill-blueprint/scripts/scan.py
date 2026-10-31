#!/usr/bin/env python3
"""skills フォルダ配下の指定フォルダを走査し、各スキルの見出し・他スキルへの参照をJSONで出力する。

usage: python scan.py <フォルダ名 | パス | @project | @user> [--skills-dir DIR]
  @project = <cwd>/.claude/skills   @user = ~/.claude/skills
"""
import argparse, json, os, re, sys

def find_skills_dir(explicit):
    if explicit:
        return os.path.abspath(explicit)
    here = os.path.abspath(os.path.dirname(__file__))
    for start in (os.getcwd(), here):
        d = start
        while True:
            cand = os.path.join(d, "skills")
            if os.path.isdir(cand) and not os.path.exists(os.path.join(cand, "SKILL.md")):
                return cand
            parent = os.path.dirname(d)
            if parent == d:
                break
            d = parent
    sys.exit("skills フォルダが見つかりません。--skills-dir で指定してください")

def resolve_target(skills_dir, name):
    if os.path.isdir(name):
        return os.path.abspath(name)
    direct = os.path.join(skills_dir, name)
    if os.path.isdir(direct):
        return direct
    for root, dirs, _ in os.walk(skills_dir):
        if name in dirs:
            return os.path.join(root, name)
    sys.exit(f"フォルダ '{name}' が {skills_dir} 以下に見つかりません")

def parse_frontmatter(text):
    m = re.match(r"---\s*\n(.*?)\n---\s*\n", text, re.S)
    fm, body_start = {}, 0
    if m:
        body_start = m.end()
        key = None
        for line in m.group(1).splitlines():
            km = re.match(r"^([\w-]+):\s*(.*)$", line)
            if km:
                key = km.group(1)
                v = km.group(2).strip()
                fm[key] = "" if v in (">", "|", ">-", "|-") else v.strip("\"'")
            elif key and line.strip():
                fm[key] = (fm[key] + " " + line.strip()).strip()
    return fm, body_start

def headings(lines):
    out, fence = [], False
    for i, line in enumerate(lines, 1):
        if line.lstrip().startswith("```"):
            fence = not fence
        if fence:
            continue
        m = re.match(r"^(#{1,4})\s+(.+?)\s*$", line)
        if m:
            out.append({"line": i, "level": len(m.group(1)), "title": m.group(2)})
    return out

def special_target(folder):
    """@project = <cwd>/.claude/skills、@user = ~/.claude/skills"""
    if folder == "@project":
        t = os.path.join(os.getcwd(), ".claude", "skills")
    elif folder == "@user":
        t = os.path.join(os.path.expanduser("~"), ".claude", "skills")
    else:
        return None
    if not os.path.isdir(t):
        sys.exit(f"{t} がありません")
    return t

def scan(folder, skills_dir_arg=None):
    target = special_target(folder)
    if target:
        skills_dir = target
    else:
        skills_dir = find_skills_dir(skills_dir_arg)
        target = resolve_target(skills_dir, folder)

    skills = {}
    for root, dirs, files in os.walk(target):
        dirs[:] = [d for d in dirs if d not in (".git", "node_modules")]
        if "SKILL.md" in files:
            path = os.path.join(root, "SKILL.md")
            text = open(path, encoding="utf-8", errors="replace").read()
            fm, _ = parse_frontmatter(text)
            name = fm.get("name") or os.path.basename(root)
            lines = text.splitlines()
            others = [os.path.relpath(os.path.join(r, f), root).replace("\\", "/")
                      for r, _, fs in os.walk(root) for f in fs if f != "SKILL.md"
                      and not r.startswith(os.path.join(root, ".git"))]
            skills[name] = {"name": name, "dir": root, "path": path,
                            "description": fm.get("description", ""),
                            "trigger": fm.get("trigger", ""),
                            "line_count": len(lines),
                            "headings": headings(lines),
                            "files": sorted(others)[:40],
                            "refs": []}
    names = list(skills)
    for s in skills.values():
        targets = [("SKILL.md", s["path"])]
        for f in s["files"]:
            if f.endswith(".md"):
                targets.append((f, os.path.join(s["dir"], f)))
        for fname, p in targets:
            lines = open(p, encoding="utf-8", errors="replace").read().splitlines()
            hs = headings(lines)
            for i, line in enumerate(lines, 1):
                for n in names:
                    if n == s["name"]:
                        continue
                    esc = re.escape(n)
                    pat = (rf"(?:[\w-]+:{esc}(?![\w-]))|(?:[`\"'*「]{esc}[`\"'*」])|"
                           rf"(?:(?<![\w-]){esc}(?![\w-])\s*(?:skill|スキル))|(?:(?:skill|スキル)\s*[`\"'*「]?{esc}(?![\w-]))")
                    if re.search(pat, line):
                        sec = next((h["title"] for h in reversed(hs) if h["line"] <= i), "")
                        s["refs"].append({"to": n, "file": fname, "line": i,
                                          "section": sec, "text": line.strip()[:220]})
    incoming = {n: 0 for n in names}
    for s in skills.values():
        for t in {r["to"] for r in s["refs"]}:
            incoming[t] += 1
    result = {"target": target, "skills_dir": skills_dir,
              "entry_candidates": [n for n in names if incoming[n] == 0],
              "skills": list(skills.values())}
    return result

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folder", help="フォルダ名 / パス / @project / @user")
    ap.add_argument("--skills-dir")
    a = ap.parse_args()
    json.dump(scan(a.folder, a.skills_dir), sys.stdout, ensure_ascii=False, indent=1)

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
