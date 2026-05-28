# air_piano.py
# cv2 imported first to avoid SDL conflict
 
import cv2
import numpy as np
import os
import math
import socket
import json
import time
import subprocess
import mediapipe as mp
from PIL import Image, ImageDraw, ImageFont
 
# ── TCP to Processing ─────────────────────────────────────────────────────────
TCP_HOST = "localhost"
TCP_PORT = 5204
tcp_sock = None
 
def connect_to_processing():
    global tcp_sock
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((TCP_HOST, TCP_PORT))
        s.setblocking(False)
        tcp_sock = s
        print("Connected to Processing.")
    except Exception:
        print("Processing not running — continuing without it.")
        tcp_sock = None
 
def send_state(data: dict):
    if tcp_sock is None:
        return
    try:
        tcp_sock.sendall((json.dumps(data) + "\n").encode())
    except Exception:
        pass
 
# ── Fonts (TrueType via Pillow) ───────────────────────────────────────────────
FONT_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/Avenir Next.ttc",   # macOS
    "/System/Library/Fonts/SFNSRounded.ttf",
    "/System/Library/Fonts/HelveticaNeue.ttc",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/Library/Fonts/Arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",       # Linux fallback
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
]
FONT_PATH = next((p for p in FONT_CANDIDATES if os.path.exists(p)), None)
_font_cache = {}
 
def _font(size):
    size = int(size)
    if size not in _font_cache:
        try:
            _font_cache[size] = ImageFont.truetype(FONT_PATH, size) if FONT_PATH else ImageFont.load_default()
        except Exception:
            _font_cache[size] = ImageFont.load_default()
    return _font_cache[size]
 
def text_w(txt, size):
    return _font(size).getlength(txt)
 
_text_queue = []
 
def queue_text(x, y, txt, size, color_bgr, anchor="lm", shadow=False):
    r, g, b = color_bgr[2], color_bgr[1], color_bgr[0]
    _text_queue.append((int(x), int(y), txt, int(size), (r, g, b), anchor, shadow))
 
def flush_text(frame):
    if not _text_queue:
        return frame
    img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    d   = ImageDraw.Draw(img)
    for x, y, txt, size, color, anchor, shadow in _text_queue:
        f = _font(size)
        if shadow:
            d.text((x + 1, y + 1), txt, font=f, fill=(0, 0, 0), anchor=anchor)
        d.text((x, y), txt, font=f, fill=color, anchor=anchor)
    _text_queue.clear()
    return cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
 
# ── Notes & chord qualities ───────────────────────────────────────────────────
NOTE_NAMES = ["C", "D", "E", "F", "G", "A", "B"]                       
QUALITIES  = ["major", "maj7", "7", "sus4", "minor", "m7", "dim", "aug"]  
 
QUALITY_LABELS = {
    "major": "maj", "maj7": "maj7", "7": "7", "sus4": "sus4",
    "minor": "m",   "m7":  "m7",   "dim": "dim", "aug":  "aug",
}
QUALITY_SUFFIX = {
    "major": "", "minor": "m", "maj7": "maj7", "7": "7",
    "sus4": "sus4", "m7": "m7", "dim": "dim", "aug": "aug",
}
MINOR_QUALITIES = {"minor", "m7", "dim"}
 
CHORD_DIR = os.path.join(os.getcwd(), "chords")
 
def chord_path(note, quality, octave):
    return os.path.join(CHORD_DIR, f"{note}_{quality}_oct{octave}.wav")
 
def chord_name(note, quality):
    return note + QUALITY_SUFFIX[quality]
 
def is_minor_quality(q):
    return q in MINOR_QUALITIES
 
# ── Audio via afplay ──────────────────────────────────────────────────────────
def afplay(path, volume=1.0):
    if not os.path.exists(path):
        print(f"Missing: {path}")
        return
    subprocess.Popen(
        ["afplay", "-v", str(volume), "-q", "1", path],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
 
def play_chord(note, quality, octave):
    afplay(chord_path(note, quality, octave), volume=1.0)
 
# ── Geometry helpers & Math Fixes ──────────────────────────────────────────────
# Tweak these if the physical finger doesn't perfectly match the visual slice
NOTE_OFFSET = -25  
QUAL_OFFSET = -22 

# ── Audio via afplay ──────────────────────────────────────────────────────────

current_audio_process = None 

def afplay(path, volume=1.0):
    global current_audio_process  # Bring in the tracker
    
    if not os.path.exists(path):
        print(f"Missing: {path}")
        return
        
    # 1. If a chord is already playing, instantly stop it!
    if current_audio_process is not None:
        current_audio_process.terminate()
        
    # 2. Play the new chord and save this process to our variable
    current_audio_process = subprocess.Popen(
        ["afplay", "-v", str(volume), "-q", "1", path],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
 
def play_chord(note, quality, octave):
    afplay(chord_path(note, quality, octave), volume=1.0)

def get_octave(wrist_y_norm):
    if wrist_y_norm < 0.33:   return 5
    elif wrist_y_norm < 0.66: return 4
    else:                      return 3
 
def angle_around(cx, cy, px, py):
    return math.degrees(math.atan2(py - cy, px - cx)) % 360
 
def angle_to_slice(angle, n, offset=0):
    return int(((angle + 90 + offset) % 360) / (360.0 / n)) % n
 
# ── Colours & UI Drawing ──────────────────────────────────────────────────────
NOTE_COLORS = [
    ( 90, 170, 230), ( 90, 200, 180), (120, 200, 120), (150, 200,  90),
    (210, 180,  90), (220, 140,  90), (210, 110, 130),
]
QUALITY_COLORS = [          
    (205, 150,  80), (195, 160,  90), (185, 140,  95), (175, 130, 115),
    (160, 100, 175), (165,  95, 160), (150,  90, 145), (180, 130, 100),
]
 
def _blend(frame, overlay, alpha, roi):
    x, y, w, h = roi
    x2, y2 = x + w, y + h
    x,  y  = max(0, x),  max(0, y)
    x2, y2 = min(frame.shape[1], x2), min(frame.shape[0], y2)
    if x2 <= x or y2 <= y: return
    cv2.addWeighted(overlay[y:y2, x:x2], alpha,
                    frame[y:y2, x:x2], 1 - alpha, 0, frame[y:y2, x:x2])
 
def rounded_rect(img, x, y, w, h, r, color):
    r = int(min(r, w // 2, h // 2))
    cv2.rectangle(img, (x + r, y), (x + w - r, y + h), color, -1)
    cv2.rectangle(img, (x, y + r), (x + w, y + h - r), color, -1)
    for cxr, cyr in [(x + r, y + r), (x + w - r, y + r),
                     (x + r, y + h - r), (x + w - r, y + h - r)]:
        cv2.circle(img, (cxr, cyr), r, color, -1)
 
def hub_radius(radius): return int(radius * 0.42)
 
def draw_wheel(frame, cx, cy, radius, labels, active, colors, center_text="", triggered=False):
    n = len(labels)
    step = 360.0 / n
    inner = hub_radius(radius)
    bbox = (cx - radius, cy - radius, 2 * radius, 2 * radius)
 
    ov = frame.copy()
    for i in range(n):
        s = i * step - 90
        e = s + step
        base = colors[i]
        if i == active:
            col = tuple(min(int(v + 95), 255) for v in base) if triggered else base
        else:
            col = tuple(int(v * 0.32 + 20) for v in base)
        pts = [(cx, cy)]
        for a in np.linspace(np.radians(s), np.radians(e), 28):
            pts.append((int(cx + radius * np.cos(a)), int(cy + radius * np.sin(a))))
        cv2.fillPoly(ov, [np.array(pts, np.int32)], col)
    _blend(frame, ov, 0.42, bbox)
 
    for i in range(n):
        a = np.radians(i * step - 90)
        cv2.line(frame, (cx, cy), (int(cx + radius * np.cos(a)), int(cy + radius * np.sin(a))), (150, 155, 180), 1, cv2.LINE_AA)
    cv2.circle(frame, (cx, cy), radius, (222, 226, 240), 2, cv2.LINE_AA)
 
    hov = frame.copy()
    cv2.circle(hov, (cx, cy), inner, (14, 16, 26), -1)
    _blend(frame, hov, 0.82, (cx - inner, cy - inner, 2 * inner, 2 * inner))
    cv2.circle(frame, (cx, cy), inner, (92, 98, 124), 2, cv2.LINE_AA)
 
    for i in range(n):
        mid = np.radians(i * step - 90 + step / 2)
        lx  = cx + radius * 0.70 * np.cos(mid)
        ly  = cy + radius * 0.70 * np.sin(mid)
        is_a = (i == active)
        queue_text(lx, ly, labels[i], 27 if is_a else 22, (255, 255, 255) if is_a else (205, 208, 220), anchor="mm", shadow=True)
 
    if center_text: queue_text(cx, cy, center_text, 46, (236, 239, 250), anchor="mm")
 
def draw_hud(frame, rows, fw):
    fs, line_h, padx, pady, gap = 19, 30, 18, 16, 18
    label_w = max(text_w(k, fs) for k, _ in rows)
    val_w   = max(text_w(v, fs) for _, v in rows)
    w = int(max(padx * 2 + label_w + gap + val_w, 200))
    h = pady * 2 + line_h * len(rows)
    x, y = fw - w - 18, 16
    ov = frame.copy()
    rounded_rect(ov, x, y, w, h, 12, (16, 18, 30))
    _blend(frame, ov, 0.62, (x, y, w, h))
    for i, (k, v) in enumerate(rows):
        ty = y + pady + line_h // 2 + line_h * i
        queue_text(x + padx, ty, k, fs, (150, 156, 180), anchor="lm")
        queue_text(x + padx + label_w + gap, ty, v, fs, (95, 212, 236), anchor="lm")
 
def draw_bottom_bar(frame, segments, fw, fh):
    fs, gap = 22, 36
    widths = [(text_w(k + " ", fs), text_w(v, fs)) for k, v in segments]
    total  = sum(wk + wv for wk, wv in widths) + gap * (len(segments) - 1)
    padx, bh = 30, 50
    bw = int(total + padx * 2)
    x  = (fw - bw) // 2
    y  = fh - bh - 18
    ov = frame.copy()
    rounded_rect(ov, x, y, bw, bh, 20, (16, 18, 30))
    _blend(frame, ov, 0.60, (x, y, bw, bh))
 
    cy = y + bh // 2
    tx = x + padx
    for idx, (k, v) in enumerate(segments):
        wk, wv = widths[idx]
        queue_text(tx, cy, k + " ", fs, (150, 156, 180), anchor="lm"); tx += wk
        queue_text(tx, cy, v, fs, (95, 212, 236), anchor="lm");        tx += wv
        if idx < len(segments) - 1:
            cv2.circle(frame, (int(tx + gap // 2), cy), 2, (115, 120, 145), -1, cv2.LINE_AA)
            tx += gap
 
# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print("Starting Air Piano...")
    connect_to_processing()
 
    mp_hands = mp.solutions.hands
    hands = mp_hands.Hands(max_num_hands=2, min_detection_confidence=0.7, min_tracking_confidence=0.6)
 
    cap = cv2.VideoCapture(1, cv2.CAP_AVFOUNDATION)
    if not cap.isOpened(): cap = cv2.VideoCapture(0, cv2.CAP_AVFOUNDATION)
    if not cap.isOpened(): return print("ERROR: No camera found.")
 
    print("Warming up camera...")
    for _ in range(10):
        cap.read()
        time.sleep(0.05)
        
    ret, frame = cap.read()
    if not ret: return print("ERROR: Cannot read camera frames.")
 
    fh, fw = frame.shape[:2]
    cv2.namedWindow("Air Piano", cv2.WINDOW_NORMAL)
    cv2.setWindowProperty("Air Piano", cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
 
    WHEEL_R = int(min(fw, fh) * 0.27)     
    HUB_R   = hub_radius(WHEEL_R)
    LC = (int(fw * 0.27), fh // 2)        
    RC = (int(fw * 0.73), fh // 2)        
 
    note_slice = 0
    quality_slice = 0
    octave = 4
    last_note_slice = -1
    flash_frames = 0
    startup_time = time.time()
    last_play_time = 0      
 
 
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret: break
 
        frame = cv2.flip(frame, 1)
        fh_r, fw_r = frame.shape[:2]
        rgb    = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        result = hands.process(rgb)
 
        note_present = qual_present = note_trigger = note_off = False
 
        if result.multi_hand_landmarks:
            for hand_lm in result.multi_hand_landmarks:
                lm  = hand_lm.landmark
                wx, wy = lm[0].x, lm[0].y
                tip = (int(lm[8].x * fw_r), int(lm[8].y * fh_r))
 
                if wx < 0.5:
                    note_present = True
                    octave = get_octave(wy)
                    dist = math.hypot(tip[0] - LC[0], tip[1] - LC[1])
                    if dist < HUB_R:
                        note_off = True                       
                    else:
                        ang = angle_around(*LC, *tip)
                        # Applied the visual offset math fix here!
                        note_slice = angle_to_slice(ang, len(NOTE_NAMES), NOTE_OFFSET)
                        if note_slice != last_note_slice:
                            note_trigger = True
                            last_note_slice = note_slice
                    cv2.line(frame, LC, tip, (90, 200, 230), 2, cv2.LINE_AA)
                    cv2.circle(frame, tip, 10, (90, 200, 230), -1, cv2.LINE_AA)
                else:
                    qual_present = True
                    dist = math.hypot(tip[0] - RC[0], tip[1] - RC[1])
                    if dist >= HUB_R:
                        ang = angle_around(*RC, *tip)
                        # Applied the visual offset math fix here!
                        quality_slice = angle_to_slice(ang, len(QUALITIES), QUAL_OFFSET)
                    cv2.line(frame, RC, tip, (190, 130, 230), 2, cv2.LINE_AA)
                    cv2.circle(frame, tip, 10, (190, 130, 230), -1, cv2.LINE_AA)
 
        if note_off or not note_present:
            last_note_slice = -1
 
        cur_note    = NOTE_NAMES[note_slice]
        cur_quality = QUALITIES[quality_slice]
        disp_q      = QUALITY_LABELS[cur_quality]
        full_chord  = chord_name(cur_note, cur_quality)
        note_active = note_present and not note_off
 
        if note_trigger and time.time() - startup_time > 2.0:
            if time.time() - last_play_time > 0.4: 
                play_chord(cur_note, cur_quality, octave)
                flash_frames = 8
                last_play_time = time.time()
                print(f"  ♪  {full_chord} | Oct {octave}")
 
        draw_wheel(frame, *LC, WHEEL_R, NOTE_NAMES, note_slice, NOTE_COLORS,
                   center_text=(cur_note if note_active else "OFF"),
                   triggered=(flash_frames > 0))
        draw_wheel(frame, *RC, WHEEL_R, [QUALITY_LABELS[q] for q in QUALITIES],
                   quality_slice, QUALITY_COLORS, center_text=disp_q)
 
        if flash_frames > 0: flash_frames -= 1
 
        hands_n = int(note_present) + int(qual_present)
        draw_hud(frame, [
            ("Note",   cur_note if note_active else "—"),
            ("Type",   disp_q),
            ("Chord",  full_chord),
            ("Octave", str(octave)),
            ("Hands",  str(hands_n)),
        ], fw_r)
        draw_bottom_bar(frame, [
            ("Mode",   "Two-hand Chord"),
            ("Chord",  full_chord),
            ("Octave", str(octave)),
        ], fw_r, fh_r)
 
        send_state({
            "chord":      f"{cur_note}_{cur_quality}",
            "quality":    cur_quality,
            "octave":     octave,
            "gesture":    "minor" if is_minor_quality(cur_quality) else "major",
            "right_hand": qual_present,
            "left_hand":  note_present,
        })
 
        frame = flush_text(frame)
        cv2.imshow("Air Piano", frame)
        if cv2.waitKey(1) & 0xFF == ord('q'): break
 
    cap.release()
    cv2.destroyAllWindows()
    if tcp_sock: tcp_sock.close()
 
if __name__ == "__main__":
    main()