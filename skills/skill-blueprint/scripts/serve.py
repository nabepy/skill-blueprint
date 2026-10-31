#!/usr/bin/env python3
"""設計図フォルダをローカルで配信する(リアルタイム表示用)。127.0.0.1 のみで待ち受ける。

usage: python serve.py <blueprints/設計図名> [--port N] [--detach | --stop | --status]

  (オプションなし)  前面で配信する。表示される URL を開く。Ctrl+C で止まる。
  --detach          裏で配信して、URL を表示してすぐ戻る。すでにこのフォルダ用のサーバーが動いていれば、それを再利用する。
  --stop            --detach で起動したサーバーを止める。
  --status          動いていれば URL を表示する(動いていなければ "not running")。

ポートは省略すると設計図フォルダごとに決まる(8700〜8899。別プロジェクトの設計図と取り違えないため)。
ページはログ(logs/events.jsonl)と stats.json を1秒ごとに読み直す。/api/analyze で事後解析を再実行できる。
サーバーの情報は <設計図フォルダ>/.server.json に書く(止まったあとに残っても、使うときに生死を確かめる)。
"""
import argparse, functools, http.server, json, os, subprocess, sys, time, urllib.request, zlib

HERE = os.path.dirname(os.path.abspath(__file__))


def default_port(root):
    return 8700 + zlib.crc32(root.lower().encode("utf-8")) % 200


def state_path(root):
    return os.path.join(root, ".server.json")


def alive(port, root):
    """そのポートで、このフォルダを配信しているサーバーが動いているか"""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/__blueprint", timeout=1.5) as r:
            return r.read().decode("utf-8") == root
    except Exception:
        return False


def running(root):
    try:
        st = json.load(open(state_path(root), encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return st if alive(st["port"], root) else None


def serve(root, port):
    class H(http.server.SimpleHTTPRequestHandler):
        def end_headers(self):
            self.send_header("Cache-Control", "no-store")
            super().end_headers()

        def do_GET(self):
            if self.path.startswith("/__blueprint"):  # このサーバーが配信しているフォルダの確認用
                body = root.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if self.path.startswith("/api/analyze"):
                subprocess.run([sys.executable, "-I", os.path.join(HERE, "analyze.py"), root],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                self.send_response(204)
                self.end_headers()
                return
            super().do_GET()

        def log_message(self, *a):
            pass

    handler = functools.partial(H, directory=root)
    for p in range(port, port + 20):
        try:
            srv = http.server.ThreadingHTTPServer(("127.0.0.1", p), handler)
            break
        except OSError:
            continue
    else:
        sys.exit(f"ポート {port}〜{port + 19} が使用中です。--port で指定してください")
    json.dump({"pid": os.getpid(), "port": p}, open(state_path(root), "w", encoding="utf-8"))
    print(f"serving {root}\n  http://localhost:{p}/index.html", flush=True)
    srv.serve_forever()


def detach(root, port):
    st = running(root)
    if st:
        print(f"already running\n  http://localhost:{st['port']}/index.html")
        return
    try:
        os.remove(state_path(root))
    except OSError:
        pass
    cmd = [sys.executable, "-I", os.path.abspath(__file__), root] + (["--port", str(port)] if port else [])
    kw = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    if os.name == "nt":
        kw["creationflags"] = 0x00000008 | 0x00000200 | 0x08000000  # DETACHED_PROCESS | NEW_PROCESS_GROUP | NO_WINDOW
    else:
        kw["start_new_session"] = True
    subprocess.Popen(cmd, **kw)
    for _ in range(40):  # 最大 ~8 秒、起動を待つ
        time.sleep(0.2)
        st = running(root)
        if st:
            print(f"started\n  http://localhost:{st['port']}/index.html")
            return
    sys.exit("サーバーが起動しませんでした。前面で `serve.py <フォルダ>` を実行してエラーを確認してください")


def stop(root):
    st = running(root)
    if not st:
        print("not running")
    else:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(st["pid"]), "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            os.kill(st["pid"], 15)
        print("stopped")
    try:
        os.remove(state_path(root))
    except OSError:
        pass


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("folder")
    ap.add_argument("--port", type=int)
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--detach", action="store_true")
    g.add_argument("--stop", action="store_true")
    g.add_argument("--status", action="store_true")
    a = ap.parse_args()
    root = os.path.abspath(a.folder)
    if not os.path.isdir(root):
        sys.exit(f"フォルダがありません: {root}")
    if a.stop:
        stop(root)
    elif a.status:
        st = running(root)
        print(f"running\n  http://localhost:{st['port']}/index.html" if st else "not running")
    elif a.detach:
        detach(root, a.port)
    else:
        serve(root, a.port or default_port(root))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
