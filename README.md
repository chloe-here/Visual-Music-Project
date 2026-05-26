how to run:

Instructions for Running Air Piano
Prerequisites

Python 3 installed
Processing 4 installed — processing.org/download


Step 1 — Clone the repo
git clone <your-repo-url>
cd air_piano

Step 2 — Install Python dependencies
pip3 install mediapipe==0.10.9 opencv-python pygame numpy scipy

Step 3 — Generate the sound samples
python3 generate_samples.py
You should see C_oct3.wav through B_oct5.wav — 21 files total — appear in the folder.

Step 4 — Open Processing sketch

Open the Processing IDE
File → Open → navigate to AirPiano/AirPiano.pde
Hit ▶ Play
Wait until the console at the bottom says:

Processing TCP server listening on port 5204

Step 5 — Run Python (after Processing is up)
In terminal:
python3 air_piano.py
You should see:
Connected to Processing.
Air Piano running. Press Q to quit.
