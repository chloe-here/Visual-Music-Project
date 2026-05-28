# air_piano.py
# cv2 imported first to avoid SDL conflict

import cv2
import numpy as np
import os
import socket
import json
import time
import threading
import subprocess
import mediapipe as mp

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

# ── Audio via afplay (Mac built-in, no SDL conflict) ──────────────────────────
NOTE_NAMES = ["C", "D", "E", "F", "G", "A", "B"]
EFFECTS    = ["None", "Echo", "Reverb", "High", "Low", "Chorus"]
SAMPLE_DIR = os.getcwd()

def wav_path(note, octave):
    return os.path.join(SAMPLE_DIR, f"{note}_oct{octave}.wav")

def afplay(path, volume=1.0):
    if not os.path.exists(path):
        print(f"Missing: {path}")
        return
    subprocess.Popen(
        ["afplay", "-v", str(volume), "-q", "1", path],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )

def play_note(note, octave, effect):
    path = wav_path(note, octave)
    afplay(path, volume=1.0)

    if effect == "Echo":
        def _echo():
            time.sleep(0.25); afplay(path, volume=0.45)
            time.sleep(0.25); afplay(path, volume=0.22)
        threading.Thread(target=_echo, daemon=True).start()

    elif effect == "Reverb":
        def _reverb():
            for delay, vol in [(0.07, 0.45), (0.14, 0.30), (0.22, 0.18), (0.32, 0.08)]:
                time.sleep(delay); afplay(path, volume=vol)
        threading.Thread(target=_reverb, daemon=True).start()

    elif effect == "High":
        hi = wav_path(note, min(octave + 1, 5))
        threading.Thread(target=afplay, args=(hi, 0.5), daemon=True).start()

    elif effect == "Low":
        lo = wav_path(note, max(octave - 1, 3))
        threading.Thread(target=afplay, args=(lo, 0.5), daemon=True).start()

    elif effect == "Chorus":
        def _chorus():
            time.sleep(0.035); afplay(path, volume=0.55)
            time.sleep(0.045); afplay(path, volume=0.35)
        threading.Thread(target=_chorus, daemon=True).start()

# ── MediaPipe ─────────────────────────────────────────────────────────────────
mp_hands = mp.solutions.hands
hands    = mp_hands.Hands(
    max_num_hands=2,
    min_detection_confidence=0.7,
    min_tracking_confidence=0.6,
)

# ── Gesture helpers ───────────────────────────────────────────────────────────
def detect_gesture(lm):
    up = sum([
        lm[8].y  < lm[6].y,
        lm[12].y < lm[10].y,
        lm[16].y < lm[14].y,
        lm[20].y < lm[18].y,
    ])
    return "major" if up >= 3 else "minor"

def get_octave(wrist_y_norm):
    if wrist_y_norm < 0.33:   return 5
    elif wrist_y_norm < 0.66: return 4
    else:                      return 3

def index_angle(lm, fw, fh):
    dx = (lm[8].x - lm[0].x) * fw
    dy = (lm[8].y - lm[0].y) * fh
    return np.degrees(np.arctan2(dy, dx)) % 360

def angle_to_slice(angle, n):
    return int(((angle + 90) % 360) / (360.0 / n)) % n

# ── Trigger: only fires when finger moves into a NEW slice ────────────────────
_last_slice = -1

def should_trigger(slice_idx):
    global _last_slice
    if slice_idx == _last_slice:
        return False
    _last_slice = slice_idx
    return True

# ── Wheel colours (BGR) ───────────────────────────────────────────────────────
CHORD_COLORS = [
    (200,  90,  30),
    ( 80, 160,  30),
    (120,  30, 160),
    ( 20, 140, 180),
    (160, 140,  30),
    ( 60,  60, 160),
    (180,  30, 100),
]
EFFECT_COLORS = [
    ( 60,  60,  60),
    (200, 100,  30),
    (180,  30, 120),
    ( 20, 100, 210),
    (100, 180,  30),
    ( 80,  30, 180),
]

# ── Draw wheel ────────────────────────────────────────────────────────────────
def draw_wheel(frame, cx, cy, radius, labels, active, colors, triggered=False):
    n    = len(labels)
    step = 360.0 / n
    ov   = frame.copy()

    for i in range(n):
        start_deg = i * step - 90
        end_deg   = start_deg + step
        bc  = colors[i]
        if i == active:
            col = tuple(min(c + 140, 255) for c in bc) if triggered else tuple(min(c + 90, 255) for c in bc)
        else:
            col = bc
        pts = [(cx, cy)]
        for a in np.linspace(np.radians(start_deg), np.radians(end_deg), 30):
            pts.append((int(cx + radius * np.cos(a)),
                        int(cy + radius * np.sin(a))))
        pts = np.array(pts, np.int32)
        cv2.fillPoly(ov, [pts], col)
        cv2.polylines(ov, [pts], True, (200, 200, 220), 1)

    cv2.addWeighted(ov, 0.60, frame, 0.40, 0, frame)
    cv2.circle(frame, (cx, cy), radius, (210, 215, 230), 2)

    inner = radius // 3
    cv2.circle(frame, (cx, cy), inner, (10, 12, 22), -1)
    cv2.circle(frame, (cx, cy), inner, (90, 95, 120), 2)

    for i in range(n):
        mid = np.radians(i * step - 90 + step / 2)
        lx  = int(cx + radius * 0.65 * np.cos(mid))
        ly  = int(cy + radius * 0.65 * np.sin(mid))
        txt = labels[i]
        sc  = 0.65 if i == active else 0.50
        th  = 2    if i == active else 1
        col = (255, 255, 255) if i == active else (200, 200, 210)
        tw, t_h = cv2.getTextSize(txt, cv2.FONT_HERSHEY_SIMPLEX, sc, th)[0]
        cv2.putText(frame, txt, (lx - tw // 2, ly + t_h // 2),
                    cv2.FONT_HERSHEY_SIMPLEX, sc, col, th, cv2.LINE_AA)

    if active >= 0:
        mid = np.radians(active * step - 90 + step / 2)
        px  = int(cx + (inner + 16) * np.cos(mid))
        py  = int(cy + (inner + 16) * np.sin(mid))
        cv2.circle(frame, (px, py), 9,  (0, 230, 255), -1)
        cv2.circle(frame, (px, py), 9,  (255, 255, 255), 1)

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print("Starting Air Piano...")
    print("Point right hand finger at chord slice to play")
    print("Move to a new slice to play again")
    print("Left hand selects effect")
    print("Hand height = octave")

    missing = [f"{n}_oct{o}.wav" for n in NOTE_NAMES for o in [3, 4, 5]
               if not os.path.exists(wav_path(n, o))]
    if missing:
        print(f"WARNING: {len(missing)} samples missing — run generate_samples.py first")
    else:
        print("All 21 samples found.")

    connect_to_processing()

    cap = cv2.VideoCapture(1, cv2.CAP_AVFOUNDATION)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

    if not cap.isOpened():
        cap = cv2.VideoCapture(0, cv2.CAP_AVFOUNDATION)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH,  1280)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

    if not cap.isOpened():
        print("ERROR: No camera found.")
        return

    for _ in range(5):
        cap.read()

    ret, frame = cap.read()
    if not ret:
        print("ERROR: Cannot read camera frames.")
        return

    fh, fw = frame.shape[:2]
    print(f"Camera: {fw}x{fh}. Press Q to quit.")

    cv2.namedWindow("Air Piano", cv2.WINDOW_NORMAL)
    cv2.setWindowProperty("Air Piano", cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)

    WHEEL_R = int(min(fw, fh) * 0.22)
    LC = (int(fw * 0.13), fh // 2)
    RC = (int(fw * 0.87), fh // 2)

    chord_slice   = 0
    effect_slice  = 0
    octave        = 4
    gesture       = "major"
    right_present = False
    left_present  = False
    right_trigger = False
    flash_frames  = 0

    startup_time = time.time()

    while True:
        ret, frame = cap.read()
        if not ret:
            print("Camera lost.")
            break

        frame = cv2.flip(frame, 1)
        fh_r, fw_r = frame.shape[:2]

        rgb    = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        result = hands.process(rgb)

        right_present = False
        left_present  = False
        right_trigger = False

        if result.multi_hand_landmarks:
            for hand_lm in result.multi_hand_landmarks:
                lm  = hand_lm.landmark
                wx  = lm[0].x
                wy  = lm[0].y
                ang = index_angle(lm, fw_r, fh_r)
                tip = (int(lm[8].x * fw_r), int(lm[8].y * fh_r))

                if wx < 0.5:
                    # Left half → effects wheel + major/minor control
                    left_present = True
                    effect_slice = angle_to_slice(ang, len(EFFECTS))
                    gesture      = detect_gesture(lm)
                    cv2.line(frame, LC, tip, (255, 220, 80), 2)
                    cv2.circle(frame, tip, 11, (255, 220, 80), -1)
                else:
                    # Right half → chord wheel (no gesture detection here)
                    right_present = True
                    chord_slice   = angle_to_slice(ang, len(NOTE_NAMES))
                    octave        = get_octave(wy)
                    # Fire once when entering a new slice
                    if should_trigger(chord_slice):
                        right_trigger = True
                    cv2.line(frame, RC, tip, (80, 220, 255), 2)
                    cv2.circle(frame, tip, 11, (80, 220, 255), -1)

        cur_note   = NOTE_NAMES[chord_slice]
        cur_effect = EFFECTS[effect_slice]

        if right_trigger and time.time() - startup_time > 2.0:
            play_note(cur_note, octave, cur_effect)
            flash_frames = 8
            print(f"  ♪  {cur_note} {gesture} | Oct {octave} | {cur_effect}")

        # Draw wheels
        draw_wheel(frame, *LC, WHEEL_R, EFFECTS,    effect_slice, EFFECT_COLORS)
        draw_wheel(frame, *RC, WHEEL_R, NOTE_NAMES, chord_slice,  CHORD_COLORS,
                   triggered=(flash_frames > 0))

        if flash_frames > 0:
            flash_frames -= 1

        # Labels
        cv2.putText(frame, "EFFECTS",
                    (LC[0] - 48, LC[1] - WHEEL_R - 14),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 220, 80), 2, cv2.LINE_AA)
        cv2.putText(frame, "CHORDS",
                    (RC[0] - 42, RC[1] - WHEEL_R - 14),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (80, 220, 255), 2, cv2.LINE_AA)

        # Octave indicator
        oct_str = {5: "OCT 5  HIGH", 4: "OCT 4  MID", 3: "OCT 3  LOW"}[octave]
        cv2.putText(frame, oct_str, (fw_r // 2 - 80, 36),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (200, 200, 255), 2, cv2.LINE_AA)

        # Status bar
        status = f"{cur_note} {gesture.upper()}  |  {cur_effect}  |  Oct {octave}"
        cv2.rectangle(frame, (0, fh_r - 36), (fw_r, fh_r), (8, 10, 18), -1)
        cv2.putText(frame, status, (fw_r // 2 - 180, fh_r - 12),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.72, (200, 210, 255), 1, cv2.LINE_AA)

        send_state({
            "chord":      f"{cur_note}_{gesture}",
            "effect":     cur_effect,
            "octave":     octave,
            "gesture":    gesture,
            "right_hand": right_present,
            "left_hand":  left_present,
        })

        cv2.imshow("Air Piano", frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()
    if tcp_sock:
        tcp_sock.close()
    print("Bye.")

if __name__ == "__main__":
    main()
