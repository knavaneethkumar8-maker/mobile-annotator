from flask import Flask, render_template, request, jsonify, send_from_directory, session, redirect, url_for, send_file
import wave
import math
import os
import shutil
from datetime import datetime
import json
import glob
from functools import wraps
from config import BASE_PATH, DEBUG, HOST, PORT

import subprocess
import tempfile
import base64
import time
import requests
import uuid

app = Flask(__name__)
app.secret_key = 'your-secret-key-change-this-in-production'

# Only apply BASE_PATH if it's not empty
if BASE_PATH:
    @app.before_request
    def fix_script_name():
        from flask import request
        request.environ['SCRIPT_NAME'] = BASE_PATH
    
    app.config['APPLICATION_ROOT'] = BASE_PATH

# Helper function for URL generation
def url_for_path(path):
    """Generate URL with proper base path"""
    if path.startswith('/'):
        path = path[1:]
    return f"{BASE_PATH}/{path}" if BASE_PATH else f"/{path}"

# Make url_for_path available to templates
app.jinja_env.globals['url_for_path'] = url_for_path

# Folders
AUDIO_FOLDER = "data"
SUBMIT_FOLDER = "annotation_submitted"
USERS_FILE = "users.json"
COMPLETED_LOG = "completed_files.json"
MOBILE_DATASET_FOLDER = "MOBILE_DATASET"
MOBILE_VERIFIED_FOLDER = "MOBILE_VERIFIED_DATA"
USER_SUBMISSIONS_FOLDER = "user_submissions"
FILE_ASSIGNMENTS_FILE = "file_assignments.json"
USER_STATS_FILE = "user_stats.json"
SKIPPED_FILES_FILE = "skipped_files.json"
DAILY_STATS_FILE = "daily_stats.json"
SELF_RECORDINGS_FOLDER = "self_recordings"
LIVE_AUDIO_CACHE_FOLDER = "live_audio_cache"
DESKTOP_LIVE_SESSION_FOLDER = "desktop_live_sessions"

# Create all necessary folders
os.makedirs(SUBMIT_FOLDER, exist_ok=True)
os.makedirs(MOBILE_DATASET_FOLDER, exist_ok=True)
os.makedirs(MOBILE_VERIFIED_FOLDER, exist_ok=True)
os.makedirs(USER_SUBMISSIONS_FOLDER, exist_ok=True)
os.makedirs(SELF_RECORDINGS_FOLDER, exist_ok=True)
os.makedirs(LIVE_AUDIO_CACHE_FOLDER, exist_ok=True)
os.makedirs(DESKTOP_LIVE_SESSION_FOLDER, exist_ok=True)

from werkzeug.middleware.proxy_fix import ProxyFix

if BASE_PATH:
    app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)


# ==============================
# TRAINING DATA FOLDER CONFIGURATION
# ==============================

# Base folder for mobile training data
MOBILE_TRAINING_DATA_BASE_FOLDER = "/mnt/data_disk_2/UI_TRAINING_DATA/MOBILE_DATA/normal_data"

# Create the base directory
os.makedirs(MOBILE_TRAINING_DATA_BASE_FOLDER, exist_ok=True)
print(f"Mobile training data base folder ready: {MOBILE_TRAINING_DATA_BASE_FOLDER}")

def get_mobile_training_date_folder():
    """Get current date folder for mobile training data (YYYY-MM-DD)"""
    current_date = datetime.now().strftime("%Y-%m-%d")
    date_folder = os.path.join(MOBILE_TRAINING_DATA_BASE_FOLDER, current_date)
    return date_folder

def save_to_mobile_training_data(audio_source_path, textgrid_source_path, json_source_path, base_filename):
    """
    Save complete package (WAV + TextGrid + JSON) to mobile training data folder with date-wise organization
    """
    try:
        # Get date-wise folder for today
        training_folder = get_mobile_training_date_folder()
        os.makedirs(training_folder, exist_ok=True)
        print(f"Saving to mobile training date folder: {training_folder}")
        
        saved_files = []
        
        # Save WAV file
        if audio_source_path and os.path.exists(audio_source_path):
            dest_wav = os.path.join(training_folder, f"{base_filename}.wav")
            # Check if file already exists
            if os.path.exists(dest_wav):
                print(f"WAV file already exists, skipping: {dest_wav}")
            else:
                shutil.copy2(audio_source_path, dest_wav)
                saved_files.append(dest_wav)
                print(f"Saved WAV to mobile training data: {dest_wav}")
        else:
            print(f"Warning: Audio source not found: {audio_source_path}")
        
        # Save TextGrid file
        if textgrid_source_path and os.path.exists(textgrid_source_path):
            dest_tg = os.path.join(training_folder, f"{base_filename}.TextGrid")
            if os.path.exists(dest_tg):
                print(f"TextGrid file already exists, skipping: {dest_tg}")
            else:
                shutil.copy2(textgrid_source_path, dest_tg)
                saved_files.append(dest_tg)
                print(f"Saved TextGrid to mobile training data: {dest_tg}")
        else:
            print(f"Warning: TextGrid source not found: {textgrid_source_path}")
        
        # Save JSON file
        if json_source_path and os.path.exists(json_source_path):
            dest_json = os.path.join(training_folder, f"{base_filename}.json")
            if os.path.exists(dest_json):
                print(f"JSON file already exists, skipping: {dest_json}")
            else:
                shutil.copy2(json_source_path, dest_json)
                saved_files.append(dest_json)
                print(f"Saved JSON to mobile training data: {dest_json}")
        else:
            print(f"Warning: JSON source not found: {json_source_path}")
        
        print(f"Successfully saved {len(saved_files)} files to {training_folder}")
        return len(saved_files) > 0
        
    except Exception as e:
        print(f"Error saving to mobile training data: {e}")
        import traceback
        traceback.print_exc()
        return False

def delete_from_mobile_training_data(base_filename):
    """
    Delete files from mobile training data folder when rejected
    Checks all date folders to find and delete the files
    """
    try:
        deleted = []
        
        print(f"Looking for files to delete with base name: {base_filename}")
        print(f"Searching in base folder: {MOBILE_TRAINING_DATA_BASE_FOLDER}")
        
        # Check if base folder exists
        if not os.path.exists(MOBILE_TRAINING_DATA_BASE_FOLDER):
            print(f"Mobile training data base folder does not exist: {MOBILE_TRAINING_DATA_BASE_FOLDER}")
            return deleted
        
        # Get all date subfolders in training data base folder
        date_found = False
        for date_folder in os.listdir(MOBILE_TRAINING_DATA_BASE_FOLDER):
            folder_path = os.path.join(MOBILE_TRAINING_DATA_BASE_FOLDER, date_folder)
            
            # Only process directories (date folders)
            if os.path.isdir(folder_path):
                # Files to delete in this date folder
                wav_path = os.path.join(folder_path, f"{base_filename}.wav")
                tg_path = os.path.join(folder_path, f"{base_filename}.TextGrid")
                json_path = os.path.join(folder_path, f"{base_filename}.json")
                
                # Check and delete each file
                for file_path in [wav_path, tg_path, json_path]:
                    if os.path.exists(file_path):
                        os.remove(file_path)
                        deleted.append(file_path)
                        print(f"Deleted from mobile training data: {file_path}")
                        date_found = True
        
        if not date_found:
            print(f"No files found for {base_filename} in any date folder")
        else:
            print(f"Successfully deleted {len(deleted)} files from mobile training data")
        
        return deleted
        
    except Exception as e:
        print(f"Error deleting from mobile training data: {e}")
        import traceback
        traceback.print_exc()
        return []


# ==============================
# TEXTGRID TIER GENERATION HELPERS
# ==============================

AKSHAR_SET = {
    "अ", "आ", "इ", "ई", "उ", "ऊ", "ऋ", "ए", "ऐ", "ओ", "औ",
    "क", "ख", "ग", "घ", "ङ",
    "च", "छ", "ज", "झ", "ञ",
    "ट", "ठ", "ड", "ढ", "ण",
    "त", "थ", "द", "ध", "न",
    "प", "फ", "ब", "भ", "म",
    "य", "र", "ल", "व",
    "श", "ष", "स", "ह",
    "क्ष", "त्र", "ज्ञ",
    "ं", "ँ", "ः", "ॉ", "ऑ", "०", "१", "२", "३", "४", "५", "६", "७", "८", "९"
}

VYANJAN_SET = {
    "क", "ख", "ग", "घ", "ङ",
    "च", "छ", "ज", "झ", "ञ",
    "ट", "ठ", "ड", "ढ", "ण",
    "त", "थ", "द", "ध", "न",
    "प", "फ", "ब", "भ", "म",
    "य", "र", "ल", "व",
    "श", "ष", "स", "ह",
    "क्ष", "त्र", "ज्ञ"
}

SWAR_SET = {"अ", "आ", "इ", "ई", "उ", "ऊ", "ऋ", "ए", "ऐ", "ओ", "औ"}
NAASIKA_SET = {"म", "न", "ण", "ङ", "ञ", "ं", "ँ"}

# Normalization map for cleaning
norm_map = {
    "ा": "आ", "ि": "इ", "ी": "ई", "ु": "उ", "ू": "ऊ", "ृ": "ऋ",
    "े": "ए", "ै": "ऐ", "ो": "ओ", "ौ": "औ",
    "ँ": "ं",
    "ण": "न", "ङ": "न", "ञ": "न",
    "श": "स", "ष": "स",
    "ई": "इ", "ऊ": "उ", "ऐ": "ए", "औ": "ओ"
}

def clean_text(text):
    """Clean and normalize text"""
    text = text.strip()
    if text == "":
        return ""
    
    # normalize + filter
    chars = []
    for ch in text:
        if ch in norm_map:
            ch = norm_map[ch]
        if ch in AKSHAR_SET:
            chars.append(ch)
    
    if not chars:
        return ""
    
    # dedup
    dedup = [chars[0]]
    for ch in chars[1:]:
        if ch != dedup[-1]:
            dedup.append(ch)
    
    # remove implicit अ
    final = []
    i = 0
    while i < len(dedup):
        ch = dedup[i]
        if (ch in VYANJAN_SET and
            i + 1 < len(dedup) and
            dedup[i + 1] == "अ"):
            final.append(ch)
            i += 2
        else:
            final.append(ch)
            i += 1
    
    return "".join(final)

def get_swar(text):
    """Extract swar (vowels) from text"""
    text = text.strip()
    if text == "":
        return ""
    
    swars = []
    i = 0
    while i < len(text):
        ch = text[i]
        
        if ch in SWAR_SET:
            swars.append(ch)
        
        elif ch in VYANJAN_SET:
            if i + 1 < len(text) and text[i + 1] in SWAR_SET:
                swars.append(text[i + 1])
                i += 1
            else:
                swars.append("अ")
        
        i += 1
    
    return "".join(swars)

def get_vyanjan(text):
    """Extract vyanjan (consonants) from text"""
    out = []
    for ch in text:
        if ch in VYANJAN_SET:
            if not out or out[-1] != ch:
                out.append(ch)
    return "".join(out)

def get_naasika(text):
    """Extract naasika (nasal sounds) from text"""
    out = []
    for ch in text:
        if ch in NAASIKA_SET:
            if not out or out[-1] != ch:
                out.append(ch)
    return "".join(out)

def create_enhanced_textgrid(frames, duration, sentence, annotator, full_sequence):
    """
    Create enhanced TextGrid with 7 tiers:
    - sentence: original sentence
    - annotations: original frames (108ms windows)
    - window_108ms: cleaned version of annotations
    - swar: extracted vowels
    - vyanjan: extracted consonants
    - naasika: extracted nasal sounds
    - annotator: annotator name
    """
    tg = []
    
    tg.append('File type = "ooTextFile"')
    tg.append('Object class = "TextGrid"\n')
    
    tg.append(f"xmin = 0")
    tg.append(f"xmax = {duration}")
    tg.append("tiers? <exists>")
    tg.append("size = 7")
    tg.append("item []:")
    
    # ========== 1. sentence tier ==========
    tg.append("    item [1]:")
    tg.append('        class = "IntervalTier"')
    tg.append('        name = "sentence"')
    tg.append(f"        xmin = 0")
    tg.append(f"        xmax = {duration}")
    tg.append("        intervals: size = 1")
    
    tg.append("        intervals [1]:")
    tg.append(f"            xmin = 0")
    tg.append(f"            xmax = {duration}")
    tg.append(f'            text = "{sentence if sentence else full_sequence}"')
    
    # ========== 2. annotations tier (original frames) ==========
    tg.append("    item [2]:")
    tg.append('        class = "IntervalTier"')
    tg.append('        name = "annotations"')
    tg.append(f"        xmin = 0")
    tg.append(f"        xmax = {duration}")
    tg.append(f"        intervals: size = {len(frames)}")
    
    for i, f in enumerate(frames, 1):
        start = f.get("start_ms", 0) / 1000.0
        end = f.get("end_ms", 0) / 1000.0
        text = f.get("text", "") if f.get("text") else ""
        
        tg.append(f"        intervals [{i}]:")
        tg.append(f"            xmin = {start}")
        tg.append(f"            xmax = {end}")
        tg.append(f'            text = "{text}"')
    
    # ========== 3. window_108ms tier (cleaned version) ==========
    cleaned_frames = []
    for f in frames:
        cleaned_text = clean_text(f.get("text", "")) if f.get("text") else ""
        cleaned_frames.append({
            "start_ms": f.get("start_ms", 0),
            "end_ms": f.get("end_ms", 0),
            "text": cleaned_text
        })
    
    tg.append("    item [3]:")
    tg.append('        class = "IntervalTier"')
    tg.append('        name = "window_108ms"')
    tg.append(f"        xmin = 0")
    tg.append(f"        xmax = {duration}")
    tg.append(f"        intervals: size = {len(cleaned_frames)}")
    
    for i, f in enumerate(cleaned_frames, 1):
        start = f["start_ms"] / 1000.0
        end = f["end_ms"] / 1000.0
        text = f["text"] if f["text"] else ""
        
        tg.append(f"        intervals [{i}]:")
        tg.append(f"            xmin = {start}")
        tg.append(f"            xmax = {end}")
        tg.append(f'            text = "{text}"')
    
    # ========== 4. swar tier ==========
    tg.append("    item [4]:")
    tg.append('        class = "IntervalTier"')
    tg.append('        name = "swar"')
    tg.append(f"        xmin = 0")
    tg.append(f"        xmax = {duration}")
    tg.append(f"        intervals: size = {len(cleaned_frames)}")
    
    for i, f in enumerate(cleaned_frames, 1):
        start = f["start_ms"] / 1000.0
        end = f["end_ms"] / 1000.0
        text = get_swar(f["text"]) if f["text"] else ""
        
        tg.append(f"        intervals [{i}]:")
        tg.append(f"            xmin = {start}")
        tg.append(f"            xmax = {end}")
        tg.append(f'            text = "{text}"')
    
    # ========== 5. vyanjan tier ==========
    tg.append("    item [5]:")
    tg.append('        class = "IntervalTier"')
    tg.append('        name = "vyanjan"')
    tg.append(f"        xmin = 0")
    tg.append(f"        xmax = {duration}")
    tg.append(f"        intervals: size = {len(cleaned_frames)}")
    
    for i, f in enumerate(cleaned_frames, 1):
        start = f["start_ms"] / 1000.0
        end = f["end_ms"] / 1000.0
        text = get_vyanjan(f["text"]) if f["text"] else ""
        
        tg.append(f"        intervals [{i}]:")
        tg.append(f"            xmin = {start}")
        tg.append(f"            xmax = {end}")
        tg.append(f'            text = "{text}"')
    
    # ========== 6. naasika tier ==========
    tg.append("    item [6]:")
    tg.append('        class = "IntervalTier"')
    tg.append('        name = "naasika"')
    tg.append(f"        xmin = 0")
    tg.append(f"        xmax = {duration}")
    tg.append(f"        intervals: size = {len(cleaned_frames)}")
    
    for i, f in enumerate(cleaned_frames, 1):
        start = f["start_ms"] / 1000.0
        end = f["end_ms"] / 1000.0
        text = get_naasika(f["text"]) if f["text"] else ""
        
        tg.append(f"        intervals [{i}]:")
        tg.append(f"            xmin = {start}")
        tg.append(f"            xmax = {end}")
        tg.append(f'            text = "{text}"')
    
    # ========== 7. annotator tier ==========
    tg.append("    item [7]:")
    tg.append('        class = "IntervalTier"')
    tg.append('        name = "annotator"')
    tg.append(f"        xmin = 0")
    tg.append(f"        xmax = {duration}")
    tg.append("        intervals: size = 1")
    
    tg.append("        intervals [1]:")
    tg.append(f"            xmin = 0")
    tg.append(f"            xmax = {duration}")
    tg.append(f'            text = "{annotator}"')
    
    return "\n".join(tg)


def create_enhanced_textgrid_with_tiers(frames_216, frames_108, frames_54, duration, sentence, annotator, verified_by=None):
    """
    Create TextGrid with 12 tiers for VERIFIED files (matches desktop UI)
    If verified_by is None, creates 11 tiers (for self-recorded)
    """
    tg = []
    
    tg.append('File type = "ooTextFile"')
    tg.append('Object class = "TextGrid"\n')
    
    tg.append(f"xmin = 0")
    tg.append(f"xmax = {duration}")
    tg.append("tiers? <exists>")
    
    if verified_by:
        tg.append("size = 12")
    else:
        tg.append("size = 11")
    
    tg.append("item []:")
    
    # ========== 1. sentence tier ==========
    tg.append("    item [1]:")
    tg.append('        class = "IntervalTier"')
    tg.append('        name = "sentence"')
    tg.append(f"        xmin = 0")
    tg.append(f"        xmax = {duration}")
    tg.append("        intervals: size = 1")
    tg.append("        intervals [1]:")
    tg.append(f"            xmin = 0")
    tg.append(f"            xmax = {duration}")
    tg.append(f'            text = "{sentence}"')
    
    # ========== 2. annotations tier (54ms frames) ==========
    tg.append("    item [2]:")
    tg.append('        class = "IntervalTier"')
    tg.append('        name = "annotations"')
    tg.append(f"        xmin = 0")
    tg.append(f"        xmax = {duration}")
    tg.append(f"        intervals: size = {len(frames_54)}")
    
    for i, f in enumerate(frames_54, 1):
        start = f.get("start_ms", 0) / 1000.0
        end = f.get("end_ms", 0) / 1000.0
        text = f.get("text", "") if f.get("text") else ""
        
        tg.append(f"        intervals [{i}]:")
        tg.append(f"            xmin = {start}")
        tg.append(f"            xmax = {end}")
        tg.append(f'            text = "{text}"')
    
    # ========== 3. EMPTY TIER (spacer) ==========
    tg.append("    item [3]:")
    tg.append('        class = "IntervalTier"')
    tg.append('        name = "----------"')
    tg.append(f"        xmin = 0")
    tg.append(f"        xmax = {duration}")
    tg.append("        intervals: size = 1")
    tg.append("        intervals [1]:")
    tg.append(f"            xmin = 0")
    tg.append(f"            xmax = {duration}")
    tg.append(f'            text = ""')
    
    # ========== 4. window_216ms tier ==========
    tg.append("    item [4]:")
    tg.append('        class = "IntervalTier"')
    tg.append('        name = "window_216ms"')
    tg.append(f"        xmin = 0")
    tg.append(f"        xmax = {duration}")
    tg.append(f"        intervals: size = {len(frames_216)}")
    
    for i, f in enumerate(frames_216, 1):
        start = f.get("start_ms", 0) / 1000.0
        end = f.get("end_ms", 0) / 1000.0
        text = f.get("text", "") if f.get("text") else ""
        
        tg.append(f"        intervals [{i}]:")
        tg.append(f"            xmin = {start}")
        tg.append(f"            xmax = {end}")
        tg.append(f'            text = "{text}"')
    
    # ========== 5. window_108ms tier ==========
    tg.append("    item [5]:")
    tg.append('        class = "IntervalTier"')
    tg.append('        name = "window_108ms"')
    tg.append(f"        xmin = 0")
    tg.append(f"        xmax = {duration}")
    tg.append(f"        intervals: size = {len(frames_108)}")
    
    for i, f in enumerate(frames_108, 1):
        start = f.get("start_ms", 0) / 1000.0
        end = f.get("end_ms", 0) / 1000.0
        text = f.get("text", "") if f.get("text") else ""
        
        tg.append(f"        intervals [{i}]:")
        tg.append(f"            xmin = {start}")
        tg.append(f"            xmax = {end}")
        tg.append(f'            text = "{text}"')
    
    # ========== 6. window_54ms tier ==========
    tg.append("    item [6]:")
    tg.append('        class = "IntervalTier"')
    tg.append('        name = "window_54ms"')
    tg.append(f"        xmin = 0")
    tg.append(f"        xmax = {duration}")
    tg.append(f"        intervals: size = {len(frames_54)}")
    
    for i, f in enumerate(frames_54, 1):
        start = f.get("start_ms", 0) / 1000.0
        end = f.get("end_ms", 0) / 1000.0
        text = f.get("text", "") if f.get("text") else ""
        
        tg.append(f"        intervals [{i}]:")
        tg.append(f"            xmin = {start}")
        tg.append(f"            xmax = {end}")
        tg.append(f'            text = "{text}"')
    
    # ========== 7. EMPTY TIER (spacer) ==========
    tg.append("    item [7]:")
    tg.append('        class = "IntervalTier"')
    tg.append('        name = "----------"')
    tg.append(f"        xmin = 0")
    tg.append(f"        xmax = {duration}")
    tg.append("        intervals: size = 1")
    tg.append("        intervals [1]:")
    tg.append(f"            xmin = 0")
    tg.append(f"            xmax = {duration}")
    tg.append(f'            text = ""')
    
    # ========== 8. swar tier ==========
    tg.append("    item [8]:")
    tg.append('        class = "IntervalTier"')
    tg.append('        name = "swar"')
    tg.append(f"        xmin = 0")
    tg.append(f"        xmax = {duration}")
    tg.append(f"        intervals: size = {len(frames_108)}")
    
    for i, f in enumerate(frames_108, 1):
        start = f.get("start_ms", 0) / 1000.0
        end = f.get("end_ms", 0) / 1000.0
        text = get_swar(f.get("text", "")) if f.get("text") else ""
        
        tg.append(f"        intervals [{i}]:")
        tg.append(f"            xmin = {start}")
        tg.append(f"            xmax = {end}")
        tg.append(f'            text = "{text}"')
    
    # ========== 9. vyanjan tier ==========
    tg.append("    item [9]:")
    tg.append('        class = "IntervalTier"')
    tg.append('        name = "vyanjan"')
    tg.append(f"        xmin = 0")
    tg.append(f"        xmax = {duration}")
    tg.append(f"        intervals: size = {len(frames_108)}")
    
    for i, f in enumerate(frames_108, 1):
        start = f.get("start_ms", 0) / 1000.0
        end = f.get("end_ms", 0) / 1000.0
        text = get_vyanjan(f.get("text", "")) if f.get("text") else ""
        
        tg.append(f"        intervals [{i}]:")
        tg.append(f"            xmin = {start}")
        tg.append(f"            xmax = {end}")
        tg.append(f'            text = "{text}"')
    
    # ========== 10. naasika tier ==========
    tg.append("    item [10]:")
    tg.append('        class = "IntervalTier"')
    tg.append('        name = "naasika"')
    tg.append(f"        xmin = 0")
    tg.append(f"        xmax = {duration}")
    tg.append(f"        intervals: size = {len(frames_108)}")
    
    for i, f in enumerate(frames_108, 1):
        start = f.get("start_ms", 0) / 1000.0
        end = f.get("end_ms", 0) / 1000.0
        text = get_naasika(f.get("text", "")) if f.get("text") else ""
        
        tg.append(f"        intervals [{i}]:")
        tg.append(f"            xmin = {start}")
        tg.append(f"            xmax = {end}")
        tg.append(f'            text = "{text}"')
    
    # ========== 11. annotator tier ==========
    tg.append("    item [11]:")
    tg.append('        class = "IntervalTier"')
    tg.append('        name = "annotator"')
    tg.append(f"        xmin = 0")
    tg.append(f"        xmax = {duration}")
    tg.append("        intervals: size = 1")
    tg.append("        intervals [1]:")
    tg.append(f"            xmin = 0")
    tg.append(f"            xmax = {duration}")
    tg.append(f'            text = "{annotator}"')
    
    # ========== 12. verified_by tier (only if provided) ==========
    if verified_by:
        tg.append("    item [12]:")
        tg.append('        class = "IntervalTier"')
        tg.append('        name = "verified_by"')
        tg.append(f"        xmin = 0")
        tg.append(f"        xmax = {duration}")
        tg.append("        intervals: size = 1")
        tg.append("        intervals [1]:")
        tg.append(f"            xmin = 0")
        tg.append(f"            xmax = {duration}")
        tg.append(f'            text = "{verified_by}"')
    
    return "\n".join(tg)


def create_live_stream_textgrid_with_speaker_gender(frames_216, frames_108, frames_54, duration, sentence, annotator, speaker_intervals, gender_intervals):
    """
    Create TextGrid for live stream files with 13 tiers:
    - sentence
    - annotations (54ms frames)
    - spacer
    - window_216ms
    - window_108ms
    - window_54ms
    - spacer
    - swar (from window_108ms)
    - vyanjan (from window_108ms)
    - naasika (from window_108ms)
    - annotator
    - speaker_id (merged intervals from user input)
    - gender_id (merged intervals from user input)
    """
    tg = []
    
    tg.append('File type = "ooTextFile"')
    tg.append('Object class = "TextGrid"\n')
    tg.append(f"xmin = 0")
    tg.append(f"xmax = {duration}")
    tg.append("tiers? <exists>")
    tg.append("size = 13")
    tg.append("item []:")
    
    # 1. sentence tier
    tg.append("    item [1]:")
    tg.append('        class = "IntervalTier"')
    tg.append('        name = "sentence"')
    tg.append(f"        xmin = 0")
    tg.append(f"        xmax = {duration}")
    tg.append("        intervals: size = 1")
    tg.append("        intervals [1]:")
    tg.append(f"            xmin = 0")
    tg.append(f"            xmax = {duration}")
    safe_sentence = sentence.replace('"', '\\"') if sentence else ""
    tg.append(f'            text = "{safe_sentence}"')
    
    # 2. annotations tier (54ms frames)
    tg.append("    item [2]:")
    tg.append('        class = "IntervalTier"')
    tg.append('        name = "annotations"')
    tg.append(f"        xmin = 0")
    tg.append(f"        xmax = {duration}")
    tg.append(f"        intervals: size = {len(frames_54)}")
    for i, f in enumerate(frames_54, 1):
        start = f.get("start_ms", 0) / 1000.0
        end = f.get("end_ms", 0) / 1000.0
        text = (f.get("text", "") or "").replace('"', '\\"')
        tg.append(f"        intervals [{i}]:")
        tg.append(f"            xmin = {start}")
        tg.append(f"            xmax = {end}")
        tg.append(f'            text = "{text}"')
    
    # 3. spacer
    tg.append("    item [3]:")
    tg.append('        class = "IntervalTier"')
    tg.append('        name = "----------"')
    tg.append(f"        xmin = 0")
    tg.append(f"        xmax = {duration}")
    tg.append("        intervals: size = 1")
    tg.append("        intervals [1]:")
    tg.append(f"            xmin = 0")
    tg.append(f"            xmax = {duration}")
    tg.append(f'            text = ""')
    
    # 4. window_216ms tier
    tg.append("    item [4]:")
    tg.append('        class = "IntervalTier"')
    tg.append('        name = "window_216ms"')
    tg.append(f"        xmin = 0")
    tg.append(f"        xmax = {duration}")
    tg.append(f"        intervals: size = {len(frames_216)}")
    for i, f in enumerate(frames_216, 1):
        start = f.get("start_ms", 0) / 1000.0
        end = f.get("end_ms", 0) / 1000.0
        text = (f.get("text", "") or "").replace('"', '\\"')
        tg.append(f"        intervals [{i}]:")
        tg.append(f"            xmin = {start}")
        tg.append(f"            xmax = {end}")
        tg.append(f'            text = "{text}"')
    
    # 5. window_108ms tier
    tg.append("    item [5]:")
    tg.append('        class = "IntervalTier"')
    tg.append('        name = "window_108ms"')
    tg.append(f"        xmin = 0")
    tg.append(f"        xmax = {duration}")
    tg.append(f"        intervals: size = {len(frames_108)}")
    for i, f in enumerate(frames_108, 1):
        start = f.get("start_ms", 0) / 1000.0
        end = f.get("end_ms", 0) / 1000.0
        text = (f.get("text", "") or "").replace('"', '\\"')
        tg.append(f"        intervals [{i}]:")
        tg.append(f"            xmin = {start}")
        tg.append(f"            xmax = {end}")
        tg.append(f'            text = "{text}"')
    
    # 6. window_54ms tier
    tg.append("    item [6]:")
    tg.append('        class = "IntervalTier"')
    tg.append('        name = "window_54ms"')
    tg.append(f"        xmin = 0")
    tg.append(f"        xmax = {duration}")
    tg.append(f"        intervals: size = {len(frames_54)}")
    for i, f in enumerate(frames_54, 1):
        start = f.get("start_ms", 0) / 1000.0
        end = f.get("end_ms", 0) / 1000.0
        text = (f.get("text", "") or "").replace('"', '\\"')
        tg.append(f"        intervals [{i}]:")
        tg.append(f"            xmin = {start}")
        tg.append(f"            xmax = {end}")
        tg.append(f'            text = "{text}"')
    
    # 7. spacer
    tg.append("    item [7]:")
    tg.append('        class = "IntervalTier"')
    tg.append('        name = "----------"')
    tg.append(f"        xmin = 0")
    tg.append(f"        xmax = {duration}")
    tg.append("        intervals: size = 1")
    tg.append("        intervals [1]:")
    tg.append(f"            xmin = 0")
    tg.append(f"            xmax = {duration}")
    tg.append(f'            text = ""')
    
    # 8. swar tier (from window_108ms)
    tg.append("    item [8]:")
    tg.append('        class = "IntervalTier"')
    tg.append('        name = "swar"')
    tg.append(f"        xmin = 0")
    tg.append(f"        xmax = {duration}")
    tg.append(f"        intervals: size = {len(frames_108)}")
    for i, f in enumerate(frames_108, 1):
        start = f.get("start_ms", 0) / 1000.0
        end = f.get("end_ms", 0) / 1000.0
        text = get_swar(f.get("text", "")) if f.get("text") else ""
        tg.append(f"        intervals [{i}]:")
        tg.append(f"            xmin = {start}")
        tg.append(f"            xmax = {end}")
        tg.append(f'            text = "{text}"')
    
    # 9. vyanjan tier
    tg.append("    item [9]:")
    tg.append('        class = "IntervalTier"')
    tg.append('        name = "vyanjan"')
    tg.append(f"        xmin = 0")
    tg.append(f"        xmax = {duration}")
    tg.append(f"        intervals: size = {len(frames_108)}")
    for i, f in enumerate(frames_108, 1):
        start = f.get("start_ms", 0) / 1000.0
        end = f.get("end_ms", 0) / 1000.0
        text = get_vyanjan(f.get("text", "")) if f.get("text") else ""
        tg.append(f"        intervals [{i}]:")
        tg.append(f"            xmin = {start}")
        tg.append(f"            xmax = {end}")
        tg.append(f'            text = "{text}"')
    
    # 10. naasika tier
    tg.append("    item [10]:")
    tg.append('        class = "IntervalTier"')
    tg.append('        name = "naasika"')
    tg.append(f"        xmin = 0")
    tg.append(f"        xmax = {duration}")
    tg.append(f"        intervals: size = {len(frames_108)}")
    for i, f in enumerate(frames_108, 1):
        start = f.get("start_ms", 0) / 1000.0
        end = f.get("end_ms", 0) / 1000.0
        text = get_naasika(f.get("text", "")) if f.get("text") else ""
        tg.append(f"        intervals [{i}]:")
        tg.append(f"            xmin = {start}")
        tg.append(f"            xmax = {end}")
        tg.append(f'            text = "{text}"')
    
    # 11. annotator tier
    tg.append("    item [11]:")
    tg.append('        class = "IntervalTier"')
    tg.append('        name = "annotator"')
    tg.append(f"        xmin = 0")
    tg.append(f"        xmax = {duration}")
    tg.append("        intervals: size = 1")
    tg.append("        intervals [1]:")
    tg.append(f"            xmin = 0")
    tg.append(f"            xmax = {duration}")
    tg.append(f'            text = "{annotator}"')
    
    # 12. speaker_id tier (merged intervals)
    tg.append("    item [12]:")
    tg.append('        class = "IntervalTier"')
    tg.append('        name = "speaker_id"')
    tg.append(f"        xmin = 0")
    tg.append(f"        xmax = {duration}")
    if speaker_intervals:
        tg.append(f"        intervals: size = {len(speaker_intervals)}")
        for i, interval in enumerate(speaker_intervals, 1):
            start = interval['start_time']
            end = interval['end_time']
            text = interval['text'].replace('"', '\\"')
            tg.append(f"        intervals [{i}]:")
            tg.append(f"            xmin = {start}")
            tg.append(f"            xmax = {end}")
            tg.append(f'            text = "{text}"')
    else:
        tg.append("        intervals: size = 1")
        tg.append("        intervals [1]:")
        tg.append(f"            xmin = 0")
        tg.append(f"            xmax = {duration}")
        tg.append(f'            text = ""')
    
    # 13. gender_id tier (merged intervals)
    tg.append("    item [13]:")
    tg.append('        class = "IntervalTier"')
    tg.append('        name = "gender_id"')
    tg.append(f"        xmin = 0")
    tg.append(f"        xmax = {duration}")
    if gender_intervals:
        tg.append(f"        intervals: size = {len(gender_intervals)}")
        for i, interval in enumerate(gender_intervals, 1):
            start = interval['start_time']
            end = interval['end_time']
            text = interval['text'].replace('"', '\\"')
            tg.append(f"        intervals [{i}]:")
            tg.append(f"            xmin = {start}")
            tg.append(f"            xmax = {end}")
            tg.append(f'            text = "{text}"')
    else:
        tg.append("        intervals: size = 1")
        tg.append("        intervals [1]:")
        tg.append(f"            xmin = 0")
        tg.append(f"            xmax = {duration}")
        tg.append(f'            text = ""')
    
    return "\n".join(tg)


def merge_frames_to_intervals(frames, total_duration, window_size):
    """
    Merge continuous frames with same value into intervals.
    frames: list of dicts with 'index' and 'text'
    returns: list of intervals with start_time, end_time, text
    """
    if not frames:
        return []
    
    # Create a full array of values indexed by frame number
    max_index = max([f.get('index', 0) for f in frames]) if frames else int(total_duration / window_size)
    
    # Build value array
    values = [''] * (max_index + 1)
    for f in frames:
        idx = f.get('index', 0)
        value = f.get('text', '')
        if idx < len(values):
            values[idx] = value
    
    # Merge consecutive identical values
    intervals = []
    current_start = 0
    current_value = values[0] if values else ''
    
    for i in range(1, len(values)):
        if values[i] != current_value:
            # End of current interval
            if current_value:  # Only add if non-empty
                intervals.append({
                    'start_time': current_start * window_size,
                    'end_time': i * window_size,
                    'text': current_value
                })
            current_start = i
            current_value = values[i]
    
    # Add last interval
    if current_value:
        intervals.append({
            'start_time': current_start * window_size,
            'end_time': len(values) * window_size,
            'text': current_value
        })
    
    return intervals


# ============= LIVE STREAM FUNCTIONS =============

NEWS_STREAMS = {
    'hi': [
        'https://aajtakhdlive-amd.akamaized.net/hls/live/2014415/aajtakhd/aajtakhdlive/live_720p/chunks.m3u8',
        'https://abp-i.akamaihd.net/hls/live/765529/abphindi/masterhls_1564.m3u8',
        'https://ndtvindiaelemarchana.akamaized.net/hls/live/2003679/ndtvindia/master.m3u8',
        'https://d3qs3d2rkhfqrt.cloudfront.net/out/v1/6cd2f649739a45ca9de1daf81cc7d0f2/index.m3u8',
        'https://live.wmncdn.net/firstindianewstv1/live.stream/tracks-v1a1/mono.m3u8',
    ],
    'te': [
        'https://dyjmyiv3bp2ez.cloudfront.net/pub-iotv9telcmjhcs/liveabr/playlist.m3u8',
        'https://yuppmedtaorire.akamaized.net/v1/master/a0d007312bfd99c47f76b77ae26b1ccdaae76cb1/v6news_nim_https/140622/v6news/playlist.m3u8',
        'http://103.199.161.254/Content/tv9telungu/Live/Channel(TV9Telungu)/index.m3u8',
        'http://103.199.161.254/Content/tv9telungu/Live/Channel(TV9Telungu)/Stream(04)/index.m3u8',
        'https://live.wmncdn.net/ntvtelugu/live.stream/tracks-v1a1/mono.m3u8',
    ],
    'ta': [
        'https://d35j504z0x2vu2.cloudfront.net/v1/master/0bc8e8376bd8417a1b6761138aa41c26c7309312/news-tamil-24x7/index.m3u8',
        'https://932y483pdjv8-hls-live.5centscdn.com/stream/deb10bae362f810630ec3abedcae5894.sdp/playlist.m3u8',
        'http://103.199.160.85/Content/kalaignarseithikal/Live/Channel(KalaignarSeithikal)/index.m3u8',
        'http://5k8q87azdy4v-hls-live.wmncdn.net/MAKKAL/271ddf829afeece44d8732757fba1a66.sdp/tracks-v1a1/mono.m3u8',
        'https://6n3yope4d9ok-hls-live.5centscdn.com/vaanavil/TV.stream/playlist.m3u8',
    ],
    'bn': [
        'https://abp-i.akamaihd.net/hls/live/765530/abpananda/masterhls_1564.m3u8',
        'https://bk7l298nyx53-hls-live.5centscdn.com/realnews/e7dee419f91aa9e65939d3677fb9c4f5.sdp/playlist.m3u8',
        'https://live.wmncdn.net/news18bangla/live.stream/tracks-v1a1/mono.m3u8',
        'https://7mbd4ogkr3gx-hls-live.wmncdn.net/harvesttvlive1/bbb19eae240ec100af921d511efc86a0.sdp/index.m3u8',
    ],
    'gu': [
        'https://abp-i.akamaihd.net/hls/live/765532/abpasmita/masterhls_1564.m3u8',
        'https://live.wmncdn.net/sandesh/live.stream/tracks-v1a1/mono.m3u8',
        'http://103.199.161.254/Content/vtv/Live/Channel(VTV)/index.m3u8',
        'http://cshms3.airtel.tv/wh7f454c46tw4163224253_611767333/PLTV/88888888/224/3221226113/index.m3u8',
    ],
    'mr': [
        'https://abp-i.akamaihd.net/hls/live/765531/abpmajha/masterhls_1564.m3u8',
        'http://mhms9.airtel.tv/wh7f454c46tw4163224253_611767333/PLTV/88888888/224/3221226370/index.m3u8',
        'https://live.wmncdn.net/zee24taas/live.stream/tracks-v1a1/mono.m3u8',
    ],
}

def fetch_live_audio_chunk(stream_urls, duration_seconds=2, lang=None):
    if isinstance(stream_urls, str):
        stream_urls = [stream_urls]

    MIN_BYTES = 8_000
    LIVE_FLAGS = [
        '-reconnect', '1',
        '-reconnect_streamed', '1',
        '-reconnect_delay_max', '3',
        '-timeout', '10000000',
        '-fflags', '+discardcorrupt',
        '-analyzeduration', '2000000',
        '-probesize', '1000000',
    ]

    for attempt, url in enumerate(stream_urls):
        tmp_path = None
        try:
            print(f"[live] attempt {attempt+1}/{len(stream_urls)}: {url[:90]}")
            import tempfile
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp:
                tmp_path = tmp.name

            cmd = (['ffmpeg'] + LIVE_FLAGS + ['-i', url, '-t', str(duration_seconds), '-vn', '-acodec', 'pcm_s16le', '-ar', '16000', '-ac', '1', '-y', tmp_path])

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=duration_seconds + 25)

            if os.path.exists(tmp_path):
                size = os.path.getsize(tmp_path)
                if size >= MIN_BYTES:
                    with open(tmp_path, 'rb') as f:
                        wav_bytes = f.read()
                    os.unlink(tmp_path)
                    print(f"[live] ✓ {size:,} bytes — stream {attempt+1} succeeded")
                    return wav_bytes
                else:
                    print(f"[live] too small: {size} bytes (rc={result.returncode})")
                    os.unlink(tmp_path)
            else:
                print(f"[live] no output — rc={result.returncode}")
        except subprocess.TimeoutExpired:
            print(f"[live] timeout — stream {attempt+1}")
            try:
                if tmp_path and os.path.exists(tmp_path):
                    os.unlink(tmp_path)
            except:
                pass
        except Exception as exc:
            print(f"[live] error — stream {attempt+1}: {exc}")
            try:
                if tmp_path and os.path.exists(tmp_path):
                    os.unlink(tmp_path)
            except:
                pass

    print("[live] all streams failed — returning silent audio")
    return generate_silent_audio(duration_seconds)

def generate_silent_audio(duration_seconds=2, sample_rate=16000):
    import struct
    num_samples = int(sample_rate * duration_seconds)
    data_size = num_samples * 2
    riff_size = 36 + data_size
    header = struct.pack('<4sI4s', b'RIFF', riff_size, b'WAVE')
    header += struct.pack('<4sIHHIIHH', b'fmt ', 16, 1, 1, sample_rate, sample_rate * 2, 2, 16)
    header += struct.pack('<4sI', b'data', data_size)
    return header + b'\x00\x00' * num_samples

def fetch_live_video_segment(stream_urls, duration_seconds=2):
    """
    Fetch live video segment from HLS streams
    Returns video bytes in MP4 format, or None if failed.
    """
    for attempt, stream_url in enumerate(stream_urls):
        tmp_path = None
        try:
            print(f"[Video] Trying HLS stream {attempt+1}/{len(stream_urls)}: {stream_url[:80]}...")

            with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as tmp:
                tmp_path = tmp.name

            timeout_seconds = duration_seconds + 30
            
            cmd = [
                'ffmpeg',
                '-i', stream_url,
                '-t', str(duration_seconds),
                '-c:v', 'libx264',
                '-c:a', 'aac',
                '-movflags', '+faststart',
                '-y',
                tmp_path
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_seconds)

            if result.returncode != 0:
                if tmp_path and os.path.exists(tmp_path):
                    os.unlink(tmp_path)
                continue

            with open(tmp_path, 'rb') as f:
                video_bytes = f.read()

            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)

            if len(video_bytes) >= 8 and video_bytes[4:8] == b'ftyp':
                print(f"[Video] ✓ HLS stream {attempt+1} succeeded! Got {len(video_bytes)} bytes")
                return video_bytes

        except subprocess.TimeoutExpired:
            print(f"[Video] Timeout for HLS stream {attempt+1}")
            if tmp_path and os.path.exists(tmp_path):
                try: os.unlink(tmp_path)
                except: pass
            continue
        except Exception as e:
            print(f"[Video] Error on HLS stream {attempt+1}: {e}")
            continue
    
    print("[Video] All video streams failed")
    return None

def get_stream_urls_for_lang(lang):
    return NEWS_STREAMS.get(lang, NEWS_STREAMS['hi'])


# ==============================
# SESSION MANAGEMENT FUNCTIONS
# ==============================

def get_user_live_session_folder(username):
    """Get user-specific folder for live session files"""
    user_folder = os.path.join(LIVE_AUDIO_CACHE_FOLDER, username)
    os.makedirs(user_folder, exist_ok=True)
    return user_folder


# ==============================
# LOAD/SAVE FUNCTIONS
# ==============================

# Load users
def load_users():
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_users(users):
    with open(USERS_FILE, 'w') as f:
        json.dump(users, f, indent=2)

# Load or create completed files log
def load_completed_files():
    if os.path.exists(COMPLETED_LOG):
        with open(COMPLETED_LOG, 'r') as f:
            return set(json.load(f))
    return set()

def save_completed_files(completed_set):
    with open(COMPLETED_LOG, 'w') as f:
        json.dump(list(completed_set), f, indent=2)

completed_files = load_completed_files()

# Skipped Files Tracking
def load_skipped_files():
    if os.path.exists(SKIPPED_FILES_FILE):
        with open(SKIPPED_FILES_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_skipped_files(skipped):
    with open(SKIPPED_FILES_FILE, 'w') as f:
        json.dump(skipped, f, indent=2)

def add_skipped_file(username, json_file):
    skipped = load_skipped_files()
    if username not in skipped:
        skipped[username] = []
    if json_file not in skipped[username]:
        skipped[username].append(json_file)
    save_skipped_files(skipped)

def get_skipped_files(username):
    skipped = load_skipped_files()
    return skipped.get(username, [])

def clear_skipped_file(username, json_file):
    skipped = load_skipped_files()
    if username in skipped and json_file in skipped[username]:
        skipped[username].remove(json_file)
        save_skipped_files(skipped)

# File Assignment Tracking
def load_file_assignments():
    if os.path.exists(FILE_ASSIGNMENTS_FILE):
        with open(FILE_ASSIGNMENTS_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_file_assignments(assignments):
    with open(FILE_ASSIGNMENTS_FILE, 'w') as f:
        json.dump(assignments, f, indent=2)

def load_user_stats():
    if os.path.exists(USER_STATS_FILE):
        with open(USER_STATS_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_user_stats(stats):
    with open(USER_STATS_FILE, 'w') as f:
        json.dump(stats, f, indent=2)

def update_user_stats(username, json_file, duration_seconds, increment=True):
    stats = load_user_stats()
    
    if username not in stats:
        stats[username] = {
            "completed_files": [],
            "total_files_completed": 0,
            "total_duration_seconds": 0,
            "total_duration_formatted": "0s",
            "last_active": None
        }
    
    if increment:
        if json_file not in stats[username]["completed_files"]:
            stats[username]["completed_files"].append(json_file)
            stats[username]["total_files_completed"] += 1
            stats[username]["total_duration_seconds"] += duration_seconds
    else:
        # decrement (for rejection)
        if json_file in stats[username]["completed_files"]:
            stats[username]["completed_files"].remove(json_file)
            stats[username]["total_files_completed"] -= 1
            stats[username]["total_duration_seconds"] -= duration_seconds
            if stats[username]["total_duration_seconds"] < 0:
                stats[username]["total_duration_seconds"] = 0
            if stats[username]["total_files_completed"] < 0:
                stats[username]["total_files_completed"] = 0
    
    total_secs = stats[username]["total_duration_seconds"]
    if total_secs < 60:
        stats[username]["total_duration_formatted"] = f"{total_secs:.1f}s"
    elif total_secs < 3600:
        mins = int(total_secs // 60)
        secs = int(total_secs % 60)
        stats[username]["total_duration_formatted"] = f"{mins}m {secs}s"
    else:
        hours = int(total_secs // 3600)
        mins = int((total_secs % 3600) // 60)
        stats[username]["total_duration_formatted"] = f"{hours}h {mins}m"
    
    stats[username]["last_active"] = datetime.now().isoformat()
    save_user_stats(stats)
    return stats[username]

def get_user_stats(username):
    stats = load_user_stats()
    return stats.get(username, {
        "completed_files": [],
        "total_files_completed": 0,
        "total_duration_seconds": 0,
        "total_duration_formatted": "0s",
        "last_active": None
    })

def load_daily_stats():
    if os.path.exists(DAILY_STATS_FILE):
        with open(DAILY_STATS_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_daily_stats(stats):
    with open(DAILY_STATS_FILE, 'w') as f:
        json.dump(stats, f, indent=2)

def update_daily_stats(username, json_file, duration_seconds, increment=True):
    today = datetime.now().strftime("%Y-%m-%d")
    daily_stats = load_daily_stats()
    
    if username not in daily_stats:
        daily_stats[username] = {
            "total": {
                "files_completed": 0,
                "duration_seconds": 0,
                "duration_formatted": "0s"
            },
            "daily": {}
        }
    
    if today not in daily_stats[username]["daily"]:
        daily_stats[username]["daily"][today] = {
            "files_completed": 0,
            "duration_seconds": 0,
            "duration_formatted": "0s",
            "files": []
        }
    
    if increment:
        if json_file not in daily_stats[username]["daily"][today]["files"]:
            daily_stats[username]["daily"][today]["files_completed"] += 1
            daily_stats[username]["daily"][today]["duration_seconds"] += duration_seconds
            daily_stats[username]["daily"][today]["files"].append(json_file)
            daily_stats[username]["total"]["files_completed"] += 1
            daily_stats[username]["total"]["duration_seconds"] += duration_seconds
    else:
        # decrement: remove from today's stats if present
        if json_file in daily_stats[username]["daily"][today]["files"]:
            daily_stats[username]["daily"][today]["files_completed"] -= 1
            daily_stats[username]["daily"][today]["duration_seconds"] -= duration_seconds
            daily_stats[username]["daily"][today]["files"].remove(json_file)
            daily_stats[username]["total"]["files_completed"] -= 1
            daily_stats[username]["total"]["duration_seconds"] -= duration_seconds
            if daily_stats[username]["daily"][today]["files_completed"] < 0:
                daily_stats[username]["daily"][today]["files_completed"] = 0
            if daily_stats[username]["daily"][today]["duration_seconds"] < 0:
                daily_stats[username]["daily"][today]["duration_seconds"] = 0
            if daily_stats[username]["total"]["files_completed"] < 0:
                daily_stats[username]["total"]["files_completed"] = 0
            if daily_stats[username]["total"]["duration_seconds"] < 0:
                daily_stats[username]["total"]["duration_seconds"] = 0
    
    # Format durations
    for key in ['daily', 'total']:
        if key == 'daily':
            for date, data in daily_stats[username]['daily'].items():
                secs = data['duration_seconds']
                if secs < 60:
                    data['duration_formatted'] = f"{secs:.1f}s"
                elif secs < 3600:
                    mins = int(secs // 60)
                    secs_rem = int(secs % 60)
                    data['duration_formatted'] = f"{mins}m {secs_rem}s"
                else:
                    hours = int(secs // 3600)
                    mins = int((secs % 3600) // 60)
                    data['duration_formatted'] = f"{hours}h {mins}m"
        else:
            secs = daily_stats[username]['total']['duration_seconds']
            if secs < 60:
                daily_stats[username]['total']['duration_formatted'] = f"{secs:.1f}s"
            elif secs < 3600:
                mins = int(secs // 60)
                secs_rem = int(secs % 60)
                daily_stats[username]['total']['duration_formatted'] = f"{mins}m {secs_rem}s"
            else:
                hours = int(secs // 3600)
                mins = int((secs % 3600) // 60)
                daily_stats[username]['total']['duration_formatted'] = f"{hours}h {mins}m"
    
    save_daily_stats(daily_stats)
    return daily_stats[username]

def get_user_daily_stats(username):
    daily_stats = load_daily_stats()
    if username in daily_stats:
        return daily_stats[username]
    return {
        "total": {
            "files_completed": 0,
            "duration_seconds": 0,
            "duration_formatted": "0s"
        },
        "daily": {}
    }

def assign_file_to_user(username):
    file_assignments = load_file_assignments()
    user_stats = get_user_stats(username)
    completed_by_user = set(user_stats.get("completed_files", []))
    skipped_by_user = set(get_skipped_files(username))
    
    all_json_files = glob.glob(os.path.join(AUDIO_FOLDER, "*.json"))
    available_files = []
    
    for json_path in all_json_files:
        base_name = os.path.basename(json_path)
        wav_name = base_name.replace('.json', '.wav')
        wav_path = os.path.join(AUDIO_FOLDER, wav_name)
        
        if os.path.exists(wav_path):
            if base_name in completed_files:
                continue
            if base_name in skipped_by_user:
                continue
            if base_name in file_assignments:
                assignment = file_assignments[base_name]
                assigned_time = datetime.fromisoformat(assignment["assigned_at"])
                if datetime.now().timestamp() - assigned_time.timestamp() > 1800:
                    pass
                elif assignment["assigned_to"] != username:
                    continue
            if base_name in completed_by_user:
                continue
            available_files.append(base_name)
    
    if not available_files:
        return None
    
    assigned_file = available_files[0]
    file_assignments[assigned_file] = {
        "assigned_to": username,
        "assigned_at": datetime.now().isoformat(),
        "status": "assigned"
    }
    save_file_assignments(file_assignments)
    return assigned_file

def release_file_assignment(json_file):
    file_assignments = load_file_assignments()
    if json_file in file_assignments:
        del file_assignments[json_file]
        save_file_assignments(file_assignments)

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session:
            return jsonify({
                "error": "Please login first", 
                "redirect": url_for_path("login")
            }), 401
        return f(*args, **kwargs)
    return decorated_function

def verifier_login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('verifier'):
            return jsonify({"error": "Verifier access required", "redirect": url_for_path("verify/login")}), 401
        return f(*args, **kwargs)
    return decorated_function

def get_audio_length(file_path):
    try:
        with wave.open(file_path, 'rb') as wf:
            frames = wf.getnframes()
            rate = wf.getframerate()
            duration = frames / float(rate)
            return int(duration * 1000)
    except:
        return 5000

def load_json_data(json_file):
    json_path = os.path.join(AUDIO_FOLDER, json_file)
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading {json_file}: {e}")
        return None

def get_user_annotation_dir(username):
    """Get or create user's annotation directory"""
    user_dir = os.path.join(USER_SUBMISSIONS_FOLDER, username)
    os.makedirs(user_dir, exist_ok=True)
    return user_dir

def save_to_mobile_dataset(annotated_data, username, original_wav_path, json_filename, verified=False):
    try:
        base_name = json_filename.replace('.json', '')
        # Determine target folder
        target_folder = MOBILE_VERIFIED_FOLDER if verified else MOBILE_DATASET_FOLDER
        
        json_output_path = os.path.join(target_folder, json_filename)
        with open(json_output_path, 'w', encoding='utf-8') as f:
            json.dump(annotated_data, f, indent=2, ensure_ascii=False)
        
        wav_filename = f"{base_name}.wav"
        wav_output_path = None
        if original_wav_path and os.path.exists(original_wav_path):
            wav_output_path = os.path.join(target_folder, wav_filename)
            shutil.copy2(original_wav_path, wav_output_path)
        
        # Check if data has frames_54 (3-tier) or frames (single tier)
        if 'frames_54' in annotated_data:
            frames_216 = annotated_data.get('frames_216', [])
            frames_108 = annotated_data.get('frames_108', [])
            frames_54 = annotated_data.get('frames_54', [])
            duration = annotated_data.get('duration_ms', 0) / 1000.0
            sentence = annotated_data.get('sentence', '')
            annotator = annotated_data.get('annotator', username)
            verified_by = annotated_data.get('verified_by', None)
            
            # Check if speaker and gender frames exist
            speaker_frames = annotated_data.get('speaker_frames', [])
            gender_frames = annotated_data.get('gender_frames', [])
            
            if speaker_frames or gender_frames:
                # Use 13-tier TextGrid with speaker/gender
                merged_speaker = merge_frames_to_intervals(speaker_frames, duration, 0.216)
                merged_gender = merge_frames_to_intervals(gender_frames, duration, 0.216)
                textgrid_content = create_live_stream_textgrid_with_speaker_gender(
                    frames_216=frames_216,
                    frames_108=frames_108,
                    frames_54=frames_54,
                    duration=duration,
                    sentence=sentence,
                    annotator=annotator,
                    speaker_intervals=merged_speaker,
                    gender_intervals=merged_gender
                )
            else:
                # Use 12-tier TextGrid for regular 3-tier
                textgrid_content = create_enhanced_textgrid_with_tiers(
                    frames_216=frames_216,
                    frames_108=frames_108,
                    frames_54=frames_54,
                    duration=duration,
                    sentence=sentence,
                    annotator=annotator,
                    verified_by=verified_by
                )
        else:
            frames = annotated_data.get('frames', [])
            duration = annotated_data.get('duration_ms', 0) / 1000.0
            if duration == 0 and frames:
                duration = frames[-1].get('end_ms', 0) / 1000.0
            sentence = annotated_data.get('sentence', '')
            full_sequence = annotated_data.get('full_sequence', '')
            annotator = annotated_data.get('annotator', username)
            
            # Use 7-tier TextGrid for single tier annotations
            textgrid_content = create_enhanced_textgrid(
                frames=frames,
                duration=duration,
                sentence=sentence,
                annotator=annotator,
                full_sequence=full_sequence
            )
        
        textgrid_output_path = os.path.join(target_folder, f"{base_name}.TextGrid")
        with open(textgrid_output_path, 'w', encoding='utf-8') as f:
            f.write(textgrid_content)
        
        print(f"Saved annotated data to {target_folder}: {base_name}")
        
        # =========================
        # 🔥 SAVE TO MOBILE TRAINING DATA FOLDER
        # =========================
        try:
            save_to_mobile_training_data(
                audio_source_path=wav_output_path if wav_output_path else original_wav_path,
                textgrid_source_path=textgrid_output_path,
                json_source_path=json_output_path,
                base_filename=base_name
            )
        except Exception as e:
            print(f"Warning: Mobile training data save failed: {e}")
        
        return True
    except Exception as e:
        print(f"Error saving to dataset: {e}")
        return False


# ============= ANNOTATION ROUTES =============

@app.route("/")
def index():
    if 'username' in session:
        return render_template("index.html", username=session['username'], base_path=BASE_PATH)
    return redirect(url_for_path("login"))

@app.route("/self-record")
@login_required
def self_record_page():
    """Self recording and annotation page for mobile"""
    return render_template("self_record.html", 
                         username=session.get('username'),
                         base_path=BASE_PATH)

@app.route("/live-stream")
@login_required
def live_stream_page():
    """Live streaming annotation page - real-time news clips"""
    return render_template("live_stream.html", 
                         username=session.get('username'),
                         base_path=BASE_PATH)

@app.route("/login")
def login_page():
    return render_template("login.html", base_path=BASE_PATH)

@app.route("/register")
def register_page():
    return render_template("register.html", base_path=BASE_PATH)

@app.route("/stats")
@login_required
def stats_page():
    return render_template("stats.html", base_path=BASE_PATH)

@app.route("/api/register", methods=["POST"])
def api_register():
    data = request.json
    username = data.get('username', '').strip()
    phone = data.get('phone', '').strip()
    password = data.get('password', '').strip()
    company_password = data.get('company_password', '').strip()
    COMPANY_MASTER_PASSWORD = "admin123"
    users = load_users()
    if not username or not phone or not password or not company_password:
        return jsonify({"error": "All fields are required"}), 400
    if username in users:
        return jsonify({"error": "Username already exists"}), 400
    if not username.replace('_', '').isalnum():
        return jsonify({"error": "Username can only contain letters, numbers, and underscore"}), 400
    if not phone.isdigit() or len(phone) != 10:
        return jsonify({"error": "Phone number must be exactly 10 digits"}), 400
    if company_password != COMPANY_MASTER_PASSWORD:
        return jsonify({"error": "Invalid company password"}), 400
    users[username] = {
        "username": username,
        "phone": phone,
        "password": password,
        "created_at": datetime.now().isoformat(),
        "role": "annotator"
    }
    save_users(users)
    user_folder = os.path.join(USER_SUBMISSIONS_FOLDER, username)
    os.makedirs(user_folder, exist_ok=True)
    return jsonify({"message": "Account created successfully"})

@app.route("/api/login", methods=["POST"])
def api_login():
    data = request.json
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()
    users = load_users()
    if username not in users:
        return jsonify({"error": "Invalid username or password"}), 401
    if users[username]['password'] != password:
        return jsonify({"error": "Invalid username or password"}), 401
    session['username'] = username
    session['phone'] = users[username].get('phone', '')
    session['role'] = users[username].get('role', 'annotator')
    return jsonify({"message": "Login successful", "username": username})

@app.route("/api/logout", methods=["POST"])
def api_logout():
    session.clear()
    return jsonify({"message": "Logged out successfully"})

@app.route("/api/current-user")
def api_current_user():
    if 'username' in session:
        return jsonify({
            "username": session['username'],
            "phone": session.get('phone', ''),
            "logged_in": True,
            "role": session.get('role', 'annotator')
        })
    return jsonify({"logged_in": False})

@app.route("/get-next-file")
@login_required
def get_next_file():
    username = session.get('username')
    file_assignments = load_file_assignments()
    assigned_file = None
    for filename, assignment in file_assignments.items():
        if assignment.get("assigned_to") == username and assignment.get("status") == "assigned":
            assigned_time = datetime.fromisoformat(assignment["assigned_at"])
            if datetime.now().timestamp() - assigned_time.timestamp() < 1800:
                if filename not in completed_files:
                    assigned_file = filename
                    break
            else:
                release_file_assignment(filename)
    if assigned_file:
        json_data = load_json_data(assigned_file)
        if json_data:
            wav_file = assigned_file.replace('.json', '.wav')
            json_data['wav_file'] = wav_file
            json_data['json_file'] = assigned_file
            wav_path = os.path.join(AUDIO_FOLDER, wav_file)
            duration_ms = get_audio_length(wav_path)
            json_data['duration_ms'] = duration_ms
            return jsonify(json_data)
    next_file = assign_file_to_user(username)
    if not next_file:
        return jsonify({"completed": True, "message": "All files have been annotated!"})
    json_data = load_json_data(next_file)
    if not json_data:
        return jsonify({"error": "Could not load file"})
    wav_file = next_file.replace('.json', '.wav')
    json_data['wav_file'] = wav_file
    json_data['json_file'] = next_file
    wav_path = os.path.join(AUDIO_FOLDER, wav_file)
    duration_ms = get_audio_length(wav_path)
    json_data['duration_ms'] = duration_ms
    return jsonify(json_data)

@app.route("/update-frame", methods=["POST"])
@login_required
def update_frame():
    data = request.json
    json_file = data.get('json_file')
    frame_index = data.get('frame_index')
    new_text = data.get('text')
    json_data = load_json_data(json_file)
    if json_data and frame_index < len(json_data.get('frames', [])):
        json_data['frames'][frame_index]['text'] = new_text
        full_sequence = ' '.join([f['text'] for f in json_data['frames'] if f.get('text')])
        json_data['full_sequence'] = full_sequence
        return jsonify({"success": True, "full_sequence": full_sequence})
    return jsonify({"success": False, "error": "Update failed"})

@app.route("/submit", methods=["POST"])
@login_required
def submit():
    data = request.json
    json_file = data.get('json_file')
    username = session.get('username')
    wav_file = data.get('wav_file', json_file.replace('.json', '.wav'))
    original_wav_path = os.path.join(AUDIO_FOLDER, wav_file)
    duration_ms = data.get('duration_ms', 0)
    duration_seconds = duration_ms / 1000.0
    data["status"] = "submitted"
    data["submitted_at"] = datetime.now().isoformat()
    data["submitted_by"] = username
    data["submitted_by_phone"] = session.get('phone', '')
    data["annotator"] = username
    data["verification_status"] = "pending"
    
    user_submit_folder = os.path.join(USER_SUBMISSIONS_FOLDER, username)
    os.makedirs(user_submit_folder, exist_ok=True)
    user_submit_path = os.path.join(user_submit_folder, json_file)
    with open(user_submit_path, "w", encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    old_submit_path = os.path.join(SUBMIT_FOLDER, f"{username}_{json_file}")
    with open(old_submit_path, "w", encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    save_to_mobile_dataset(data, username, original_wav_path, json_file)
    update_user_stats(username, json_file, duration_seconds, increment=True)
    update_daily_stats(username, json_file, duration_seconds, increment=True)
    
    completed_files.add(json_file)
    save_completed_files(completed_files)
    release_file_assignment(json_file)
    clear_skipped_file(username, json_file)
    
    all_json_files = glob.glob(os.path.join(AUDIO_FOLDER, "*.json"))
    total = len(all_json_files)
    remaining = total - len(completed_files)
    has_more = remaining > 0
    user_stats = get_user_stats(username)
    return jsonify({
        "message": "Submitted successfully", 
        "file": json_file,
        "user_folder": f"user_submissions/{username}",
        "has_more": has_more,
        "remaining": remaining,
        "user_stats": user_stats
    })

# ============= NEW 3-TIER SUBMIT ENDPOINT (ADDED) =============
@app.route("/submit-3-tier", methods=["POST"])
@login_required
def submit_3_tier():
    """Submit 3-tier annotation (216ms, 108ms, 54ms frames)"""
    data = request.json
    json_file = data.get('json_file')
    username = session.get('username')
    wav_file = data.get('wav_file', json_file.replace('.json', '.wav'))
    original_wav_path = os.path.join(AUDIO_FOLDER, wav_file)
    duration_ms = data.get('duration_ms', 0)
    duration_seconds = duration_ms / 1000.0
    
    data["status"] = "submitted"
    data["submitted_at"] = datetime.now().isoformat()
    data["submitted_by"] = username
    data["submitted_by_phone"] = session.get('phone', '')
    data["annotator"] = username
    data["verification_status"] = "pending"
    data["type"] = "3_tier"
    
    # Save to user submissions folder
    user_submit_folder = os.path.join(USER_SUBMISSIONS_FOLDER, username)
    os.makedirs(user_submit_folder, exist_ok=True)
    user_submit_path = os.path.join(user_submit_folder, json_file)
    with open(user_submit_path, "w", encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    # Also save to SUBMIT_FOLDER for backup
    old_submit_path = os.path.join(SUBMIT_FOLDER, f"{username}_{json_file}")
    with open(old_submit_path, "w", encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    # Save to mobile dataset (this creates TextGrid and saves to training data)
    save_to_mobile_dataset(data, username, original_wav_path, json_file)
    
    # Update statistics
    update_user_stats(username, json_file, duration_seconds, increment=True)
    update_daily_stats(username, json_file, duration_seconds, increment=True)
    
    # Mark as completed
    completed_files.add(json_file)
    save_completed_files(completed_files)
    
    # Release file assignment
    release_file_assignment(json_file)
    clear_skipped_file(username, json_file)
    
    # Calculate remaining files
    all_json_files = glob.glob(os.path.join(AUDIO_FOLDER, "*.json"))
    total = len(all_json_files)
    remaining = total - len(completed_files)
    has_more = remaining > 0
    user_stats = get_user_stats(username)
    
    return jsonify({
        "message": "3-Tier annotation submitted successfully", 
        "file": json_file,
        "user_folder": f"user_submissions/{username}",
        "has_more": has_more,
        "remaining": remaining,
        "user_stats": user_stats
    })
# ============= END OF NEW 3-TIER SUBMIT ENDPOINT =============

@app.route("/skip-file", methods=["POST"])
@login_required
def skip_file():
    data = request.json
    json_file = data.get('json_file')
    username = session.get('username')
    if json_file:
        add_skipped_file(username, json_file)
        release_file_assignment(json_file)
        return jsonify({
            "message": "File skipped and will not appear again", 
            "has_more": True,
            "skipped": True
        })
    return jsonify({"message": "No file to skip", "has_more": True})

@app.route("/progress")
@login_required
def progress():
    username = session.get('username')
    all_json_files = glob.glob(os.path.join(AUDIO_FOLDER, "*.json"))
    total = len(all_json_files)
    completed = len(completed_files)
    remaining = total - completed
    user_stats = get_user_stats(username)
    user_daily_stats = get_user_daily_stats(username)
    return jsonify({
        "total": total,
        "completed": completed,
        "remaining": remaining,
        "completed_list": list(completed_files),
        "username": username,
        "user_stats": user_stats,
        "user_daily_stats": user_daily_stats
    })

@app.route("/api/user-stats")
@login_required
def get_user_stats_endpoint():
    username = session.get('username')
    stats = get_user_stats(username)
    return jsonify(stats)

@app.route("/api/all-user-stats")
@login_required
def get_all_user_stats():
    stats = load_user_stats()
    return jsonify(stats)

@app.route("/audio/<path:filename>")
@login_required
def serve_audio(filename):
    return send_from_directory(AUDIO_FOLDER, filename)

@app.route("/api/my-submissions")
@login_required
def get_my_submissions():
    username = session.get('username')
    user_folder = os.path.join(USER_SUBMISSIONS_FOLDER, username)
    submissions = []
    if os.path.exists(user_folder):
        for file in os.listdir(user_folder):
            if file.endswith('.json'):
                file_path = os.path.join(user_folder, file)
                stat = os.stat(file_path)
                submissions.append({
                    "filename": file,
                    "size": stat.st_size,
                    "modified": stat.st_mtime,
                    "path": f"user_submissions/{username}/{file}"
                })
    submissions.sort(key=lambda x: x['modified'], reverse=True)
    return jsonify({"submissions": submissions, "username": username})

@app.route("/api/mobile-dataset")
@login_required
def get_mobile_dataset():
    files = []
    if os.path.exists(MOBILE_DATASET_FOLDER):
        for file in os.listdir(MOBILE_DATASET_FOLDER):
            file_path = os.path.join(MOBILE_DATASET_FOLDER, file)
            stat = os.stat(file_path)
            files.append({
                "filename": file,
                "size": stat.st_size,
                "modified": stat.st_mtime,
                "extension": file.split('.')[-1] if '.' in file else 'unknown'
            })
    files.sort(key=lambda x: x['modified'], reverse=True)
    return jsonify({"files": files, "total": len(files)})

@app.route("/mobile-dataset/<filename>")
@login_required
def download_mobile_dataset(filename):
    return send_from_directory(MOBILE_DATASET_FOLDER, filename, as_attachment=True)

@app.route("/user_submissions/<username>/<filename>")
@login_required
def serve_user_submission(username, filename):
    file_path = os.path.join(USER_SUBMISSIONS_FOLDER, username, filename)
    safe_path = os.path.abspath(file_path)
    safe_base = os.path.abspath(USER_SUBMISSIONS_FOLDER)
    if not safe_path.startswith(safe_base):
        return jsonify({"error": "Access denied"}), 403
    if not os.path.exists(file_path):
        return jsonify({"error": "File not found"}), 404
    return send_from_directory(os.path.dirname(file_path), filename)


# ============= LIVE STREAM API ROUTES =============

@app.route("/api/live-stream/create-session", methods=["POST"])
@login_required
def live_stream_create_session():
    """Create a session for live stream annotation with autosave"""
    try:
        data = request.json
        username = session.get('username')
        
        session_id = f"{username}_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
        
        user_session_folder = get_user_live_session_folder(username)
        session_path = os.path.join(user_session_folder, f"{session_id}.json")
        
        session_data = {
            "session_id": session_id,
            "username": username,
            "language": data.get("language", "hi"),
            "duration": data.get("duration", 2),
            "created_at": datetime.now().isoformat(),
            "frames_216": [],
            "frames_108": [],
            "frames_54": [],
            "speaker_frames": [],
            "gender_frames": [],
            "sentence": "",
            "has_video": data.get("video_blob", False)
        }
        
        with open(session_path, 'w', encoding='utf-8') as f:
            json.dump(session_data, f, indent=2)
        
        return jsonify({
            "success": True,
            "session_id": session_id
        })
        
    except Exception as e:
        print(f"Error creating session: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/live-stream/autosave", methods=["POST"])
@login_required
def live_stream_autosave():
    """Auto-save live stream annotation progress with speaker/gender frames"""
    try:
        data = request.json
        username = session.get('username')
        session_id = data.get("session_id")
        
        if not session_id:
            return jsonify({"error": "No session_id"}), 400
        
        user_session_folder = get_user_live_session_folder(username)
        session_path = os.path.join(user_session_folder, f"{session_id}.json")
        
        if os.path.exists(session_path):
            with open(session_path, 'r', encoding='utf-8') as f:
                session_data = json.load(f)
        else:
            session_data = {"session_id": session_id}
        
        session_data["frames_216"] = data.get("frames_216", [])
        session_data["frames_108"] = data.get("frames_108", [])
        session_data["frames_54"] = data.get("frames_54", [])
        session_data["speaker_frames"] = data.get("speaker_frames", [])
        session_data["gender_frames"] = data.get("gender_frames", [])
        session_data["sentence"] = data.get("sentence", "")
        session_data["last_autosave"] = datetime.now().isoformat()
        
        with open(session_path, 'w', encoding='utf-8') as f:
            json.dump(session_data, f, indent=2)
        
        return jsonify({"success": True})
        
    except Exception as e:
        print(f"Error in autosave: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/live-stream/get-session/<session_id>", methods=["GET"])
@login_required
def live_stream_get_session(session_id):
    """Get saved session data for restoration"""
    try:
        username = session.get('username')
        user_session_folder = get_user_live_session_folder(username)
        session_path = os.path.join(user_session_folder, f"{session_id}.json")
        
        if not os.path.exists(session_path):
            return jsonify({"success": False, "error": "Session not found"}), 404
        
        with open(session_path, 'r', encoding='utf-8') as f:
            session_data = json.load(f)
        
        return jsonify({
            "success": True,
            "session_id": session_data.get("session_id"),
            "language": session_data.get("language", "hi"),
            "duration": session_data.get("duration", 2),
            "frames_216": session_data.get("frames_216", []),
            "frames_108": session_data.get("frames_108", []),
            "frames_54": session_data.get("frames_54", []),
            "speaker_frames": session_data.get("speaker_frames", []),
            "gender_frames": session_data.get("gender_frames", []),
            "sentence": session_data.get("sentence", ""),
            "has_video": session_data.get("has_video", False)
        })
        
    except Exception as e:
        print(f"Error getting session: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/live-stream/clear-session/<session_id>", methods=["POST"])
@login_required
def live_stream_clear_session(session_id):
    """Clear saved session data"""
    try:
        username = session.get('username')
        user_session_folder = get_user_live_session_folder(username)
        session_path = os.path.join(user_session_folder, f"{session_id}.json")
        
        if os.path.exists(session_path):
            os.remove(session_path)
        
        return jsonify({"success": True})
        
    except Exception as e:
        print(f"Error clearing session: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/live-stream/fetch", methods=["GET"])
@login_required
def live_stream_fetch():
    try:
        lang = request.args.get('lang', 'hi')
        duration = int(request.args.get('duration', 2))
        duration = max(1, min(duration, 60))
        
        stream_urls = get_stream_urls_for_lang(lang)
        audio_bytes = fetch_live_audio_chunk(stream_urls, duration, lang=lang)
        
        # Fetch video segment
        video_bytes = fetch_live_video_segment(stream_urls, duration)
        
        is_real = len(audio_bytes) > 8000
        
        return jsonify({
            "success": True,
            "language": lang,
            "duration": duration,
            "audio_blob": base64.b64encode(audio_bytes).decode('utf-8'),
            "video_blob": base64.b64encode(video_bytes).decode('utf-8') if video_bytes else None,
            "mime_type": "audio/wav",
            "has_audio": is_real,
            "is_silent": not is_real,
            "has_video": video_bytes is not None
        })
    except Exception as exc:
        print(f"[live] fetch error: {exc}")
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(exc)}), 500


@app.route("/api/live-stream/submit", methods=["POST"])
@login_required
def live_stream_submit():
    try:
        username = session.get('username')
        if 'audio' not in request.files:
            return jsonify({"success": False, "error": "No audio file"}), 400
        audio_file = request.files['audio']
        language = request.form.get('language', 'unknown')
        frames_json = request.form.get('frames', '[]')
        duration = float(request.form.get('duration', 2))
        frames = json.loads(frames_json)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"live_{language}_{username}_{timestamp}"
        live_folder = os.path.join(SELF_RECORDINGS_FOLDER, "live_streams", username)
        os.makedirs(live_folder, exist_ok=True)
        wav_filename = f"{filename}.wav"
        wav_path = os.path.join(live_folder, wav_filename)
        audio_file.save(wav_path)
        full_sequence = ' '.join(f.get('text', '') for f in frames if f.get('text'))
        annotation_data = {
            "audio_file": wav_filename,
            "annotator": username,
            "timestamp": datetime.now().isoformat(),
            "language": language,
            "duration_ms": int(duration * 1000),
            "frames": frames,
            "type": "live_stream",
            "window_ms": 108,
            "full_sequence": full_sequence,
            "sentence": "",
            "submitted_by": username,
            "submitted_at": datetime.now().isoformat(),
            "verification_status": "pending",
        }
        json_filename = f"{filename}.json"
        json_path = os.path.join(live_folder, json_filename)
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(annotation_data, f, indent=2, ensure_ascii=False)
        textgrid_content = create_enhanced_textgrid(
            frames=frames, duration=duration,
            sentence="", annotator=username, full_sequence=full_sequence,
        )
        with open(os.path.join(live_folder, f"{filename}.TextGrid"), 'w', encoding='utf-8') as f:
            f.write(textgrid_content)
        save_to_mobile_dataset(annotation_data, username, wav_path, json_filename)
        akshar_count = sum(1 for f in frames if f.get('text') and f['text'].strip())
        update_user_stats(username, json_filename, duration, increment=True)
        update_daily_stats(username, json_filename, duration, increment=True)
        completed_files.add(json_filename)
        save_completed_files(completed_files)
        return jsonify({
            "success": True,
            "message": "Live stream annotation submitted successfully",
            "akshar_count": akshar_count,
            "filename": filename,
        })
    except Exception as exc:
        print(f"[live] submit error: {exc}")
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(exc)}), 500


@app.route("/api/live-stream/submit-3-tier", methods=["POST"])
@login_required
def live_stream_submit_3_tier():
    """Submit 3-tier annotation for live stream clips with speaker/gender information"""
    try:
        username = session.get('username')
        if 'audio' not in request.files:
            return jsonify({"success": False, "error": "No audio file"}), 400
        
        audio_file = request.files['audio']
        video_file = request.files.get('video')
        language = request.form.get('language', 'unknown')
        duration = float(request.form.get('duration', 2))
        
        frames_54 = json.loads(request.form.get('frames_54', '[]'))
        frames_108 = json.loads(request.form.get('frames_108', '[]'))
        frames_216 = json.loads(request.form.get('frames_216', '[]'))
        speaker_frames = json.loads(request.form.get('speaker_frames', '[]'))
        gender_frames = json.loads(request.form.get('gender_frames', '[]'))
        sentence = request.form.get('sentence', '')
        session_id = request.form.get('session_id', '')
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base_filename = f"live_3tier_{language}_{username}_{timestamp}"
        
        live_folder = os.path.join(SELF_RECORDINGS_FOLDER, "live_streams", username)
        os.makedirs(live_folder, exist_ok=True)
        
        wav_filename = f"{base_filename}.wav"
        wav_path = os.path.join(live_folder, wav_filename)
        audio_file.save(wav_path)
        
        # Save video if provided
        video_filename = None
        if video_file:
            video_filename = f"{base_filename}.mp4"
            video_path = os.path.join(live_folder, video_filename)
            video_file.save(video_path)
            print(f"Video saved to: {video_path}")
        
        full_sequence = ' '.join(f.get('text', '') for f in frames_108 if f.get('text'))
        
        annotation_data = {
            "audio_file": wav_filename,
            "video_file": video_filename,
            "annotator": username,
            "timestamp": datetime.now().isoformat(),
            "language": language,
            "duration_ms": int(duration * 1000),
            "frames_54": frames_54,
            "frames_108": frames_108,
            "frames_216": frames_216,
            "speaker_frames": speaker_frames,
            "gender_frames": gender_frames,
            "sentence": sentence,
            "type": "live_stream_3tier",
            "full_sequence": full_sequence,
            "submitted_by": username,
            "submitted_at": datetime.now().isoformat(),
            "verification_status": "pending",
        }
        
        json_filename = f"{base_filename}.json"
        json_path = os.path.join(live_folder, json_filename)
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(annotation_data, f, indent=2, ensure_ascii=False)
        
        # Get actual duration from audio file
        try:
            import soundfile as sf
            info = sf.info(wav_path)
            actual_duration = info.duration
        except:
            actual_duration = duration
        
        # Merge speaker and gender frames into intervals
        WINDOW_216 = 0.216
        merged_speaker_intervals = merge_frames_to_intervals(speaker_frames, actual_duration, WINDOW_216)
        merged_gender_intervals = merge_frames_to_intervals(gender_frames, actual_duration, WINDOW_216)
        
        # Generate 13-tier TextGrid with speaker_id and gender_id tiers
        textgrid_content = create_live_stream_textgrid_with_speaker_gender(
            frames_216=frames_216,
            frames_108=frames_108,
            frames_54=frames_54,
            duration=actual_duration,
            sentence=sentence,
            annotator=username,
            speaker_intervals=merged_speaker_intervals,
            gender_intervals=merged_gender_intervals
        )
        
        textgrid_path = os.path.join(live_folder, f"{base_filename}.TextGrid")
        with open(textgrid_path, 'w', encoding='utf-8') as f:
            f.write(textgrid_content)
        
        # Save to mobile dataset (this will also save to training data)
        save_to_mobile_dataset(annotation_data, username, wav_path, json_filename)
        
        akshar_count = sum(1 for f in frames_54 if f.get('text') and f['text'].strip())
        
        update_user_stats(username, json_filename, duration, increment=True)
        update_daily_stats(username, json_filename, duration, increment=True)
        completed_files.add(json_filename)
        save_completed_files(completed_files)
        
        # Clean up session if exists
        if session_id:
            user_session_folder = get_user_live_session_folder(username)
            session_path = os.path.join(user_session_folder, f"{session_id}.json")
            if os.path.exists(session_path):
                os.remove(session_path)
        
        return jsonify({
            "success": True,
            "message": "3-tier live stream annotation submitted successfully",
            "akshar_count": akshar_count,
            "filename": base_filename,
            "video_saved": video_filename is not None
        })
        
    except Exception as exc:
        print(f"[live-3tier] submit error: {exc}")
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(exc)}), 500


# ============= VERIFICATION ROUTES =============

VERIFIER_PASSWORD = "verify123"

@app.route("/verify/login")
def verify_login_page():
    return render_template("verify_login.html", base_path=BASE_PATH)

@app.route("/verify/api/login", methods=["POST"])
def verify_api_login():
    data = request.json
    password = data.get('password', '').strip()
    if password == VERIFIER_PASSWORD:
        session['verifier'] = True
        session['verifier_name'] = data.get('name', 'Verifier')
        return jsonify({"message": "Verifier login successful", "verified": True})
    return jsonify({"error": "Invalid verifier password"}), 401

@app.route("/verify/api/logout", methods=["POST"])
def verify_api_logout():
    session.pop('verifier', None)
    session.pop('verifier_name', None)
    return jsonify({"message": "Logged out from verification"})

@app.route("/verify")
def verify_page():
    if not session.get('verifier'):
        return redirect(url_for_path("verify/login"))
    return render_template("verify.html", base_path=BASE_PATH, verifier_name=session.get('verifier_name', 'Verifier'))

@app.route("/verify/progress")
@verifier_login_required
def verify_progress():
    total_files = 0
    verified_files = 0
    if os.path.exists(MOBILE_DATASET_FOLDER):
        json_files = glob.glob(os.path.join(MOBILE_DATASET_FOLDER, "*.json"))
        total_files = len(json_files)
    if os.path.exists(MOBILE_VERIFIED_FOLDER):
        verified_json = glob.glob(os.path.join(MOBILE_VERIFIED_FOLDER, "*.json"))
        verified_files = len(verified_json)
    remaining_files = total_files - verified_files
    return jsonify({
        "total": total_files,
        "verified": verified_files,
        "remaining": remaining_files,
        "percent": (verified_files / total_files * 100) if total_files > 0 else 0
    })

@app.route("/verify/api/annotators")
@verifier_login_required
def get_annotators_list():
    if not os.path.exists(MOBILE_DATASET_FOLDER):
        return jsonify({"annotators": [], "selected": None})
    annotators = set()
    json_files = glob.glob(os.path.join(MOBILE_DATASET_FOLDER, "*.json"))
    for json_path in json_files:
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                submitted_by = data.get('submitted_by', 'unknown')
                annotators.add(submitted_by)
        except Exception as e:
            print(f"Error reading {json_path}: {e}")
    return jsonify({"annotators": sorted(list(annotators)), "selected": None})

@app.route("/verify/api/annotator-files")
@verifier_login_required
def get_annotator_files():
    annotator = request.args.get('annotator', '')
    if not annotator:
        return jsonify({"error": "No annotator specified", "files": []}), 400
    if not os.path.exists(MOBILE_DATASET_FOLDER):
        return jsonify({"files": []})
    unverified_files = []
    json_files = glob.glob(os.path.join(MOBILE_DATASET_FOLDER, "*.json"))
    for json_path in json_files:
        json_file = os.path.basename(json_path)
        verified_json = os.path.join(MOBILE_VERIFIED_FOLDER, json_file)
        if os.path.exists(verified_json):
            continue
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                submitted_by = data.get('submitted_by', 'unknown')
                if submitted_by == annotator:
                    wav_file = json_file.replace('.json', '.wav')
                    wav_path = os.path.join(MOBILE_DATASET_FOLDER, wav_file)
                    if os.path.exists(wav_path):
                        unverified_files.append(json_file)
        except Exception as e:
            print(f"Error reading {json_path}: {e}")
    return jsonify({"files": unverified_files, "annotator": annotator, "count": len(unverified_files)})


@app.route("/verify/api/get-file/<path:json_file>")
@verifier_login_required
def get_verification_file(json_file):
    annotator = request.args.get('annotator', '')
    json_path = os.path.join(MOBILE_DATASET_FOLDER, json_file)
    if not os.path.exists(json_path):
        return jsonify({"error": "File not found"}), 404
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if annotator and data.get('submitted_by') != annotator:
            return jsonify({"error": f"This file belongs to {data.get('submitted_by')}, not {annotator}"}), 403
        data['json_file'] = json_file
        data['wav_file'] = json_file.replace('.json', '.wav')
        wav_path = os.path.join(MOBILE_DATASET_FOLDER, data['wav_file'])
        if 'duration_ms' not in data or data['duration_ms'] == 0:
            data['duration_ms'] = get_audio_length(wav_path)
        
        # Ensure 3-tier data is returned for verification
        if 'frames_54' not in data and 'frames_108' not in data and 'frames_216' not in data:
            if 'frames' in data and data['frames']:
                frames_108 = data['frames']
                frames_54 = []
                frames_216 = []
                
                for f in frames_108:
                    half = (f['end_ms'] - f['start_ms']) // 2
                    text = f.get('text', '')
                    frames_54.append({
                        'start_ms': f['start_ms'],
                        'end_ms': f['start_ms'] + half,
                        'text': text[:2] if text else ''
                    })
                    frames_54.append({
                        'start_ms': f['start_ms'] + half,
                        'end_ms': f['end_ms'],
                        'text': text[2:4] if len(text) > 2 else ''
                    })
                
                for i in range(0, len(frames_108), 2):
                    start = frames_108[i]['start_ms']
                    end = frames_108[i+1]['end_ms'] if i+1 < len(frames_108) else frames_108[i]['end_ms']
                    text1 = frames_108[i].get('text', '')
                    text2 = frames_108[i+1].get('text', '') if i+1 < len(frames_108) else ''
                    frames_216.append({
                        'start_ms': start,
                        'end_ms': end,
                        'text': (text1 + text2)[:4]
                    })
                
                data['frames_54'] = frames_54
                data['frames_108'] = frames_108
                data['frames_216'] = frames_216
        
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": f"Error loading file: {e}"}), 500


def get_next_verification_file():
    if not os.path.exists(MOBILE_DATASET_FOLDER):
        return None
    json_files = glob.glob(os.path.join(MOBILE_DATASET_FOLDER, "*.json"))
    for json_path in json_files:
        json_file = os.path.basename(json_path)
        verified_json = os.path.join(MOBILE_VERIFIED_FOLDER, json_file)
        if not os.path.exists(verified_json):
            wav_file = json_file.replace('.json', '.wav')
            wav_path = os.path.join(MOBILE_DATASET_FOLDER, wav_file)
            if os.path.exists(wav_path):
                return json_file
    return None

def load_mobile_json(json_file):
    json_path = os.path.join(MOBILE_DATASET_FOLDER, json_file)
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            data['json_file'] = json_file
            data['wav_file'] = json_file.replace('.json', '.wav')
            return data
    except Exception as e:
        print(f"Error loading mobile JSON {json_file}: {e}")
        return None

def delete_from_mobile_dataset(json_file):
    base = json_file.replace('.json', '')
    paths = [
        os.path.join(MOBILE_DATASET_FOLDER, json_file),
        os.path.join(MOBILE_DATASET_FOLDER, f"{base}.wav"),
        os.path.join(MOBILE_DATASET_FOLDER, f"{base}.TextGrid")
    ]
    for p in paths:
        if os.path.exists(p):
            os.remove(p)
            print(f"Deleted {p}")
    try:
        delete_from_mobile_training_data(base)
    except Exception as e:
        print(f"Warning: Failed to delete from mobile training data: {e}")

def revert_completion_status(json_file, original_submitter, duration_seconds):
    global completed_files
    if json_file in completed_files:
        completed_files.remove(json_file)
        save_completed_files(completed_files)
    update_user_stats(original_submitter, json_file, duration_seconds, increment=False)
    update_daily_stats(original_submitter, json_file, duration_seconds, increment=False)
    release_file_assignment(json_file)
    clear_skipped_file(original_submitter, json_file)
    user_submit_path = os.path.join(USER_SUBMISSIONS_FOLDER, original_submitter, json_file)
    if os.path.exists(user_submit_path):
        os.remove(user_submit_path)
    backup_path = os.path.join(SUBMIT_FOLDER, f"{original_submitter}_{json_file}")
    if os.path.exists(backup_path):
        os.remove(backup_path)

@app.route("/verify/get-next-file")
@verifier_login_required
def verify_get_next_file():
    next_file = get_next_verification_file()
    if not next_file:
        return jsonify({"completed": True, "message": "All files have been verified!"})
    json_data = load_mobile_json(next_file)
    if not json_data:
        return jsonify({"error": "Could not load file", "completed": False})
    wav_path = os.path.join(MOBILE_DATASET_FOLDER, json_data['wav_file'])
    if 'duration_ms' not in json_data or json_data['duration_ms'] == 0:
        json_data['duration_ms'] = get_audio_length(wav_path)
    return jsonify(json_data)

@app.route("/verify/submit", methods=["POST"])
@verifier_login_required
def verify_submit():
    data = request.json
    json_file = data.get('json_file')
    action = data.get('action')
    verifier_name = session.get('verifier_name', 'Verifier')
    if not json_file:
        return jsonify({"error": "No file specified"}), 400
    if action == 'verify':
        original_submitter = data.get('submitted_by', 'unknown')
        duration_ms = data.get('duration_ms', 0)
        duration_seconds = duration_ms / 1000.0
        data['verified_by'] = verifier_name
        data['verified_at'] = datetime.now().isoformat()
        data['verification_status'] = 'verified'
        wav_path = os.path.join(MOBILE_DATASET_FOLDER, data['wav_file'])
        save_to_mobile_dataset(data, original_submitter, wav_path, json_file, verified=True)
        save_to_mobile_dataset(data, original_submitter, wav_path, json_file, verified=False)
        return jsonify({"message": "File verified and saved to verified folder", "has_more": True, "verified": True})
    elif action == 'reject':
        original_data = load_mobile_json(json_file)
        if not original_data:
            return jsonify({"error": "Could not load file data"}), 400
        original_submitter = original_data.get('submitted_by', 'unknown')
        duration_ms = original_data.get('duration_ms', 0)
        duration_seconds = duration_ms / 1000.0
        delete_from_mobile_dataset(json_file)
        revert_completion_status(json_file, original_submitter, duration_seconds)
        return jsonify({"message": "File rejected and removed from dataset. It will be re-annotated.", "has_more": True, "rejected": True})
    else:
        return jsonify({"error": "Invalid action"}), 400


# ==============================
# SELF-RECORD API ROUTES
# ==============================

@app.route("/api/self-record/save", methods=["POST"])
@login_required
def self_record_save():
    """Save self-recorded audio for annotation"""
    try:
        if 'audio' not in request.files:
            return jsonify({"success": False, "error": "No audio file"}), 400
        
        audio_file = request.files['audio']
        username = session.get('username')
        
        # Generate unique filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        original_filename = f"{username}_self_{timestamp}.webm"
        
        # Save original recording
        user_recording_folder = os.path.join(SELF_RECORDINGS_FOLDER, username)
        os.makedirs(user_recording_folder, exist_ok=True)
        
        original_path = os.path.join(user_recording_folder, original_filename)
        audio_file.save(original_path)
        
        # Get duration from client
        duration = float(request.form.get('duration', 0))
        
        return jsonify({
            "success": True,
            "filename": original_filename,
            "duration": duration,
            "message": "Recording saved"
        })
        
    except Exception as e:
        print(f"Error saving recording: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/self-record/create-annotation", methods=["POST"])
@login_required
def self_record_create_annotation():
    """Create annotation frames for self-recorded audio"""
    try:
        data = request.json
        username = session.get('username')
        filename = data.get('filename')
        duration = data.get('duration', 0)
        speed = data.get('speed', '2x')
        
        # Frame size based on speed
        if speed == 'normal':
            frame_size_ms = 54
        elif speed == '2x':
            frame_size_ms = 108
        else:  # 4x
            frame_size_ms = 216
        
        # Calculate number of frames
        total_duration_ms = duration * 1000
        num_frames = int(total_duration_ms / frame_size_ms) + 1
        
        # Create frames
        frames = []
        for i in range(num_frames):
            start_ms = i * frame_size_ms
            end_ms = min((i + 1) * frame_size_ms, total_duration_ms)
            frames.append({
                "index": i,
                "start_ms": start_ms,
                "end_ms": end_ms,
                "text": ""
            })
        
        # Create annotation data
        annotation_data = {
            "audio_file": filename,
            "annotator": username,
            "timestamp": datetime.now().isoformat(),
            "window_ms": frame_size_ms,
            "sentence": "",
            "full_sequence": "",
            "frames": frames,
            "duration_ms": total_duration_ms,
            "speed": speed,
            "self_recorded": True
        }
        
        # Save annotation JSON
        user_recording_folder = os.path.join(SELF_RECORDINGS_FOLDER, username)
        os.makedirs(user_recording_folder, exist_ok=True)
        json_filename = filename.replace('.webm', '.json')
        json_path = os.path.join(user_recording_folder, json_filename)
        
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(annotation_data, f, indent=2, ensure_ascii=False)
        
        return jsonify({
            "success": True,
            "frames": frames,
            "window_ms": frame_size_ms,
            "duration_ms": total_duration_ms,
            "json_filename": json_filename
        })
        
    except Exception as e:
        print(f"Error creating annotation: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/self-record/submit", methods=["POST"])
@login_required
def self_record_submit():
    """Submit self-recorded annotation"""
    try:
        data = request.json
        username = session.get('username')
        json_filename = data.get('json_filename')
        frames = data.get('frames', [])
        sentence = data.get('sentence', '')
        
        # Load the annotation file
        user_recording_folder = os.path.join(SELF_RECORDINGS_FOLDER, username)
        json_path = os.path.join(user_recording_folder, json_filename)
        
        if not os.path.exists(json_path):
            return jsonify({"success": False, "error": "Annotation file not found"}), 404
        
        with open(json_path, 'r', encoding='utf-8') as f:
            annotation_data = json.load(f)
        
        # Update with submitted data
        annotation_data['frames'] = frames
        annotation_data['sentence'] = sentence
        annotation_data['full_sequence'] = ' '.join([f['text'] for f in frames if f.get('text')])
        annotation_data['submitted_at'] = datetime.now().isoformat()
        annotation_data['submitted_by'] = username
        annotation_data['verification_status'] = 'pending'
        
        # Convert webm to wav (copy with wav extension)
        audio_filename = annotation_data['audio_file']
        audio_path = os.path.join(user_recording_folder, audio_filename)
        wav_filename = audio_filename.replace('.webm', '.wav')
        wav_path = os.path.join(user_recording_folder, wav_filename)
        
        # For now, just copy the file (in production you'd convert using ffmpeg)
        if os.path.exists(audio_path):
            shutil.copy2(audio_path, wav_path)
        
        # Save to mobile dataset (this creates TextGrid too)
        save_to_mobile_dataset(annotation_data, username, wav_path, json_filename)
        
        # ALSO save TextGrid to self_recordings folder
        base_name = json_filename.replace('.json', '')
        textgrid_filename = f"{base_name}.TextGrid"
        
        # Generate TextGrid content
        duration = annotation_data.get('duration_ms', 0) / 1000.0
        if duration == 0 and frames:
            duration = frames[-1].get('end_ms', 0) / 1000.0
        full_sequence = annotation_data.get('full_sequence', '')
        
        textgrid_content = create_enhanced_textgrid(
            frames=frames,
            duration=duration,
            sentence=sentence,
            annotator=username,
            full_sequence=full_sequence
        )
        
        # Save TextGrid to self_recordings folder
        textgrid_path = os.path.join(user_recording_folder, textgrid_filename)
        with open(textgrid_path, 'w', encoding='utf-8') as f:
            f.write(textgrid_content)
        
        print(f"TextGrid saved to: {textgrid_path}")
        
        # Update user stats
        duration_seconds = annotation_data.get('duration_ms', 0) / 1000.0
        update_user_stats(username, json_filename, duration_seconds, increment=True)
        update_daily_stats(username, json_filename, duration_seconds, increment=True)
        
        # Also add to completed files to track
        completed_files.add(json_filename)
        save_completed_files(completed_files)
        
        akshar_count = sum(1 for f in frames if f.get('text') and f['text'].strip())
        
        return jsonify({
            "success": True,
            "message": "Self-recorded annotation submitted successfully",
            "akshar_count": akshar_count,
            "textgrid_path": textgrid_path
        })
        
    except Exception as e:
        print(f"Error submitting self-record: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500


if __name__ == "__main__":
    print("=" * 50)
    print("Mobile Annotation Tool Server - Enhanced with Desktop Features")
    print("=" * 50)
    print(f"Mode: {'PRODUCTION' if BASE_PATH else 'DEVELOPMENT'}")
    print(f"Base URL: {BASE_PATH if BASE_PATH else '/'}")
    print(f"Debug: {DEBUG}")
    print(f"Server: http://{HOST}:{PORT}{BASE_PATH}/")
    print("Features: 3-Tier Annotation + Speaker/Gender + Video Support")
    print("=" * 50)
    app.run(host=HOST, port=PORT, debug=DEBUG)