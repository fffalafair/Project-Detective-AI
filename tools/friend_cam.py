"""
friend_cam.py — สตรีมกล้องเว็บแคมผ่านเครือข่าย (MJPEG over HTTP) สำหรับต่อเข้ากับ CCTV Dashboard
=============================================================================================

ใช้รันบนแล็ปท็อปของเพื่อน เพื่อแชร์ภาพกล้องผ่าน Tailscale ให้เครื่อง PC ดึงไปแสดงผลบน Dashboard

จุดเด่น:
- Zero Latency: แยก Thread ดึงเฟรมกล้องตลอดเวลา ภาพจึงสดใหม่เสมอ ไม่มีการสะสมดีเลย์
- Auto-Detect Tailscale: ค้นหา Tailscale IP (100.x.y.z) อัตโนมัติ พร้อมแสดง URL ให้ก็อปปี้ได้ทันที
- Web Preview: มีหน้าเว็บพรีวิวที่ http://<IP>:5001 ตรวจสอบภาพได้ทันทีในเบราว์เซอร์
- Thread-safe: รองรับการเปิดดูพร้อมกันหลายเครื่อง/หลายแท็บ
"""

import argparse
import socket
import subprocess
import sys
import threading
import time

import cv2
from flask import Flask, Response, render_template_string

app = Flask(__name__)

# ─── Frame Grabber Thread (Zero-Latency) ──────────────────────────────────────
class VideoCaptureThread:
    """อ่านเฟรมจากกล้องไว้ตลอดเวลา เพื่อไม่ให้ค้าง buffer ในไดรเวอร์ DirectShow/V4L2"""
    def __init__(self, cam_idx: int, width: int, height: int, fps: int):
        self.cam_idx = cam_idx
        self.width = width
        self.height = height
        self.fps = fps

        self.cap = None
        self.running = False
        self.lock = threading.Lock()
        self.latest_frame = None
        self.last_frame_time = 0.0
        self.thread = None

    def _open(self):
        backend = cv2.CAP_DSHOW if sys.platform.startswith("win") and hasattr(cv2, "CAP_DSHOW") else 0
        cap = cv2.VideoCapture(self.cam_idx, backend)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        cap.set(cv2.CAP_PROP_FPS, self.fps)
        try:
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        except Exception:
            pass
        return cap

    def start(self):
        self.cap = self._open()
        self.running = True
        self.thread = threading.Thread(target=self._worker, daemon=True)
        self.thread.start()

    def _worker(self):
        while self.running:
            if self.cap is None or not self.cap.isOpened():
                time.sleep(0.5)
                self.cap = self._open()
                continue

            ok, frame = self.cap.read()
            if not ok or frame is None:
                time.sleep(0.05)
                continue

            with self.lock:
                self.latest_frame = frame
                self.last_frame_time = time.time()

            time.sleep(0.005)

    def get_latest_frame(self):
        with self.lock:
            if self.latest_frame is None:
                return None
            return self.latest_frame.copy()

    def stop(self):
        self.running = False
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=1.0)
        if self.cap:
            self.cap.release()


capture: VideoCaptureThread | None = None
args: argparse.Namespace


def get_tailscale_ip() -> str:
    """พยายามค้นหา Tailscale IPv4 address (100.x.y.z)"""
    try:
        res = subprocess.run(
            ["tailscale", "ip", "-4"],
            capture_output=True,
            text=True,
            timeout=1.5,
            check=False
        )
        if res.returncode == 0:
            ip = res.stdout.strip()
            if ip.startswith("100."):
                return ip
    except Exception:
        pass

    try:
        host_name = socket.gethostname()
        for ip in socket.gethostbyname_ex(host_name)[2]:
            if ip.startswith("100."):
                return ip
    except Exception:
        pass

    return ""


def get_local_ip() -> str:
    """หา Local LAN IP กรณีไม่ได้ต่อ Tailscale"""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


def generate_mjpeg():
    """Generator ส่งภาพ MJPEG แบบ Low-latency"""
    global capture, args
    encode_params = [cv2.IMWRITE_JPEG_QUALITY, args.quality]
    interval = 1.0 / max(1, args.fps)

    while True:
        t0 = time.time()
        frame = capture.get_latest_frame() if capture else None

        if frame is None:
            time.sleep(0.05)
            continue

        ok, buf = cv2.imencode(".jpg", frame, encode_params)
        if not ok:
            continue

        yield (b"--frame\r\n"
               b"Content-Type: image/jpeg\r\n\r\n" + buf.tobytes() + b"\r\n")

        elapsed = time.time() - t0
        to_sleep = interval - elapsed
        if to_sleep > 0:
            time.sleep(to_sleep)


@app.route("/video")
def video():
    return Response(generate_mjpeg(),
                    mimetype="multipart/x-mixed-replace; boundary=frame")


PREVIEW_HTML = """
<!DOCTYPE html>
<html lang="th">
<head>
  <meta charset="UTF-8">
  <title>CCTV Friend Camera - Live</title>
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: #0f172a; color: #f8fafc;
      display: flex; flex-direction: column; align-items: center; justify-content: center;
      min-height: 100vh; padding: 20px;
    }
    .card {
      background: #1e293b; border-radius: 16px; border: 1px solid #334155;
      padding: 24px; width: 100%; max-width: 680px; box-shadow: 0 10px 25px rgba(0,0,0,0.5);
    }
    .header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px; }
    .title { font-size: 1.25rem; font-weight: 700; display: flex; align-items: center; gap: 8px; }
    .badge {
      background: #10b981; color: #022c22; font-size: 0.75rem; font-weight: bold;
      padding: 4px 10px; border-radius: 9999px;
    }
    .video-wrap {
      position: relative; width: 100%; background: #000;
      border-radius: 12px; overflow: hidden; margin-bottom: 20px;
      aspect-ratio: 16 / 9; display: flex; align-items: center; justify-content: center;
    }
    .video-wrap img { width: 100%; height: 100%; object-fit: contain; }
    .url-box {
      background: #090d16; border: 1px solid #334155; border-radius: 10px;
      padding: 12px 16px; display: flex; align-items: center; justify-content: space-between;
      gap: 12px; margin-bottom: 12px;
    }
    .url-text { font-family: monospace; font-size: 0.95rem; color: #38bdf8; word-break: break-all; }
    .copy-btn {
      background: #38bdf8; color: #0f172a; border: none; border-radius: 8px;
      padding: 8px 14px; font-weight: 600; cursor: pointer; white-space: nowrap;
      transition: background 0.2s;
    }
    .copy-btn:hover { background: #7dd3fc; }
    .instructions {
      font-size: 0.85rem; color: #94a3b8; line-height: 1.5;
    }
    .instructions b { color: #f1f5f9; }
  </style>
</head>
<body>
  <div class="card">
    <div class="header">
      <div class="title">🎥 CCTV Friend Camera Stream</div>
      <div class="badge">● ONLINE</div>
    </div>
    <div class="video-wrap">
      <img src="/video" alt="Camera Stream" />
    </div>
    <div class="url-box">
      <span class="url-text" id="streamUrl">{{ stream_url }}</span>
      <button class="copy-btn" onclick="copyUrl()">คัดลอก URL</button>
    </div>
    <div class="instructions">
      👉 <b>วิธีเชื่อมต่อไปยัง Dashboard:</b><br>
      1. คัดลอก URL ด้านบนนี้<br>
      2. ส่งให้เพื่อน หรือนำไปวางในหน้า Dashboard (ที่เมนู <b>Settings → กล้องระยะไกล</b> หรือกดปุ่ม <b>⚙</b> ที่ช่องกล้อง)<br>
      3. กด <b>เชื่อมต่อ</b> ภาพจากกล้องนี้จะขึ้นไปแสดงผลบน Dashboard ของเพื่อนทันที
    </div>
  </div>
  <script>
    function copyUrl() {
      const url = document.getElementById('streamUrl').innerText;
      navigator.clipboard.writeText(url).then(() => {
        alert('คัดลอก URL สำเร็จ:\\n' + url);
      });
    }
  </script>
</body>
</html>
"""


@app.route("/")
def index():
    ts_ip = get_tailscale_ip() or get_local_ip()
    stream_url = f"http://{ts_ip}:{args.port}/video"
    return render_template_string(PREVIEW_HTML, stream_url=stream_url)


def main():
    global capture, args
    p = argparse.ArgumentParser(description="แชร์กล้อง Laptop ผ่าน Tailscale/LAN (MJPEG Stream)")
    p.add_argument("--cam", type=int, default=0, help="ลำดับกล้องเว็บแคม (ค่าเริ่มต้น 0)")
    p.add_argument("--port", type=int, default=5001, help="พอร์ตที่ใช้เปิดบริการ (ค่าเริ่มต้น 5001)")
    p.add_argument("--width", type=int, default=960, help="ความกว้างภาพ (default 960)")
    p.add_argument("--height", type=int, default=540, help="ความสูงภาพ (default 540)")
    p.add_argument("--fps", type=int, default=24, help="FPS (default 24)")
    p.add_argument("--quality", type=int, default=65, help="คุณภาพ JPEG 1-100 (default 65)")
    args = p.parse_args()

    capture = VideoCaptureThread(
        cam_idx=args.cam,
        width=args.width,
        height=args.height,
        fps=args.fps
    )
    capture.start()

    ts_ip = get_tailscale_ip()
    local_ip = get_local_ip()

    print("\n" + "=" * 64)
    print("  🎥 CCTV Friend Camera Streamer กำลังทำงาน!")
    print("=" * 64)
    if ts_ip:
        print(f"  🌐 ตรวจพบ Tailscale IP: {ts_ip}")
        print("  👉 URL ที่ต้องนำไปใส่ใน Dashboard ของเครื่อง PC:")
        print(f"     http://{ts_ip}:{args.port}/video")
    else:
        print(f"  ℹ️ ไม่พบ Tailscale IP (กำลังใช้ Local LAN IP: {local_ip})")
        print(f"     http://{local_ip}:{args.port}/video")
    print("-" * 64)
    print(f"  🖥️ ดูพรีวิวภาพได้ที่: http://localhost:{args.port}")
    print("  ⛔ หากต้องการหยุด ให้กด Ctrl + C ในหน้าต่างนี้")
    print("=" * 64 + "\n")

    try:
        app.run(host="0.0.0.0", port=args.port, threaded=True)
    finally:
        if capture:
            capture.stop()


if __name__ == "__main__":
    main()
