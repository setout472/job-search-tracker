"""本机求职跟踪表：只监听 127.0.0.1，岗位数据与个人标记分开保存。"""

from __future__ import annotations

import argparse
import json
import os
import tempfile
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parent
ALLOWED_STATUS = {
    "jobs": {"", "待投", "准备中", "已投", "笔试", "面试", "暂缓", "结束"},
    "fairs": {"", "待查看", "计划参加", "已报名", "已参加", "不参加"},
}
FILES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/style.css": ("style.css", "text/css; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
}


class Store:
    def __init__(self, directory: Path):
        self.directory = Path(directory)
        self.data_path = self.directory / "data.json"
        self.marks_path = self.directory / "marks.json"
        self.lock = threading.RLock()

    def read_data(self):
        with self.lock:
            return json.loads(self.data_path.read_text(encoding="utf-8"))

    def read_marks(self):
        with self.lock:
            if not self.marks_path.exists():
                return {"jobs": {}, "fairs": {}}
            marks = json.loads(self.marks_path.read_text(encoding="utf-8"))
            return {"jobs": marks.get("jobs", {}), "fairs": marks.get("fairs", {})}

    def save_mark(self, payload):
        kind = payload.get("kind")
        item_id = payload.get("id")
        status = payload.get("status", "")
        note = payload.get("note", "")
        if kind not in ALLOWED_STATUS or not isinstance(item_id, str):
            raise ValueError("类别或编号无效")
        if status not in ALLOWED_STATUS[kind]:
            raise ValueError("状态无效")
        if not isinstance(note, str) or len(note) > 500:
            raise ValueError("备注不能超过 500 字")
        with self.lock:
            data = self.read_data()
            if item_id not in {item["id"] for item in data[kind]}:
                raise ValueError("找不到这条记录")
            marks = self.read_marks()
            marks[kind][item_id] = {"status": status, "note": note}
            self._atomic_write(self.marks_path, marks)
            return marks[kind][item_id]

    @staticmethod
    def _atomic_write(path: Path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=".marks-", suffix=".json", dir=path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(data, stream, ensure_ascii=False, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(tmp, path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)


def create_server(port=8765, directory=ROOT):
    store = Store(directory)

    class LocalServer(ThreadingHTTPServer):
        allow_reuse_address = False

    class Handler(BaseHTTPRequestHandler):
        def _json(self, status, value):
            body = json.dumps(value, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            path = urlparse(self.path).path
            if path == "/health":
                return self._json(200, {"ok": True, "app": "shanghai-job-tracker"})
            if path == "/api/state":
                try:
                    return self._json(200, {"data": store.read_data(), "marks": store.read_marks()})
                except (OSError, ValueError, KeyError) as exc:
                    return self._json(500, {"error": str(exc)})
            if path not in FILES:
                return self._json(404, {"error": "页面不存在"})
            name, content_type = FILES[path]
            try:
                body = (Path(directory) / name).read_bytes()
            except OSError:
                return self._json(404, {"error": "文件不存在"})
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            if urlparse(self.path).path != "/api/mark":
                return self._json(404, {"error": "接口不存在"})
            origin = self.headers.get("Origin")
            if origin and origin != f"http://127.0.0.1:{self.server.server_port}":
                return self._json(403, {"error": "仅接受本机页面写入"})
            if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                return self._json(415, {"error": "请使用 JSON"})
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 8192:
                    raise ValueError("请求长度无效")
                payload = json.loads(self.rfile.read(length))
                result = store.save_mark(payload)
            except (ValueError, json.JSONDecodeError) as exc:
                return self._json(400, {"error": str(exc)})
            except OSError as exc:
                return self._json(500, {"error": str(exc)})
            return self._json(200, {"saved": result})

        def log_message(self, format, *args):
            print("%s - %s" % (self.address_string(), format % args))

    return LocalServer(("127.0.0.1", port), Handler)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    url = f"http://127.0.0.1:{args.port}/"
    try:
        with urlopen(url + "health", timeout=1) as response:
            health = json.load(response)
            already_running = health.get("ok") is True and health.get("app") == "shanghai-job-tracker"
    except (OSError, ValueError):
        already_running = False
    if already_running:
        print(f"求职表已在运行：{url}", flush=True)
        if not args.no_browser:
            webbrowser.open(url)
        return
    try:
        server = create_server(args.port)
    except OSError as exc:
        try:
            with urlopen(url + "health", timeout=1) as response:
                health = json.load(response)
                already_running = health.get("ok") is True and health.get("app") == "shanghai-job-tracker"
        except (OSError, ValueError):
            already_running = False
        if not already_running:
            raise SystemExit(f"{args.port} 端口已被其他程序占用：{exc}")
        print(f"求职表已在运行：{url}", flush=True)
        if not args.no_browser:
            webbrowser.open(url)
        return
    print(f"求职表已启动：{url}", flush=True)
    print("关闭此窗口会停止本地网页；个人标记保存在 marks.json。", flush=True)
    if not args.no_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
