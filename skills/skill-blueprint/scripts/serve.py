#!/usr/bin/env python3
"""設計図フォルダをローカルで配信する(リアルタイム表示用)。

usage: python serve.py <blueprints/設計図名> [--port 8765]
  http://localhost:8765/index.html を開く。ログ(logs/events.jsonl)と stats.json は
  ページが1秒ごとに読み直す。/api/analyze で事後解析を再実行できる。
  127.0.0.1 のみで待ち受ける。
"""
import functools, http.server, os, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    port = int(sys.argv[sys.argv.index("--port") + 1]) if "--port" in sys.argv else 8765
    if "--port" in sys.argv:
        args = [a for a in args if a != str(port)]
    if not args:
        sys.exit(__doc__)
    root = os.path.abspath(args[0])

    class H(http.server.SimpleHTTPRequestHandler):
        def end_headers(self):
            self.send_header("Cache-Control", "no-store")
            super().end_headers()

        def do_GET(self):
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
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
    print(f"serving {root} at http://localhost:{port}/index.html", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
