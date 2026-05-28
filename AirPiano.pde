// AirPiano.pde
// Processing info panel — receives JSON state from Python via TCP
// Run this BEFORE running air_piano.py

// AirPiano.pde
// Processing info panel — receives JSON state from Python via TCP
// Run this BEFORE running air_piano.py

import processing.net.*;

Server server;
String buf = "";

// State from Python
String chord     = "---";
String quality   = "major";
String gesture   = "major";   // "major"/"minor" — drives the chord colour
int    octave    = 4;
boolean rightHand = false;
boolean leftHand  = false;

// Flash on new note
int    flashTimer = 0;
int    FLASH_DUR  = 20;
String lastChord  = "";

// Colors
color BG      = color(8, 10, 20);
color PANEL   = color(16, 20, 38);
color YELLOW  = color(255, 220, 80);
color CYAN    = color(80, 220, 255);
color MAJOR_C = color(80, 210, 130);
color MINOR_C = color(210, 80, 120);
color MUTED   = color(70, 80, 108);
color WHITE   = color(210, 215, 240);
color OCT5    = color(255, 110, 70);
color OCT4    = color(80, 130, 255);
color OCT3    = color(80, 210, 120);

void setup() {
  size(380, 500);
  frameRate(30);
  textAlign(CENTER, CENTER);
  server = new Server(this, 5204);
  println("Processing TCP server listening on port 5204");
}

void draw() {
  readTCP();
  background(BG);
  drawHeader();
  drawChordBox();
  drawQualityBox();
  drawOctaveBox();
  drawHandBox();
  drawHints();

  if (flashTimer > 0) {
    noStroke();
    fill(YELLOW, map(flashTimer, 0, FLASH_DUR, 0, 50));
    rect(0, 0, width, height);
    flashTimer--;
  }
}

void readTCP() {
  Client c = server.available();
  if (c == null) return;
  String s = c.readString();
  if (s == null) return;
  buf += s;
  while (buf.contains("\n")) {
    int i      = buf.indexOf("\n");
    String msg = buf.substring(0, i).trim();
    buf        = buf.substring(i + 1);
    if (msg.length() > 0) parseMsg(msg);
  }
}

void parseMsg(String msg) {
  try {
    // Check if the message is actually a JSON object
    if (!msg.startsWith("{") || !msg.endsWith("}")) return;
    
    JSONObject j = parseJSONObject(msg);
    if (j == null) return;
    
    String nc = j.getString("chord");
    // Only flash if the note actually changed
    if (!nc.equals("---") && !nc.equals(lastChord)) {
      flashTimer = FLASH_DUR;
      lastChord = nc;
    }
    
    chord = nc.toUpperCase();
    quality = j.getString("quality");
    gesture = j.getString("gesture");
    octave = j.getInt("octave");
    leftHand = j.getBoolean("left_hand");
    rightHand = j.getBoolean("right_hand");
    
  } catch (Exception e) {
    println("JSON Error: " + e.getMessage());
  }
}

void drawHeader() {
  fill(YELLOW); textSize(24);
  text("AIR PIANO", width/2, 28);
  fill(MUTED); textSize(11);
  text("live info panel", width/2, 48);
}

void drawChordBox() {
  box(14, 60, width-28, 105);
  label("CHORD", width/2, 77);
  fill(gesture.equals("minor") ? MINOR_C : MAJOR_C);
  textSize(46);
  text(chord, width/2, 128);
}

void drawQualityBox() {
  box(14, 175, width-28, 68);
  label("CHORD TYPE", width/2, 192);
  fill(CYAN); textSize(26);
  text(quality.toUpperCase(), width/2, 224);
}

void drawOctaveBox() {
  box(14, 253, width-28, 80);
  label("OCTAVE", width/2, 270);
  int[]    octs  = {5, 4, 3};
  color[]  cols  = {OCT5, OCT4, OCT3};
  String[] names = {"HIGH", "MID", "LOW"};
  for (int i = 0; i < 3; i++) {
    float ox   = width/2 - 64 + i * 64;
    boolean on = octs[i] == octave;
    noStroke();
    fill(on ? cols[i] : color(26, 30, 50));
    ellipse(ox, 308, on ? 26 : 18, on ? 26 : 18);
    fill(on ? WHITE : MUTED); textSize(10);
    text(names[i], ox, 326);
  }
}

void drawHandBox() {
  box(14, 343, width-28, 80);
  label("HANDS", width/2, 360);

  noStroke();
  fill(leftHand ? CYAN : color(26, 30, 50));
  ellipse(width/2 - 65, 390, 20, 20);
  fill(leftHand ? CYAN : MUTED); textSize(11);
  text("LEFT", width/2-65, 408);
  fill(MUTED); textSize(9);
  text("note", width/2-65, 418);

  noStroke();
  fill(rightHand ? YELLOW : color(26, 30, 50));
  ellipse(width/2 + 65, 390, 20, 20);
  fill(rightHand ? YELLOW : MUTED); textSize(11);
  text("RIGHT", width/2+65, 408);
  fill(MUTED); textSize(9);
  text("chord type", width/2+65, 418);

  color gc = gesture.equals("minor") ? MINOR_C : MAJOR_C;
  fill(gc, 40); noStroke();
  rect(width/2-36, 378, 72, 24, 8);
  fill(gc); textSize(12);
  text(quality.toUpperCase(), width/2, 390);
}

void drawHints() {
  fill(MUTED); textSize(10);
  text("Left wheel = note  |  Right wheel = chord type", width/2, 448);
  text("Point a finger to select a slice", width/2, 462);
  text("Right-hand height = octave", width/2, 476);
}

void box(float x, float y, float w, float h) {
  fill(PANEL); noStroke(); rect(x, y, w, h, 10);
}

void label(String t, float x, float y) {
  fill(MUTED); textSize(11); text(t, x, y);
}