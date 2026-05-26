import numpy as np
from scipy.io.wavfile import write
import os

SAMPLE_RATE = 44100

# Frequencies for C4 through B4
NOTES = {
    "C": 261.63,
    "D": 293.66,
    "E": 329.63,
    "F": 349.23,
    "G": 392.00,
    "A": 440.00,
    "B": 493.88,
}
OCTAVES = {
    3: 0.5,   # one octave down
    4: 1.0,   # normal
    5: 2.0,   # one octave up
}

def generate_note(name, freq, duration=1.8):
    t = np.linspace(0, duration, int(SAMPLE_RATE * duration))

    # Richer sound: fundamental + harmonics
    wave = (
        np.sin(2 * np.pi * freq * t) * 0.6 +
        np.sin(2 * np.pi * freq * 2 * t) * 0.25 +
        np.sin(2 * np.pi * freq * 3 * t) * 0.10 +
        np.sin(2 * np.pi * freq * 4 * t) * 0.05
    )

    # Attack + decay envelope so it sounds like a piano key
    attack_samples = int(0.01 * SAMPLE_RATE)
    attack = np.ones(len(t))
    attack[:attack_samples] = np.linspace(0, 1, attack_samples)

    decay = np.exp(-2.5 * t)
    wave = wave * attack * decay

    # Normalize and convert to int16
    wave = np.int16(wave / np.max(np.abs(wave)) * 32767)
    filename = f"{name}.wav"
    write(filename, SAMPLE_RATE, wave)
    print(f"Generated {filename}")

if __name__ == "__main__":
    for octave, multiplier in OCTAVES.items():
        for name, freq in NOTES.items():
            generate_note(f"{name}_oct{octave}", freq * multiplier)
    print("All samples ready.")
