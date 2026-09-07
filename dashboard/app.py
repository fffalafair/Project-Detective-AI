import os
import re
import glob
import time
import threading
import queue
import json
import base64
from datetime import datetime
from collections import deque
from pathlib import Path

_APP_DIR  = Path(__file__).resolve().parent   # …/dashboard
_REPO_DIR = _APP_DIR.parent                    # repo root (has runs/, yolo11s.pt)

import cv2
import numpy as np
import torch
from flask import Flask, render_template, Response, request, jsonify
from ultralytics import YOLO

app = Flask(__name__)

# ─── Config ───────────────────────────────────────────────────────────────────
MODEL_PATH = os.environ.get("MODEL_PATH", "")
CONF_THRESHOLD = float(os.environ.get("CONF_THRESHOLD", "0.4"))

# Inference device.  YOLO_DEVICE overrides (e.g. "cpu", "0", "0,1"); otherwise
# use the GPU when a CUDA build of torch can see one, else fall back to CPU.
YOLO_DEVICE = os.environ.get("YOLO_DEVICE", "").strip() or \
    (0 if torch.cuda.is_available() else "cpu")

# RTSP / network-stream tuning for the OpenCV FFMPEG backend.
# rtsp_transport=tcp  → survives lossy / NAT'd links (e.g. a friend's cam over Tailscale)
# *timeout in microseconds → don't hang forever when the peer disappears
RTSP_TRANSPORT = os.environ.get("RTSP_TRANSPORT", "tcp")
os.environ.setdefault(
    "OPENCV_FFMPEG_CAPTURE_OPTIONS",
    f"rtsp_transport;{RTSP_TRANSPORT}|stimeout;5000000|max_delay;500000|reorder_queue_size;0",
)

CLASS_NAMES = {
    0: "Helmet", 1: "Gloves", 2: "Vest", 3: "Boots",
    4: "Goggles", 5: "none", 6: "Person",
    7: "no_helmet", 8: "no_goggle", 9: "no_gloves", 10: "no_boots"
}

# Green for safe PPE, Red for violations, Blue for person, Gray for others
CLASS_COLORS = {
    0: (0, 220, 100),   # Helmet      – green
    1: (0, 220, 100),   # Gloves      – green
    2: (0, 220, 100),   # Vest        – green
    3: (0, 220, 100),   # Boots       – green
    4: (0, 220, 100),   # Goggles     – green
    5: (150, 150, 150), # none        – gray
    6: (255, 200, 0),   # Person      – yellow
    7: (0, 0, 230),     # no_helmet   – red
    8: (0, 0, 230),     # no_goggle   – red
    9: (0, 0, 230),     # no_gloves   – red
    10: (0, 0, 230),    # no_boots    – red
}

VIOLATION_IDS = {7, 8, 9, 10}
SAFE_PPE_IDS  = {0, 1, 2, 3, 4}

# ─── Global state ─────────────────────────────────────────────────────────────
model: YOLO | None = None
model_lock = threading.Lock()

# Stream state per camera slot
streams: dict[str, dict] = {}   # key = cam_id ("cam0", "cam1", …)
stream_lock = threading.Lock()

# Rolling stats ring-buffer (last 100 detections)
stats_buffer: deque = deque(maxlen=300)
stats_lock = threading.Lock()

alert_queue: queue.Queue = queue.Queue(maxsize=50)

# Alert de-bounce: fire an alert only when the violation set changes, when the
# same violation has been up past ALERT_COOLDOWN_SEC, or when it reappears after
# being gone for at least ALERT_CLEAR_GRACE_SEC.  Stops a person standing
# without a helmet from spamming ~30 alerts/sec, while ignoring 1-2 frame
# detection flicker.
ALERT_COOLDOWN_SEC    = float(os.environ.get("ALERT_COOLDOWN_SEC", "20"))
ALERT_CLEAR_GRACE_SEC = float(os.environ.get("ALERT_CLEAR_GRACE_SEC", "4"))
_alert_state = {"key": "", "ts": 0.0, "gone_since": 0.0}

# ─── Persistence (survives restarts) ─────────────────────────────────────────
# DATA_DIR is a bind-mounted folder in docker-compose (./outputs) so these
# files persist even when the container is recreated.
DATA_DIR      = os.environ.get("DATA_DIR", "outputs")
CAM_CFG_FILE  = os.path.join(DATA_DIR, "cameras.json")
EVENTS_FILE   = os.path.join(DATA_DIR, "events.jsonl")
EVENTS_MAX_BYTES = int(os.environ.get("EVENTS_MAX_BYTES", str(5 * 1024 * 1024)))
os.makedirs(DATA_DIR, exist_ok=True)

_cfg_lock    = threading.Lock()
_events_lock = threading.Lock()


def cam_cfg_load() -> dict:
    try:
        with open(CAM_CFG_FILE, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {}


def cam_cfg_save(cfg: dict) -> None:
    with _cfg_lock:
        try:
            with open(CAM_CFG_FILE, "w", encoding="utf-8") as fh:
                json.dump(cfg, fh, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[warn] cannot write {CAM_CFG_FILE}: {e}")


def cam_cfg_update(cam_id: str, source, label: str) -> None:
    cfg = cam_cfg_load()
    cfg[cam_id] = {"source": str(source), "label": label}
    cam_cfg_save(cfg)


def cam_cfg_remove(cam_id: str) -> None:
    cfg = cam_cfg_load()
    if cfg.pop(cam_id, None) is not None:
        cam_cfg_save(cfg)


def _rotate_events_if_big() -> None:
    """Keep events.jsonl bounded: when it passes the cap, move it to .1
    (dropping any older .1) so the file never grows without limit."""
    try:
        if os.path.getsize(EVENTS_FILE) <= EVENTS_MAX_BYTES:
            return
    except OSError:
        return
    bak = EVENTS_FILE + ".1"
    try:
        if os.path.exists(bak):
            os.remove(bak)
        os.replace(EVENTS_FILE, bak)
    except OSError:
        pass


def log_event(kind: str, **data) -> None:
    """Append one JSON line to events.jsonl (kind = 'gate' | 'alert' | …)."""
    rec = {"ts": datetime.now().isoformat(), "kind": kind, **data}
    with _events_lock:
        try:
            _rotate_events_if_big()
            with open(EVENTS_FILE, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        except Exception as e:
            print(f"[warn] cannot write {EVENTS_FILE}: {e}")


def events_tail(n: int = 100, kind: str = "") -> list:
    lines: list[str] = []
    for fp in (EVENTS_FILE + ".1", EVENTS_FILE):     # older half first
        try:
            with open(fp, encoding="utf-8") as fh:
                lines.extend(fh.readlines())
        except Exception:
            pass
    out = []
    for ln in lines[-4000:]:
        try:
            rec = json.loads(ln)
        except Exception:
            continue
        if not kind or rec.get("kind") == kind:
            out.append(rec)
    return out[-n:]


# ─── Barrier gate (ไม้กั้น) — open/closed status + board link ─────────────────
# BOARD_URL: base URL of the microcontroller (ESP32) that will drive the real
# barrier's servo/relay. Leave blank to run the card as a dashboard-only mock.
BOARD_URL = os.environ.get("ESP32_URL", os.environ.get("BOARD_URL", "")).rstrip("/")

gate_lock = threading.Lock()
gate_state: dict = {
    "status":     "closed",   # "open" | "closed"
    "board":      "n/a",      # "online" | "offline" | "n/a"
    "changed_at": None,       # ISO time of last status change
}


def _gate_snapshot_locked() -> dict:
    """Serializable view of the gate. Caller MUST hold gate_lock."""
    g = gate_state
    return {"status": g["status"], "board": g["board"], "changed_at": g["changed_at"]}


def _board_send(action: str) -> None:
    """Signal the barrier board (open / close) and refresh the link indicator.
    No-op (board = 'n/a') when BOARD_URL is not configured."""
    if not BOARD_URL:
        with gate_lock:
            gate_state["board"] = "n/a"
        return
    try:
        import urllib.request
        urllib.request.urlopen(f"{BOARD_URL}/{action}", timeout=1.5)
        ok = True
    except Exception:
        ok = False
    with gate_lock:
        gate_state["board"] = "online" if ok else "offline"


def _set_gate(status: str) -> dict:
    """Set the gate open/closed, tell the board, return a fresh snapshot."""
    with gate_lock:
        gate_state["status"]     = status
        gate_state["changed_at"] = datetime.now().isoformat()
        snap = _gate_snapshot_locked()
    log_event("gate", status=status, board=snap["board"])
    threading.Thread(target=_board_send,
                     args=("open" if status == "open" else "close",),
                     daemon=True).start()
    return snap


def _board_monitor() -> None:
    """Keep the board link indicator fresh so the card shows a live
    'connected / not connected' state even when no button is pressed."""
    if not BOARD_URL:
        return
    import urllib.request
    while True:
        try:
            urllib.request.urlopen(f"{BOARD_URL}/", timeout=1.5)
            state = "online"
        except Exception:
            state = "offline"
        with gate_lock:
            gate_state["board"] = state
        time.sleep(10)


threading.Thread(target=_board_monitor, daemon=True).start()


# ─── Model helpers ────────────────────────────────────────────────────────────
def _weight_search_bases() -> list[Path]:
    # look in cwd, the dashboard dir, and the repo root – so it works whether
    # you run `python app.py` from dashboard/, from the repo root, or in Docker
    seen, bases = set(), []
    for b in (Path.cwd(), _APP_DIR, _REPO_DIR):
        b = b.resolve()
        if b not in seen:
            seen.add(b)
            bases.append(b)
    return bases


def find_best_weights() -> str:
    rel_patterns = [
        "runs/detect/industrial_safety_yolo/yolo11s_safety_boots*/weights/best.pt",
        "runs/detect/**/weights/best.pt",
    ]
    candidates = []
    for base in _weight_search_bases():
        for pat in rel_patterns:
            candidates.extend(glob.glob(str(base / pat), recursive=True))
    if candidates:
        return max(candidates, key=os.path.getmtime)
    # fall back to a base yolo11s.pt on disk if there is one
    for base in _weight_search_bases():
        if (base / "yolo11s.pt").exists():
            return str(base / "yolo11s.pt")
    return "yolo11s.pt"     # let ultralytics auto-download as a last resort


def load_model(path: str = "") -> tuple[bool, str]:
    global model
    path = path or MODEL_PATH or find_best_weights()
    if not os.path.exists(path):
        for base in _weight_search_bases():
            if (base / "yolo11s.pt").exists():
                path = str(base / "yolo11s.pt")
                break
        else:
            path = "yolo11s.pt"
    try:
        with model_lock:
            model = YOLO(path)
        return True, path
    except Exception as e:
        return False, str(e)


def _startup_load() -> None:
    """Load the model once at process start.

    Runs for BOTH `python app.py` and gunicorn (`app:app`) – the old code only
    loaded inside ``if __name__ == "__main__"`` so under Docker/gunicorn the
    model stayed unloaded until someone hit the Settings button.
    """
    dev = f"cuda:{YOLO_DEVICE} ({torch.cuda.get_device_name(0)})" \
        if torch.cuda.is_available() and YOLO_DEVICE != "cpu" else "cpu"
    print(f"[*] Loading model at startup… (device: {dev})")
    ok, msg = load_model()
    print(f"[{'OK' if ok else 'WARN'}] model: {msg}")


threading.Thread(target=_startup_load, daemon=True).start()


# ─── Frame processing ─────────────────────────────────────────────────────────
def process_frame(frame: np.ndarray) -> tuple[np.ndarray, dict]:
    if model is None:
        return frame, {}

    with model_lock:
        results = model(frame, conf=CONF_THRESHOLD, device=YOLO_DEVICE, verbose=False)

    counts = {name: 0 for name in CLASS_NAMES.values()}
    violations = 0
    safe_ppe = 0
    annotated = frame.copy()

    for result in results:
        for box in result.boxes:
            cls_id = int(box.cls[0])
            conf   = float(box.conf[0])
            x1, y1, x2, y2 = map(int, box.xyxy[0].cpu().numpy())

            name  = CLASS_NAMES.get(cls_id, f"cls{cls_id}")
            color = CLASS_COLORS.get(cls_id, (180, 180, 180))
            thick = 3 if cls_id in VIOLATION_IDS else 2

            # Box
            cv2.rectangle(annotated, (x1, y1), (x2, y2), color, thick)
            # Label background
            label = f"{name} {conf:.2f}"
            (lw, lh), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 1)
            cv2.rectangle(annotated, (x1, y1 - lh - 8), (x1 + lw + 4, y1), color, -1)
            cv2.putText(annotated, label, (x1 + 2, y1 - 4),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1)

            counts[name] = counts.get(name, 0) + 1
            if cls_id in VIOLATION_IDS:
                violations += 1
            elif cls_id in SAFE_PPE_IDS:
                safe_ppe += 1

    # ── PPE per-item status (ok = detected & no violation counterpart) ──────────
    ppe_status = {
        "helmet": {
            "ok":    counts.get("Helmet", 0) > 0,
            "fail":  counts.get("no_helmet", 0) > 0,
            "count": counts.get("Helmet", 0),
            "fail_count": counts.get("no_helmet", 0),
        },
        "boots": {
            "ok":    counts.get("Boots", 0) > 0,
            "fail":  counts.get("no_boots", 0) > 0,
            "count": counts.get("Boots", 0),
            "fail_count": counts.get("no_boots", 0),
        },
        "gloves": {
            "ok":    counts.get("Gloves", 0) > 0,
            "fail":  counts.get("no_gloves", 0) > 0,
            "count": counts.get("Gloves", 0),
            "fail_count": counts.get("no_gloves", 0),
        },
        "vest": {
            "ok":    counts.get("Vest", 0) > 0,
            "fail":  False,
            "count": counts.get("Vest", 0),
            "fail_count": 0,
        },
        "goggles": {
            "ok":    counts.get("Goggles", 0) > 0,
            "fail":  counts.get("no_goggle", 0) > 0,
            "count": counts.get("Goggles", 0),
            "fail_count": counts.get("no_goggle", 0),
        },
    }
    # overall PPE ok = someone detected AND zero violations
    ppe_status["overall"] = {
        "ok":   violations == 0 and safe_ppe > 0,
        "fail": violations > 0,
    }

    # ── Violation summary (shared by alerts + gate reason) ────────────────────
    viol_msgs = []
    if counts.get("no_helmet", 0):
        viol_msgs.append(f"ไม่สวม Helmet {counts['no_helmet']} คน")
    if counts.get("no_boots", 0):
        viol_msgs.append(f"ไม่สวม Boots {counts['no_boots']} คน")
    if counts.get("no_gloves", 0):
        viol_msgs.append(f"ไม่สวม Gloves {counts['no_gloves']} คน")
    if counts.get("no_goggle", 0):
        viol_msgs.append(f"ไม่สวม Goggles {counts['no_goggle']} คน")
    # ── Barrier gate (ไม้กั้น) — status snapshot only ───────────────────────
    with gate_lock:
        gate_snapshot = _gate_snapshot_locked()

    stat = {
        "timestamp":  datetime.now().isoformat(),
        "counts":     counts,
        "violations": violations,
        "safe_ppe":   safe_ppe,
        "persons":    counts.get("Person", 0),
        "ppe_status": ppe_status,
        "gate":       gate_snapshot,
    }

    with stats_lock:
        stats_buffer.append(stat)

    # ── Alerts (de-bounced) ─────────────────────────────────────────────────
    now = time.time()
    if violations > 0:
        key = ",".join(viol_msgs) or f"v{violations}"
        back_after_gap = (_alert_state["gone_since"] > 0.0
                          and now - _alert_state["gone_since"] > ALERT_CLEAR_GRACE_SEC)
        _alert_state["gone_since"] = 0.0
        fire = (key != _alert_state["key"]
                or back_after_gap
                or now - _alert_state["ts"] > ALERT_COOLDOWN_SEC)
        if fire:
            _alert_state["key"] = key
            _alert_state["ts"]  = now
            alert_msg = "⚠ " + ", ".join(viol_msgs) if viol_msgs else \
                f"⚠ PPE violations {violations} รายการ"
            try:
                alert_queue.put_nowait({
                    "time":  datetime.now().strftime("%H:%M:%S"),
                    "msg":   alert_msg,
                    "level": "danger",
                })
            except queue.Full:
                pass
            log_event("alert", msg=alert_msg, violations=violations)
    elif _alert_state["gone_since"] == 0.0:
        _alert_state["gone_since"] = now   # start of a violations-clear streak

    return annotated, stat


# ─── Camera stream worker ──────────────────────────────────────────────────────
def _is_network_source(source) -> bool:
    return isinstance(source, str) and source.split("://", 1)[0].lower() in (
        "rtsp", "rtsps", "http", "https", "rtmp", "udp", "tcp"
    )


_YT_RE = re.compile(r"(?:youtube\.com/|youtu\.be/|youtube-nocookie\.com/)", re.I)
_yt_cache: dict = {}                 # original url -> (resolved_at, direct_url)
_yt_lock = threading.Lock()


def _is_youtube(source) -> bool:
    return isinstance(source, str) and _YT_RE.search(source) is not None


def _resolve_youtube(url: str) -> str:
    """Turn a YouTube page URL into a direct media URL that ffmpeg can open.
    Cached ~50 min (googlevideo URLs expire in a few hours)."""
    now = time.time()
    with _yt_lock:
        hit = _yt_cache.get(url)
        if hit and now - hit[0] < 3000:
            return hit[1]
    try:
        import yt_dlp
    except ImportError:
        raise RuntimeError("ยังไม่ได้ติดตั้ง yt-dlp  (pip install yt-dlp)")

    opts = {
        "quiet": True, "no_warnings": True, "skip_download": True,
        # video-only H.264 ≤720p is the most ffmpeg/OpenCV-friendly; fall back down
        "format": "bestvideo[height<=?720][vcodec^=avc1]/best[height<=?720]/best",
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    direct = info.get("url")
    if not direct and info.get("formats"):
        direct = info["formats"][-1].get("url")
    if not direct:
        raise RuntimeError("yt-dlp หา stream URL ไม่เจอ")
    with _yt_lock:
        _yt_cache[url] = (now, direct)
    return direct


def open_source(source) -> "cv2.VideoCapture":
    """Open a webcam index or a network URL (RTSP / HTTP / YouTube) with sane
    defaults.  Network streams use the FFMPEG backend + a tiny buffer so the
    dashboard shows near-live frames instead of a growing delay."""
    if _is_youtube(source):
        try:
            source = _resolve_youtube(source)
        except Exception as e:
            print(f"[warn] YouTube resolve failed: {e}")
            return cv2.VideoCapture()          # not opened → caller retries
    if _is_network_source(source):
        cap = cv2.VideoCapture(source, cv2.CAP_FFMPEG)
        try:
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        except Exception:
            pass
        return cap
    return cv2.VideoCapture(source)


def probe_source(source, read_frames: int = 5) -> dict:
    """Try to open a source and grab a frame. Returns {ok, width, height, message}."""
    if isinstance(source, str) and source.isdigit():
        source = int(source)
    if _is_youtube(source):
        try:
            _resolve_youtube(source)          # surface a clear yt-dlp error
        except Exception as e:
            return {"ok": False, "message": f"YouTube: {e}"}
    cap = open_source(source)
    try:
        if not cap.isOpened():
            return {"ok": False, "message": "เปิดสตรีมไม่ได้ (ตรวจ URL / เครือข่าย / firewall)"}
        frame = None
        for _ in range(read_frames):
            ok, frame = cap.read()
            if ok and frame is not None:
                break
        if frame is None:
            return {"ok": False, "message": "เชื่อมต่อได้แต่ไม่มีเฟรมภาพส่งมา"}
        h, w = frame.shape[:2]
        return {"ok": True, "width": int(w), "height": int(h),
                "message": f"เชื่อมต่อสำเร็จ · {w}×{h}"}
    finally:
        cap.release()


def camera_worker(cam_id: str, source, state: dict):
    """Runs in a thread; keeps reading frames into ``state`` (this worker's own
    slot entry).  As soon as ``state`` is no longer the current entry for
    ``cam_id`` – i.e. a newer source was started – this worker exits and stops
    touching the slot, so switching sources never leaves two workers running.
    """
    def _superseded() -> bool:
        with stream_lock:
            return bool(state.get("stop")) or streams.get(cam_id) is not state

    def _set_status(val: str) -> None:
        with stream_lock:
            if streams.get(cam_id) is state:
                state["status"] = val

    # Keep trying the first open – a restored / just-added RTSP/YouTube cam that
    # is momentarily offline must not kill the worker for good.
    cap = open_source(source)
    open_tries = 0
    while not cap.isOpened():
        if _superseded():
            _set_status("stopped")
            cap.release()
            return
        open_tries += 1
        _set_status("connecting" if open_tries < 3 else "reconnecting")
        cap.release()
        time.sleep(2)
        cap = open_source(source)

    _set_status("running")

    fail_reads = 0
    while not _superseded():
        ret, frame = cap.read()
        if not ret:
            # Drop a few frames before declaring the link dead, then reconnect
            fail_reads += 1
            if fail_reads < 15:
                time.sleep(0.05)
                continue
            fail_reads = 0
            _set_status("reconnecting")
            cap.release()
            time.sleep(1)
            cap = open_source(source)
            _set_status("running" if cap.isOpened() else "reconnecting")
            continue
        fail_reads = 0

        annotated, stat = process_frame(frame)

        _, buf = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 80])
        jpeg_bytes = buf.tobytes()

        with stream_lock:
            if streams.get(cam_id) is not state:
                break
            state["frame"] = jpeg_bytes
            state["stat"]  = stat

    cap.release()
    _set_status("stopped")


def gen_frames(cam_id: str):
    """MJPEG generator for a given camera slot."""
    while True:
        with stream_lock:
            info = streams.get(cam_id, {})
            frame_bytes = info.get("frame")

        if frame_bytes:
            yield (b"--frame\r\n"
                   b"Content-Type: image/jpeg\r\n\r\n" + frame_bytes + b"\r\n")
        time.sleep(0.03)  # ~33 fps cap


def _restore_cameras() -> None:
    """Re-open the cameras that were running before the last restart."""
    cfg = cam_cfg_load()
    for cam_id, c in cfg.items():
        source = c.get("source", "0")
        label  = c.get("label", "")
        if isinstance(source, str) and source.isdigit():
            source = int(source)
        with stream_lock:
            state = {"frame": None, "stat": {}, "status": "starting",
                     "stop": False, "label": label, "source": str(source)}
            streams[cam_id] = state
        threading.Thread(target=camera_worker, args=(cam_id, source, state),
                         daemon=True).start()
        print(f"[*] restored camera {cam_id} → {source}")


threading.Thread(target=_restore_cameras, daemon=True).start()


# ─── Routes ───────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/model/load", methods=["POST"])
def api_load_model():
    data = request.get_json(silent=True) or {}
    ok, msg = load_model(data.get("path", ""))
    return jsonify({"ok": ok, "message": msg})


@app.route("/api/model/status")
def api_model_status():
    return jsonify({"loaded": model is not None,
                    "path": getattr(model, "ckpt_path", "") if model else "",
                    "conf": CONF_THRESHOLD})


@app.route("/api/model/conf", methods=["POST"])
def api_model_conf():
    """Live-adjust the detection confidence threshold (Settings slider)."""
    global CONF_THRESHOLD
    data = request.get_json(silent=True) or {}
    try:
        val = float(data.get("conf"))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "message": "conf ต้องเป็นตัวเลข"}), 400
    CONF_THRESHOLD = max(0.05, min(0.95, round(val, 2)))
    return jsonify({"ok": True, "conf": CONF_THRESHOLD})


@app.route("/api/camera/start", methods=["POST"])
def api_camera_start():
    data   = request.get_json(silent=True) or {}
    source = data.get("source", 0)        # 0 = webcam, or rtsp://… / http://… URL
    cam_id = data.get("cam_id", "cam0")
    label  = (data.get("label") or "").strip()

    # Convert numeric string
    if isinstance(source, str) and source.isdigit():
        source = int(source)

    with stream_lock:
        # Tell any worker already on this slot to quit, then install a fresh
        # entry.  The old worker sees it is no longer streams[cam_id] and exits.
        if cam_id in streams:
            streams[cam_id]["stop"] = True
        state = {"frame": None, "stat": {}, "status": "starting",
                 "stop": False, "label": label, "source": str(source)}
        streams[cam_id] = state

    threading.Thread(target=camera_worker, args=(cam_id, source, state),
                     daemon=True).start()

    cam_cfg_update(cam_id, source, label)   # remember it for next restart
    return jsonify({"ok": True, "cam_id": cam_id})


@app.route("/api/camera/test", methods=["POST"])
def api_camera_test():
    """Quick one-shot check of an RTSP/HTTP URL (or webcam index) before wiring
    it into a camera slot – returns resolution or a human-readable error."""
    data   = request.get_json(silent=True) or {}
    source = data.get("source", 0)
    return jsonify(probe_source(source))


@app.route("/api/camera/stop", methods=["POST"])
def api_camera_stop():
    data   = request.get_json(silent=True) or {}
    cam_id = data.get("cam_id", "cam0")
    with stream_lock:
        if cam_id in streams:
            streams[cam_id]["stop"] = True
    cam_cfg_remove(cam_id)                  # don't auto-restore it next time
    return jsonify({"ok": True})


@app.route("/api/camera/status")
def api_camera_status():
    with stream_lock:
        cams = {k: {"status": v.get("status", "unknown"),
                    "label":  v.get("label", ""),
                    "source": v.get("source", "")}
                for k, v in streams.items()}
    return jsonify({"ok": True, "cams": cams})


# ─── Barrier gate routes ──────────────────────────────────────────────────────
@app.route("/api/gate/status")
def api_gate_status():
    with gate_lock:
        snap = _gate_snapshot_locked()
    return jsonify({"ok": True, "gate": snap})


@app.route("/api/gate/open", methods=["POST"])
def api_gate_open():
    return jsonify({"ok": True, "gate": _set_gate("open")})


@app.route("/api/gate/close", methods=["POST"])
def api_gate_close():
    return jsonify({"ok": True, "gate": _set_gate("closed")})


@app.route("/video_feed/<cam_id>")
def video_feed(cam_id):
    return Response(gen_frames(cam_id),
                    mimetype="multipart/x-mixed-replace; boundary=frame")


@app.route("/api/stats/latest")
def api_stats_latest():
    with stats_lock:
        if not stats_buffer:
            return jsonify({"ok": False})
        latest = stats_buffer[-1]
    return jsonify({"ok": True, "data": latest})


@app.route("/api/stats/history")
def api_stats_history():
    n = int(request.args.get("n", 60))
    with stats_lock:
        data = list(stats_buffer)[-n:]
    return jsonify({"ok": True, "data": data})


@app.route("/api/events")
def api_events():
    """Persisted event log (kind = 'gate' | 'alert')  – survives restarts."""
    n    = int(request.args.get("n", 100))
    kind = request.args.get("kind", "")
    return jsonify({"ok": True, "events": events_tail(n, kind)})


@app.route("/api/alerts/stream")
def api_alerts_stream():
    """Server-Sent Events endpoint for real-time alerts."""
    def event_stream():
        while True:
            try:
                alert = alert_queue.get(timeout=20)
                yield f"data: {json.dumps(alert, ensure_ascii=False)}\n\n"
            except queue.Empty:
                yield "data: {\"ping\": true}\n\n"

    return Response(event_stream(), mimetype="text/event-stream")


@app.route("/api/stats/stream")
def api_stats_stream():
    """Server-Sent Events – pushes a new stat payload every time a frame
    is processed (at most 5 fps to avoid flooding the browser).

    Each event is JSON with the same shape as /api/stats/latest:
      { timestamp, counts, violations, safe_ppe, persons }
    plus a ``camera_status`` dict so the UI can show which cams are live.
    """
    def event_stream():
        last_ts = ""
        while True:
            # Grab the latest stat from the ring-buffer
            with stats_lock:
                stat = stats_buffer[-1] if stats_buffer else None

            if stat and stat.get("timestamp") != last_ts:
                last_ts = stat["timestamp"]

                # Attach camera status snapshot
                with stream_lock:
                    cam_status = {k: v.get("status", "unknown")
                                  for k, v in streams.items()}

                payload = {**stat, "camera_status": cam_status}
                yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
            else:
                # Heartbeat every second so the connection stays alive
                yield f"data: {{\"ping\": true}}\n\n"

            time.sleep(0.2)   # ~5 fps max push rate

    resp = Response(event_stream(), mimetype="text/event-stream")
    resp.headers["Cache-Control"] = "no-cache"
    resp.headers["X-Accel-Buffering"] = "no"   # disable nginx buffering
    return resp


@app.route("/api/infer/image", methods=["POST"])
def api_infer_image():
    """Single image inference – accepts multipart file or JSON base64."""
    if model is None:
        return jsonify({"ok": False, "message": "Model not loaded"}), 400

    if "file" in request.files:
        f = request.files["file"]
        buf = np.frombuffer(f.read(), np.uint8)
        frame = cv2.imdecode(buf, cv2.IMREAD_COLOR)
    else:
        data = request.get_json(silent=True) or {}
        b64 = data.get("image", "")
        buf = np.frombuffer(base64.b64decode(b64), np.uint8)
        frame = cv2.imdecode(buf, cv2.IMREAD_COLOR)

    if frame is None:
        return jsonify({"ok": False, "message": "Cannot decode image"}), 400

    annotated, stat = process_frame(frame)
    _, out_buf = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 90])
    b64_out = base64.b64encode(out_buf.tobytes()).decode()

    return jsonify({"ok": True, "image": b64_out, "stat": stat})


# ─── Startup ──────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    # Model is already loading in the background (see _startup_load above).
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
