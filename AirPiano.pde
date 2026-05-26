// AirPiano.pde
// Processing display layer — receives JSON from Python via TCP

import processing.net.*;
import java.util.ArrayList;

// ── TCP ──────────────────────────────────────────────────────────────────────
Server server;
String buffer = "";

// ── State ────────────────────────────────────────────────────────────────────
String currentChord  = "";
String currentGesture = "";
int    activeZone    = -1;
float[][] landmarks  = new float[21][2];
boolean hasLandmarks = false;

// Glow flash on trigger
int   flashTimer     = 0;
int   FLASH_DURATION = 18;  // frames

// Note names for zone labels
String[] NOTE_NAMES = {"C", "D", "E", "F", "G", "A", "B"};

// Colors
color BG_COLOR       = color(10, 10, 20);
color ZONE_IDLE      = color(30, 40, 70);
color ZONE_ACTIVE    = color(80, 130, 255);
color GLOW_COLOR     = color(120, 180, 255);
color SKELETON_COLOR = color(0, 220, 150);
color TEXT_COLOR     = color(220, 230, 255);
color MINOR_COLOR    = color(200, 80, 120);

// ── Landmark connections (MediaPipe hand skeleton) ───────────────────────────
int[][] CONNECTIONS = {
  {0,1},{1,2},{2,3},{3,4},       // thumb
  {0,5},{5,6},{6,7},{7,8},       // index
  {0,9},{9,10},{10,11},{11,12},  // middle
  {0,13},{13,14},{14,15},{15,16},// ring
  {0,17},{17,18},{18,19},{19,20} // pinky
};

// ── Setup ────────────────────────────────────────────────────────────────────
void setup() {
  size(800, 600);
  frameRate(30);
  textAlign(CENTER, CENTER);
  server = new Server(this, 5204);
  println("Processing TCP server listening on port 5204");
}

// ── Draw ─────────────────────────────────────────────────────────────────────
void draw() {
  readTCP();
  background(BG_COLOR);

  drawKeyZones();
  drawChordLabel();
  drawSkeleton();
  drawGestureLabel();
  drawInstructions();

  if (flashTimer > 0) {
    drawFlash();
    flashTimer--;
  }
}

// ── TCP Read ─────────────────────────────────────────────────────────────────
void readTCP() {
  Client c = server.available();
  if (c == null) return;

  String incoming = c.readString();
  if (incoming == null) return;

  buffer += incoming;

  // Process complete newline-terminated messages
  while (buffer.contains("\n")) {
    int idx = buffer.indexOf("\n");
    String msg = buffer.substring(0, idx).trim();
    buffer = buffer.substring(idx + 1);
    if (msg.length() > 0) parseMessage(msg);
  }
}

void parseMessage(String msg) {
  try {
    JSONObject json = parseJSONObject(msg);
    if (json == null) return;

    String chord   = json.getString("chord");
    int zone       = json.getInt("zone");
    String gesture = json.getString("gesture");

    // Detect new trigger for flash
    if (!chord.equals(currentChord) && chord.length() > 0) {
      flashTimer = FLASH_DURATION;
    }

    currentChord   = chord;
    activeZone     = zone;
    currentGesture = gesture;

    // Parse landmarks
    JSONArray lmArray = json.getJSONArray("landmarks");
    if (lmArray != null && lmArray.size() == 21) {
      hasLandmarks = true;
      for (int i = 0; i < 21; i++) {
        JSONArray pt = lmArray.getJSONArray(i);
        landmarks[i][0] = pt.getFloat(0) * width;
        landmarks[i][1] = pt.getFloat(1) * height;
      }
    } else {
      hasLandmarks = false;
    }

  } catch (Exception e) {
    // Malformed message — skip
  }
}

// ── Draw Key Zones ────────────────────────────────────────────────────────────
void drawKeyZones() {
  int numZones = 7;
  float zoneW  = width / float(numZones);
  float zoneH  = height * 0.55;
  float zoneY  = height * 0.42;

  for (int i = 0; i < numZones; i++) {
    float x = i * zoneW;

    if (i == activeZone) {
      fill(ZONE_ACTIVE);
      stroke(GLOW_COLOR);
      strokeWeight(3);
      rect(x + 4, zoneY, zoneW - 8, zoneH, 8);

      noFill();
      stroke(GLOW_COLOR, 80);
      strokeWeight(10);
      rect(x + 4, zoneY, zoneW - 8, zoneH, 8);
    } else {
      fill(ZONE_IDLE);
      noStroke();
      rect(x + 4, zoneY, zoneW - 8, zoneH, 8);
    }

    noStroke();
    fill(i == activeZone ? color(255) : color(120, 140, 200));
    textSize(20);
    text(NOTE_NAMES[i], x + zoneW / 2, zoneY + zoneH - 24);
  }
}

// ── Chord Label ───────────────────────────────────────────────────────────────
void drawChordLabel() {
  if (currentChord.length() == 0) {
    fill(60, 70, 100);
    textSize(36);
    text("Show your hand...", width / 2, height * 0.18);
    return;
  }

  boolean isMinor = currentGesture.equals("minor");
  color labelColor = isMinor ? MINOR_COLOR : GLOW_COLOR;

  fill(labelColor);
  textSize(64);
  text(currentChord.replace("_", " ").toUpperCase(), width / 2, height * 0.15);

  fill(TEXT_COLOR, 180);
  textSize(20);
  String gestureLabel = isMinor ? "Fist -> Minor" : "Open Palm -> Major";
  text(gestureLabel, width / 2, height * 0.26);
}

// ── Hand Skeleton ─────────────────────────────────────────────────────────────
void drawSkeleton() {
  if (!hasLandmarks) return;

  stroke(SKELETON_COLOR, 180);
  strokeWeight(2);
  for (int[] conn : CONNECTIONS) {
    float x1 = landmarks[conn[0]][0];
    float y1 = landmarks[conn[0]][1];
    float x2 = landmarks[conn[1]][0];
    float y2 = landmarks[conn[1]][1];
    line(x1, y1, x2, y2);
  }

  noStroke();
  for (int i = 0; i < 21; i++) {
    boolean isTip = (i == 4 || i == 8 || i == 12 || i == 16 || i == 20);
    float r = isTip ? 10 : 6;
    fill(isTip ? GLOW_COLOR : SKELETON_COLOR);
    ellipse(landmarks[i][0], landmarks[i][1], r, r);
  }
}

// ── Gesture Label ─────────────────────────────────────────────────────────────
void drawGestureLabel() {
  if (!hasLandmarks) return;
  fill(TEXT_COLOR, 140);
  textSize(15);
  text("Active Zone: " + (activeZone >= 0 ? NOTE_NAMES[activeZone] : "-"),
       width / 2, height * 0.96);
}

// ── Flash Effect ──────────────────────────────────────────────────────────────
void drawFlash() {
  float alpha = map(flashTimer, 0, FLASH_DURATION, 0, 60);
  noStroke();
  fill(GLOW_COLOR, alpha);
  rect(0, 0, width, height);
}

// ── Instructions ──────────────────────────────────────────────────────────────
void drawInstructions() {
  fill(TEXT_COLOR, 80);
  textSize(13);
  text("Move hand left/right to change note  |  Open palm = Major  |  Fist = Minor",
       width / 2, height * 0.92);
}
