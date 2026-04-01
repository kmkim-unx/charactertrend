#!/usr/bin/env python3
"""
UNX Character Tracker 로컬 웹서버
python3 serve.py [--port 8080]
"""
import argparse
import webbrowser
import threading
import time
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
import os


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--no-open", action="store_true")
    args = parser.parse_args()

    output_dir = Path(__file__).parent / "output"
    output_dir.mkdir(exist_ok=True)

    dashboard = output_dir / "dashboard.html"
    if not dashboard.exists():
        print("dashboard.html이 없습니다. 먼저 python3 run_pipeline.py 를 실행하세요.")
        return

    os.chdir(output_dir)

    class Handler(SimpleHTTPRequestHandler):
        def log_message(self, format, *args):
            pass  # 로그 억제

    server = HTTPServer(("localhost", args.port), Handler)
    url = f"http://localhost:{args.port}/dashboard.html"
    print(f"UNX Tracker Dashboard: {url}")
    print("   종료: Ctrl+C")

    if not args.no_open:
        def open_browser():
            time.sleep(0.5)
            webbrowser.open(url)
        threading.Thread(target=open_browser, daemon=True).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n서버 종료")


if __name__ == "__main__":
    main()
