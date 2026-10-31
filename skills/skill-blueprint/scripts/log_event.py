#!/usr/bin/env python3
"""Claude Code の hook から呼ばれ、スキルの利用を設計図フォルダのログに1行追記する。

hooks (install_hooks.py が登録):
  PreToolUse  Skill|Read   → skill / read イベント
  PostToolUse Skill        → skill_done イベント
  UserPromptSubmit         → /<skill名> で始まる入力 (スラッシュ起動) を prompt_skill として記録
  Stop / SessionEnd        → turn_end / session_end を記録し、事後解析 (analyze.py) をバックグラウンド起動

書き込み先: <プロジェクト>/blueprints/<設計図名>/logs/events.jsonl
(その設計図のスペックに含まれるスキルだけ。本文は保存せず、スキル名・行範囲・セッションIDのみ)
"""
import datetime, json, os, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))


def norm(name):
    return (name or "").strip().lstrip("/").split(":")[-1]


def blueprints(root):
    base = os.path.join(root, "blueprints")
    if not os.path.isdir(base):
        return
    for d in sorted(os.listdir(base)):
        spec = os.path.join(base, d, "spec.json")
        if os.path.isfile(spec):
            try:
                data = json.load(open(spec, encoding="utf-8"))
            except Exception:
                continue
            names = {norm(s.get("skill", s["id"])) for s in data.get("skills", [])}
            yield os.path.join(base, d), names


def has_session(logfile, sid):
    try:
        return sid in open(logfile, encoding="utf-8").read()
    except OSError:
        return False


def append(bpdir, ev):
    logs = os.path.join(bpdir, "logs")
    os.makedirs(logs, exist_ok=True)
    with open(os.path.join(logs, "events.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(ev, ensure_ascii=False) + "\n")


def main():
    try:
        p = json.loads(sys.stdin.buffer.read().decode("utf-8-sig"))
    except Exception:
        return
    root = os.environ.get("CLAUDE_PROJECT_DIR") or p.get("cwd") or os.getcwd()
    hook = p.get("hook_event_name", "")
    ev = {"ts": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
          "session": p.get("session_id", ""), "transcript": p.get("transcript_path", "")}
    skill = None
    ti = p.get("tool_input") or {}
    if hook == "PreToolUse" and p.get("tool_name") == "Skill":
        skill, ev["type"], ev["tool_use_id"] = norm(ti.get("skill")), "skill", p.get("tool_use_id", "")
    elif hook == "PostToolUse" and p.get("tool_name") == "Skill":
        skill, ev["type"], ev["tool_use_id"] = norm(ti.get("skill")), "skill_done", p.get("tool_use_id", "")
    elif hook == "PreToolUse" and p.get("tool_name") == "Read":
        fp = (ti.get("file_path") or "").replace("\\", "/")
        if fp.endswith("/SKILL.md"):
            skill, ev["type"] = fp.rsplit("/", 2)[-2], "read"
            ev["offset"], ev["limit"] = ti.get("offset"), ti.get("limit")
    elif hook == "UserPromptSubmit":
        pr = (p.get("prompt") or "").lstrip()
        if pr.startswith("/") and len(pr) > 1:
            skill, ev["type"] = norm(pr.split()[0]), "prompt_skill"
    elif hook in ("Stop", "SessionEnd"):
        ev["type"] = "turn_end" if hook == "Stop" else "session_end"
    else:
        return
    if "type" not in ev:
        return
    if skill:
        ev["skill"] = skill

    for bpdir, names in blueprints(root):
        logfile = os.path.join(bpdir, "logs", "events.jsonl")
        if skill:
            if skill not in names:
                continue
        elif not has_session(logfile, ev["session"]):
            continue  # スキルを使っていないセッションの終了は記録しない
        append(bpdir, ev)
        if ev["type"] in ("turn_end", "session_end"):
            kw = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL, "stdin": subprocess.DEVNULL}
            if os.name == "nt":
                kw["creationflags"] = 0x00000008 | 0x08000000  # DETACHED_PROCESS | CREATE_NO_WINDOW
            subprocess.Popen([sys.executable, "-I", os.path.join(HERE, "analyze.py"), bpdir], **kw)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass  # hook は絶対に作業を邪魔しない
