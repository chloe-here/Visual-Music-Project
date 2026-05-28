import os
import wave
import math
import struct

# Force the folder to be exactly next to this script
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CHORD_DIR = os.path.join(SCRIPT_DIR, "chords")

if not os.path.exists(CHORD_DIR):
    os.makedirs(CHORD_DIR)

QUALITIES = {
    "major": [0, 4, 7],     "minor": [0, 3, 7],
    "maj7":  [0, 4, 7, 11], "7":     [0, 4, 7, 10],
    "m7":    [0, 3, 7, 10], "sus4":  [0, 5, 7],
    "dim":   [0, 3, 6],     "aug":   [0, 4, 8]
}

NOTES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
BASE_OCTAVE = 3
BASE_FREQ_C3 = 130.81

def generate_wav(filepath, frequencies, duration=4.0, sample_rate=44100):
    with wave.open(filepath, 'w') as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        
        num_samples = int(duration * sample_rate)
        for i in range(num_samples):
            t = float(i) / sample_rate
            sample = 0
            
            for f in frequencies:
                # Using a mix of Sine and Square-ish waves for a "Full" sound
                fundamental = math.sin(2.0 * math.pi * f * t)
                harmonic    = 0.3 * math.sin(2.0 * math.pi * (f * 3.0) * t)
                
                # Tiny "De-clicker" at the very end (last 10ms)
                # Otherwise, it stays at 1.0 (Full Volume)
                if t > (duration - 0.01):
                    declick = (duration - t) / 0.01
                else:
                    declick = 1.0
                
                sample += (fundamental + harmonic) * declick
                
            # Normalize and set volume
            sample = (sample / len(frequencies))
            final_volume = int(sample * 32767 * 0.6) # 60% volume to avoid distortion
            
            # Clamp value to valid range
            final_volume = max(-32767, min(32767, final_volume))
            wav_file.writeframes(struct.pack('<h', final_volume))

def main():
    print(f"Synthesizing sustained 'Electric Piano' chords in: {CHORD_DIR}")
    count = 0
    root_notes = ["C", "D", "E", "F", "G", "A", "B"]
    
    for note in root_notes:
        root_index = NOTES.index(note)
        for qual, intervals in QUALITIES.items():
            for octave in [3, 4, 5]:
                freqs = []
                for interval in intervals:
                    total_semitones = root_index + interval + ((octave - BASE_OCTAVE) * 12)
                    freq = BASE_FREQ_C3 * (2.0 ** (total_semitones / 12.0))
                    freqs.append(freq)
                
                filename = f"{note}_{qual}_oct{octave}.wav"
                filepath = os.path.join(CHORD_DIR, filename)
                
                generate_wav(filepath, freqs)
                count += 1
                
    print(f"✅ Successfully synthesized {count} rich, sustained chords!")

if __name__ == '__main__':
    main()