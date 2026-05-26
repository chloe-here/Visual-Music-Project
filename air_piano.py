import cv2
import mediapipe as mp
import pygame
import numpy as np
import socket
import json
import time
import os

# ── TCP Setup ───────────────────────────────────────────────────────────────
TCP_HOST = "localhost"
TCP_PORT = 5204
tcp_sock = None

def connect_to_processing():
    global tcp_sock
    try:
        tcp_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        tcp_sock.connect((TCP_HOST, TCP_PORT))
        tcp_sock.setblocking(False)
        print("Connected to Processing.")
    except Exception:
        print("Processing not running — visuals disabled, audio only.")
        tcp_sock = None

def send_to_processing(data: dict):
    if tcp_sock is None:
        return
    try:
        msg = json.dumps(data) + "\n"
        tcp_sock.sendall(msg.encode())
    except Exception:
        pass

# ── Audio Setup ──────────────────────────────────────────────────────────────
pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=512)

NOTE_NAMES = ["C", "D", "E", "F", "G", "A", "B"]
samples = {}

def load_samples():
    for note in NOTE_NAMES:
        for octave in [3, 4, 5]:
            path = f"{note}_oct{octave}.wav"
            if os.path.exists(path):
                samples[f"{note}_oct{octave}"] = pygame.mixer.Sound(path)
            else:
                print(f"WARNING: {path} not found — run generate_samples.py first")

# Chord intervals relative to root (in semitones)
CHORD_INTERVALS = {
    "major": [0, 4, 7],
    "minor": [0, 3, 7],
}

def play_chord(root_note, chord_type, octave=4):
    key = f"{root_note}_oct{octave}"
    sound = samples.get(key)
    if sound:
        sound.play()

# ── MediaPipe Setup ──────────────────────────────────────────────────────────
mp_hands = mp.solutions.hands
hands = mp_hands.Hands(
    max_num_hands=1,
    min_detection_confidence=0.7,
    min_tracking_confidence=0.6,
)

# ── Gesture Detection ────────────────────────────────────────────────────────
def get_zone(wrist_x, frame_width, num_zones=7):
    """Map horizontal wrist position to a note zone 0-6."""
    zone = int(wrist_x / frame_width * num_zones)
    return max(0, min(zone, num_zones - 1))

def is_finger_extended(landmarks, tip_id, pip_id):
    """True if fingertip is above its PIP joint (finger up)."""
    return landmarks[tip_id].y < landmarks[pip_id].y

def detect_gesture(landmarks):
    """
    Returns 'major' or 'minor' based on hand shape.
    Open hand (3+ fingers up) → major
    Fist / closed (0-1 fingers up) → minor
    """
    fingers = [
        is_finger_extended(landmarks, 8, 6),   # index
        is_finger_extended(landmarks, 12, 10),  # middle
        is_finger_extended(landmarks, 16, 14),  # ring
        is_finger_extended(landmarks, 20, 18),  # pinky
    ]
    extended = sum(fingers)
    return "major" if extended >= 3 else "minor"

def detect_octave(landmarks, current_oct):
    """
    Index finger pointing up → octave up
    Index finger pointing down → octave down
    Only shifts when other fingers are curled (isolated index)
    """
    index_tip  = landmarks[8]
    index_pip  = landmarks[6]
    wrist      = landmarks[0]

    # Check other fingers are curled (fist-like with index extended)
    middle_curled = landmarks[12].y > landmarks[10].y
    ring_curled   = landmarks[16].y > landmarks[14].y
    pinky_curled  = landmarks[20].y > landmarks[18].y

    if not (middle_curled and ring_curled and pinky_curled):
        return current_oct  # not an isolated index gesture

    # Index pointing up
    if index_tip.y < wrist.y - 0.15:
        return 5
    # Index pointing down
    elif index_tip.y > wrist.y + 0.15:
        return 3
    else:
        return 4


# ── Debounce State ───────────────────────────────────────────────────────────
DEBOUNCE_MS = 350
last_trigger_time = 0
last_zone = -1
last_chord = ""
current_octave = 4  # default middle octave

def should_trigger(zone, chord):
    global last_trigger_time, last_zone, last_chord
    now = time.time() * 1000
    if zone == last_zone and chord == last_chord:
        if now - last_trigger_time < DEBOUNCE_MS:
            return False
    last_trigger_time = now
    last_zone = zone
    last_chord = chord
    return True

# ── Main Loop ────────────────────────────────────────────────────────────────
def main():
    load_samples()
    connect_to_processing()

    cap = cv2.VideoCapture(1)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    print("Air Piano running. Press Q to quit.")

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break

        frame = cv2.flip(frame, 1)
        h, w = frame.shape[:2]
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        result = hands.process(rgb)

        payload = {"chord": "", "zone": -1, "gesture": "", "landmarks": []}

        if result.multi_hand_landmarks:
            hand_lm = result.multi_hand_landmarks[0]
            landmarks = hand_lm.landmark

            wrist_x = int(landmarks[0].x * w)
            zone = get_zone(wrist_x, w)
            gesture = detect_gesture(landmarks)
            global current_octave
            current_octave = detect_octave(landmarks, current_octave)
            chord_name = f"{NOTE_NAMES[zone]}_{gesture}"

            # Landmarks as list of [x, y] normalized
            lm_list = [[lm.x, lm.y] for lm in landmarks]

            if should_trigger(zone, gesture):
                play_chord(NOTE_NAMES[zone], gesture, current_octave)
                print(f"Playing {chord_name}")

            payload = {
                "chord": chord_name,
                "zone": zone,
                "gesture": gesture,
                "octave": current_octave,
                "landmarks": lm_list,
                "triggered": should_trigger.__code__ is not None
            }

        send_to_processing(payload)

                # Draw zone gridlines
        num_zones = 7
        zone_w = w // num_zones
        for i in range(1, num_zones):
            x = i * zone_w
            cv2.line(frame, (x, 0), (x, h), (100, 100, 255), 1)
            cv2.putText(frame, NOTE_NAMES[i-1], (((i-1) * zone_w) + 10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (100, 100, 255), 2)
        # Last zone label
        cv2.putText(frame, NOTE_NAMES[6], ((6 * zone_w) + 10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (100, 100, 255), 2)

        # Highlight active zone
        if payload["zone"] >= 0:
            zx = payload["zone"] * zone_w
            overlay = frame.copy()
            cv2.rectangle(overlay, (zx, 0), (zx + zone_w, h), (80, 130, 255), -1)
            cv2.addWeighted(overlay, 0.25, frame, 0.75, 0, frame)

        # Status text
        chord_text  = payload["chord"] if payload["chord"] else "No hand detected"
        gesture_text = f"Gesture: {payload['gesture'].upper()} | Octave: {current_octave}" if payload["gesture"] else ""
        cv2.putText(frame, chord_text,   (20, h - 60),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 100), 2)
        cv2.putText(frame, gesture_text, (20, h - 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 200, 255), 2)
        cv2.putText(frame, "OPEN PALM=Major | FIST=Minor | Move L/R=Note",
                    (20, h - 90), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)

        cv2.imshow("Air Piano - Camera", frame)
                

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()
    if tcp_sock:
        tcp_sock.close()

if __name__ == "__main__":
    main()
