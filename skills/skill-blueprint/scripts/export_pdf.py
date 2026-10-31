#!/usr/bin/env python3
"""設計図(index.html)を、図全体が1ページに入ったPDFにして書き出す。ヘッドレスの Edge / Chrome を使う。

usage: python export_pdf.py <blueprints/設計図名> [-o 出力.pdf]
  出力先を省略すると <設計図フォルダ>/blueprint.pdf に書く。
ブラウザで開いている設計図の右上の「PDF」ボタンからも、同じ内容を印刷ダイアログ経由で保存できる。
"""
import argparse, os, shutil, subprocess, sys, tempfile

CANDIDATES = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
]
NAMES = ["msedge", "microsoft-edge", "google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "chrome"]


def find_browser():
    for p in CANDIDATES:
        if os.path.isfile(p):
            return p
    for n in NAMES:
        p = shutil.which(n)
        if p:
            return p
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("folder")
    ap.add_argument("-o", "--output")
    a = ap.parse_args()
    root = os.path.abspath(a.folder)
    html = os.path.join(root, "index.html")
    if not os.path.isfile(html):
        sys.exit(f"index.html がありません(先に render.py で作ってください): {html}")
    out = os.path.abspath(a.output or os.path.join(root, "blueprint.pdf"))
    br = find_browser()
    if not br:
        sys.exit("Edge / Chrome が見つかりません。ブラウザで設計図を開き、右上の「PDF」ボタンから保存してください")
    if os.path.exists(out):
        os.remove(out)
    with tempfile.TemporaryDirectory() as prof:
        cmd = [br, "--headless=new", "--disable-gpu", "--no-pdf-header-footer", f"--user-data-dir={prof}",
               "--virtual-time-budget=4000", f"--print-to-pdf={out}", "file:///" + html.replace("\\", "/").lstrip("/")]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=90)
    if not os.path.isfile(out):
        sys.exit("PDF を作れませんでした。ブラウザの「PDF」ボタンから保存してください")
    print(f"pdf: {out}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
