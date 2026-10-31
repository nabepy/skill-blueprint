#!/usr/bin/env python3
"""設計図フォルダをローカルで配信する(リアルタイム表示用)。

usage: python serve.py <blueprints/設計図名> [--port N]
  表示される URL(http://localhost:<ポート>/index.html)を開く。ポートは省略すると設計図フォルダごとに
  決まる(8700〜8899。別プロジェクトの設計図と取り違えないため)。ログ(logs/events.jsonl)と stats.json は
  ページが1秒ごとに読み直す。/api/analyze で事後解析を再実行できる。
  127.0.0.1 のみで待ち受ける。
"""
import functools, http.server, os, subprocess, sys, zlib

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    port = int(sys.argv[sys.argv.index("--port") + 1]) if "--port" in sys.argv else None
    if port is not None:
        args = [a for a in args if a != str(port)]
    if not args:
        sys.exit(__doc__)
    root = os.path.abspath(args[0])
    if port is None:
        # 設計図フォルダごとに別のポートにする(別プロジェクトの設計図と取り違えないため)。使用中なら次の番号。
        port = 8700 + zlib.crc32(root.lower().encode("utf-8")) % 200

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
    for p in range(port, port + 20):
        try:
            srv = http.server.ThreadingHTTPServer(("127.0.0.1", p), handler)
            break
        except OSError:
            continue
    else:
        sys.exit(f"ポート {port}〜{port + 19} が使用中です。--port で指定してください")
    print(f"serving {root}\n  http://localhost:{p}/index.html", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
