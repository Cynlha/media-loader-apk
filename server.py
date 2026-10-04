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

def ensure_h264_faststart(fpath, task_id=None):
    if not fpath.lower().endswith(".mp4") or not os.path.isfile(fpath):
        return
    try:
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=codec_name,pix_fmt", "-of", "json", fpath],
            capture_output=True, text=True, timeout=15
        )
        need_fix = False
        if probe.returncode == 0 and probe.stdout:
            data = json.loads(probe.stdout)
            streams = data.get("streams", [])
            if streams:
                codec = streams[0].get("codec_name", "")
                pix = streams[0].get("pix_fmt", "")
                if codec != "h264" or "10" in pix:
                    need_fix = True
        if need_fix:
            if task_id and task_id in TASKS:
                TASKS[task_id]["step"] = "Оптимизация кодека для плеера..."
            tmp_out = fpath + ".tmp.mp4"
            res = subprocess.run([
                "ffmpeg", "-y", "-i", fpath,
                "-c:v", "libx264", "-preset", "ultrafast", "-crf", "18",
                "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
                "-movflags", "+faststart", tmp_out
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if res.returncode == 0 and os.path.isfile(tmp_out):
                os.replace(tmp_out, fpath)
            elif os.path.exists(tmp_out):
                os.remove(tmp_out)
    except Exception:
        pass

def download_worker(task_id, data):
    url = data.get("url", "").strip()
    fmt = data.get("format", "mp4")
    qual = data.get("quality", "best")
    custom_name = re.sub(r'[^\w\s\-\.]', "", data.get("custom_name", "").strip())
    no_watermark = bool(data.get("no_watermark", True))

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

        raw_base = custom_name if custom_name else title
        safe_base = re.sub(r'[^\w\s\-]', "_", raw_base)[:55].strip("_ ")
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
            # Максимальный аудио-битрейт всегда по умолчанию (0)
            cmd += ["-x", "--audio-format", "mp3", "--audio-quality", "0"]
        else:
            # Управление водяным знаком (в TikTok download_addr = с водяным знаком, play_addr = без водяного знака)
            if no_watermark:
                if qual == "best":
                    f_str = "bestvideo[format_id!*=download][ext=mp4]+bestaudio[ext=m4a]/best[format_id!*=download]/bestvideo+bestaudio/best"
                else:
                    f_str = f"bestvideo[format_id!*=download][height<={qual}][ext=mp4]+bestaudio[ext=m4a]/best[format_id!*=download][height<={qual}]/best[height<={qual}]/best"
                cmd += ["-S", "res,fps,vcodec:h264,acodec:m4a"]
            else:
                if qual == "best":
                    f_str = "download_addr-0/best[format_id*=download]/bestvideo+bestaudio/best"
                else:
                    f_str = f"best[format_id*=download][height<={qual}]/best[height<={qual}]/best"

            cmd += [
                "-f", f_str,
                "--merge-output-format", "mp4",
                "--postprocessor-args", "Merger+ffmpeg_o1:-movflags +faststart"
            ]

        cmd += ["-o", out_path, url]

        TASKS[task_id]["step"] = "Загрузка без водяного знака..." if no_watermark else "Загрузка с водяным знаком..."
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

        pct_re = re.compile(r"(\d+(?:\.\d+)?)%")
        for line in proc.stdout:
            m = pct_re.search(line)
            if m:
                p = float(m.group(1))
                TASKS[task_id]["percent"] = min(98, max(3, int(p)))
                TASKS[task_id]["step"] = f"Скачивание: {int(p)}%"
            elif "Merging" in line or "ExtractAudio" in line:
                TASKS[task_id]["step"] = "Сборка файла..."

        proc.wait()

        if proc.returncode != 0 or not os.path.exists(out_path):
            raise RuntimeError("Не удалось скачать файл по этой ссылке")

        ensure_h264_faststart(out_path, task_id)

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

def resolve_media_path(req_name):
    if not req_name:
        return None
    exact = os.path.join(SAVE_DIR, os.path.basename(req_name))
    if os.path.isfile(exact):
        return exact
    prefix = os.path.basename(req_name).split("#")[0].strip()
    if prefix:
        for fn in os.listdir(SAVE_DIR):
            if fn.startswith(prefix):
                full = os.path.join(SAVE_DIR, fn)
                if os.path.isfile(full):
                    return full
    return None

class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, format, *args):
        return

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, HEAD, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Range")

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_HEAD(self):
        self.send_file_response(head_only=True)

    def do_POST(self):
        if self.path.startswith("/download"):
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
            task_id = uuid.uuid4().hex[:10]
            threading.Thread(target=download_worker, args=(task_id, body), daemon=True).start()
            payload = json.dumps({"ok": True, "task_id": task_id}).encode("utf-8")
            self.send_response(200)
            self._cors()
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        self.send_response(404)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def send_file_response(self, head_only=False):
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)
        raw_name = unquote(qs.get("name", [""])[0])
        fpath = resolve_media_path(raw_name)

        if not fpath or not os.path.isfile(fpath):
            self.send_response(404)
            self._cors()
            self.send_header("Content-Length", "0")
            self.end_headers()
            return

        fsize = os.path.getsize(fpath)
        ctype = "audio/mpeg" if fpath.lower().endswith(".mp3") else "video/mp4"
        range_hdr = self.headers.get("Range")

        start = 0
        end = fsize - 1
        status = 200

        if range_hdr:
            m = re.search(r"bytes=(\d+)-(\d*)", range_hdr)
            if m:
                start = int(m.group(1))
                if m.group(2):
                    end = min(int(m.group(2)), fsize - 1)
                status = 206

        if start >= fsize:
            self.send_response(416)
            self._cors()
            self.send_header("Content-Range", f"bytes */{fsize}")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return

        length = end - start + 1
        self.send_response(status)
        self._cors()
        self.send_header("Content-Type", ctype)
        self.send_header("Accept-Ranges", "bytes")
        if status == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{fsize}")
        self.send_header("Content-Length", str(length))
        self.end_headers()

        if head_only:
            return

        try:
            with open(fpath, "rb") as f:
                f.seek(start)
                rem = length
                while rem > 0:
                    chunk = f.read(min(65536, rem))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    rem -= len(chunk)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_GET(self):
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)

        if parsed.path == "/progress":
            tid = qs.get("id", [""])[0]
            info = TASKS.get(tid, {"status": "running", "percent": 0, "step": "Ожидание..."})
            payload = json.dumps(info).encode("utf-8")
            self.send_response(200)
            self._cors()
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return

        if parsed.path == "/file":
            self.send_file_response(head_only=False)
            return

        self.send_response(200)
        self._cors()
        self.send_header("Content-Length", "2")
        self.end_headers()
        self.wfile.write(b"OK")

if __name__ == "__main__":
    print(f"Сервер Media Loader 0.11 BETA запущен на http://127.0.0.1:{PORT} :)")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
