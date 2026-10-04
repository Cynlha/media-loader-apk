import os, re, json, time, uuid, shutil, threading, subprocess
from urllib.parse import urlparse, parse_qs, unquote
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn

PORT = 8080
SAVE_DIR = "/sdcard/Download/MediaLoader"
os.makedirs(SAVE_DIR, exist_ok=True)

TASKS = {}

class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    allow_reuse_address = True
    daemon_threads = True

def fmt_size(num):
    for unit in ["B", "KB", "MB", "GB"]:
        if num < 1024.0:
            return f"{num:.1f} {unit}"
        num /= 1024.0
    return f"{num:.1f} TB"

def download_worker(task_id, data):
    url = data.get("url", "").strip()
    fmt = data.get("format", "mp4")
    qual = data.get("quality", "best")
    custom_name = re.sub(r'[\\/*?:"<>|]', "", data.get("custom_name", "").strip())
    max_audio = data.get("max_audio", True)

    TASKS[task_id] = {"status": "running", "percent": 2, "step": "Получение данных..."}

    try:
        info_cmd = ["yt-dlp", "--dump-single-json", "--no-playlist", "--no-warnings", url]
        proc_info = subprocess.run(info_cmd, capture_output=True, text=True, timeout=35)
        title = "Media_" + str(int(time.time()))
        thumb = ""
        if proc_info.returncode == 0 and proc_info.stdout:
            try:
                info = json.loads(proc_info.stdout)
                title = info.get("title") or title
                thumb = info.get("thumbnail") or ""
            except Exception:
                pass

        safe_base = custom_name if custom_name else re.sub(r'[\\/*?:"<>|\n\r\t]', "_", title)[:70].strip()
        if not safe_base:
            safe_base = "Media_" + str(int(time.time()))

        ext = "mp3" if fmt == "mp3" else "mp4"
        final_name = f"{safe_base}_{int(time.time()) % 10000}.{ext}"
        out_path = os.path.join(SAVE_DIR, final_name)

        cmd = [
            "yt-dlp", "--newline", "--no-playlist", "--no-warnings",
            "--concurrent-fragments", "4"
        ]

        if fmt == "mp3":
            cmd += ["-x", "--audio-format", "mp3", "--audio-quality", "0" if max_audio else "5"]
        else:
            # Оригинальный поток без потери качества + совместимость с Android плеером
            if qual == "best":
                f_str = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best"
            else:
                f_str = f"bestvideo[height<={qual}][ext=mp4]+bestaudio[ext=m4a]/best[height<={qual}]/best"
            cmd += ["-f", f_str, "--merge-output-format", "mp4"]

        cmd += ["-o", out_path, url]

        TASKS[task_id]["step"] = "Загрузка в оригинальном качестве..."
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

        pct_re = re.compile(r"(\d+(?:\.\d+)?)%")
        for line in proc.stdout:
            m = pct_re.search(line)
            if m:
                p = float(m.group(1))
                TASKS[task_id]["percent"] = min(99, max(3, int(p)))
                TASKS[task_id]["step"] = f"Скачивание: {int(p)}%"
            elif "Merging" in line or "ExtractAudio" in line:
                TASKS[task_id]["step"] = "Сборка файла без потери качества..."

        proc.wait()

        if proc.returncode != 0 or not os.path.exists(out_path):
            raise RuntimeError("Не удалось скачать файл по этой ссылке")

        try:
            subprocess.Popen(["termux-media-scan", out_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass

        size_str = fmt_size(os.path.getsize(out_path))
        TASKS[task_id].update({
            "status": "done",
            "percent": 100,
            "step": "Готово!",
            "title": custom_name if custom_name else title,
            "saved_to": final_name,
            "filename": final_name,
            "size": size_str,
            "thumb": thumb
        })
    except Exception as e:
        TASKS[task_id] = {"status": "error", "error": str(e)}

class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        return

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Range")

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors()
        self.end_headers()

    def do_POST(self):
        if self.path.startswith("/download"):
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
            task_id = uuid.uuid4().hex[:10]
            threading.Thread(target=download_worker, args=(task_id, body), daemon=True).start()
            self.send_response(200)
            self._cors()
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": True, "task_id": task_id}).encode("utf-8"))
            return
        self.send_response(404)
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)

        if parsed.path == "/progress":
            tid = qs.get("id", [""])[0]
            info = TASKS.get(tid, {"status": "running", "percent": 0, "step": "Ожидание..."})
            self.send_response(200)
            self._cors()
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(info).encode("utf-8"))
            return

        if parsed.path == "/file":
            name = os.path.basename(unquote(qs.get("name", [""])[0]))
            fpath = os.path.join(SAVE_DIR, name)
            if not os.path.isfile(fpath):
                self.send_response(404)
                self._cors()
                self.end_headers()
                return

            fsize = os.path.getsize(fpath)
            ctype = "audio/mpeg" if name.lower().endswith(".mp3") else "video/mp4"
            range_hdr = self.headers.get("Range")

            if range_hdr:
                m = re.search(r"bytes=(\d+)-(\d*)", range_hdr)
                if m:
                    start = int(m.group(1))
                    end = int(m.group(2)) if m.group(2) else fsize - 1
                    end = min(end, fsize - 1)
                    length = end - start + 1
                    self.send_response(206)
                    self._cors()
                    self.send_header("Content-Type", ctype)
                    self.send_header("Accept-Ranges", "bytes")
                    self.send_header("Content-Range", f"bytes {start}-{end}/{fsize}")
                    self.send_header("Content-Length", str(length))
                    self.end_headers()
                    with open(fpath, "rb") as f:
                        f.seek(start)
                        self.wfile.write(f.read(length))
                    return

            self.send_response(200)
            self._cors()
            self.send_header("Content-Type", ctype)
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(fsize))
            self.end_headers()
            with open(fpath, "rb") as f:
                shutil.copyfileobj(f, self.wfile)
            return

        self.send_response(200)
        self._cors()
        self.end_headers()
        self.wfile.write(b"MediaLoader Server OK")

if __name__ == "__main__":
    print(f"Сервер Media Loader запущен на http://127.0.0.1:{PORT} :)")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
