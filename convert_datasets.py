import os
import json
import wave
import math
import shutil

OUTPUT_DIR = "data"
WINDOW_MS = 108

DIGIT_MAP = {
    "0":"zero","1":"one","2":"two","3":"three","4":"four",
    "5":"five","6":"six","7":"seven","8":"eight","9":"nine"
}

def get_audio_length(path):
    with wave.open(path, 'rb') as wf:
        frames = wf.getnframes()
        rate = wf.getframerate()
        return int((frames / rate) * 1000)

def generate_frames(audio_len):
    return [{
        "index": i,
        "start_ms": i * WINDOW_MS,
        "end_ms": (i + 1) * WINDOW_MS,
        "text": ""
    } for i in range(math.ceil(audio_len / WINDOW_MS))]

# 🔥 AUDIO MNIST
def process_audiomnist():
    print("Processing AudioMNIST...")
    for speaker in os.listdir("audiomnist"):
        sp = os.path.join("audiomnist", speaker)
        if not os.path.isdir(sp):
            continue

        for f in os.listdir(sp):
            if not f.endswith(".wav"):
                continue

            digit = f.split("_")[0]
            word = DIGIT_MAP.get(digit, digit)

            new_name = f"{word}_{f}"
            src = os.path.join(sp, f)

            shutil.copy(src, os.path.join(OUTPUT_DIR, new_name))

            frames = generate_frames(get_audio_length(src))

            json_data = {
                "audio_file": new_name,
                "word": word,
                "language": "en",
                "sentence": word,
                "frames": frames,
                "window_ms": WINDOW_MS
            }

            with open(os.path.join(OUTPUT_DIR, new_name.replace(".wav",".json")), "w") as fp:
                json.dump(json_data, fp, indent=2)

# 🔥 GOOGLE COMMANDS
def process_google():
    print("Processing Google Commands...")
    for word in os.listdir("google_commands"):
        wp = os.path.join("google_commands", word)
        if not os.path.isdir(wp):
            continue

        for f in os.listdir(wp):
            if not f.endswith(".wav"):
                continue

            new_name = f"{word}_{f}"
            src = os.path.join(wp, f)

            shutil.copy(src, os.path.join(OUTPUT_DIR, new_name))

            frames = generate_frames(get_audio_length(src))

            json_data = {
                "audio_file": new_name,
                "word": word,
                "language": "en",
                "sentence": word,
                "frames": frames,
                "window_ms": WINDOW_MS
            }

            with open(os.path.join(OUTPUT_DIR, new_name.replace(".wav",".json")), "w") as fp:
                json.dump(json_data, fp, indent=2)

# RUN
process_audiomnist()
process_google()

print("🔥 DATASETS CONVERTED TO JSON")
