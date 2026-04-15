# app.py
from flask import Flask, render_template, request, jsonify, send_from_directory, session, redirect, url_for
import wave
import math
import os
import shutil
from datetime import datetime
import json
import glob
from functools import wraps
from config import BASE_PATH, DEBUG, HOST, PORT

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

# Create all necessary folders
os.makedirs(SUBMIT_FOLDER, exist_ok=True)
os.makedirs(MOBILE_DATASET_FOLDER, exist_ok=True)
os.makedirs(MOBILE_VERIFIED_FOLDER, exist_ok=True)
os.makedirs(USER_SUBMISSIONS_FOLDER, exist_ok=True)

from werkzeug.middleware.proxy_fix import ProxyFix

if BASE_PATH:
    app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

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

def generate_textgrid(frames, duration, sentence, annotator, full_sequence):
    tg_lines = []
    tg_lines.append('File type = "ooTextFile"')
    tg_lines.append('Object class = "TextGrid"\n')
    tg_lines.append(f"xmin = 0")
    tg_lines.append(f"xmax = {duration}")
    tg_lines.append("tiers? <exists>")
    tg_lines.append("size = 3")
    tg_lines.append("item []:")
    tg_lines.append("    item [1]:")
    tg_lines.append('        class = "IntervalTier"')
    tg_lines.append('        name = "sentence"')
    tg_lines.append(f"        xmin = 0")
    tg_lines.append(f"        xmax = {duration}")
    tg_lines.append("        intervals: size = 1")
    tg_lines.append("        intervals [1]:")
    tg_lines.append(f"            xmin = 0")
    tg_lines.append(f"            xmax = {duration}")
    tg_lines.append(f'            text = "{sentence if sentence else full_sequence}"')
    tg_lines.append("    item [2]:")
    tg_lines.append('        class = "IntervalTier"')
    tg_lines.append('        name = "annotations"')
    tg_lines.append(f"        xmin = 0")
    tg_lines.append(f"        xmax = {duration}")
    tg_lines.append(f"        intervals: size = {len(frames)}")
    for i, frame in enumerate(frames, 1):
        start = frame.get("start_ms", 0) / 1000.0
        end = frame.get("end_ms", 0) / 1000.0
        text = frame.get("text", "") if frame.get("text") else ""
        tg_lines.append(f"        intervals [{i}]:")
        tg_lines.append(f"            xmin = {start}")
        tg_lines.append(f"            xmax = {end}")
        tg_lines.append(f'            text = "{text}"')
    tg_lines.append("    item [3]:")
    tg_lines.append('        class = "IntervalTier"')
    tg_lines.append('        name = "annotator"')
    tg_lines.append(f"        xmin = 0")
    tg_lines.append(f"        xmax = {duration}")
    tg_lines.append("        intervals: size = 1")
    tg_lines.append("        intervals [1]:")
    tg_lines.append(f"            xmin = 0")
    tg_lines.append(f"            xmax = {duration}")
    tg_lines.append(f'            text = "{annotator}"')
    return "\n".join(tg_lines)

def save_to_mobile_dataset(annotated_data, username, original_wav_path, json_filename, verified=False):
    try:
        base_name = json_filename.replace('.json', '')
        # Determine target folder
        target_folder = MOBILE_VERIFIED_FOLDER if verified else MOBILE_DATASET_FOLDER
        
        json_output_path = os.path.join(target_folder, json_filename)
        with open(json_output_path, 'w', encoding='utf-8') as f:
            json.dump(annotated_data, f, indent=2, ensure_ascii=False)
        
        wav_filename = f"{base_name}.wav"
        if original_wav_path and os.path.exists(original_wav_path):
            wav_output_path = os.path.join(target_folder, wav_filename)
            shutil.copy2(original_wav_path, wav_output_path)
        
        frames = annotated_data.get('frames', [])
        duration = annotated_data.get('duration_ms', 0) / 1000.0
        if duration == 0 and frames:
            duration = frames[-1].get('end_ms', 0) / 1000.0
        sentence = annotated_data.get('sentence', '')
        full_sequence = annotated_data.get('full_sequence', '')
        annotator = annotated_data.get('annotator', username)
        
        textgrid_content = generate_textgrid(
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
        return True
    except Exception as e:
        print(f"Error saving to dataset: {e}")
        return False

# ============= ANNOTATION ROUTES (unchanged) =============

@app.route("/")
def index():
    if 'username' in session:
        return render_template("index.html", username=session['username'], base_path=BASE_PATH)
    return redirect(url_for_path("login"))

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
        "role": "annotator"  # default role
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
    data["verification_status"] = "pending"  # add status for verification
    
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

# ============= VERIFICATION ROUTES =============

VERIFIER_PASSWORD = "verify123"  # Change this to a secure password

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
    """Get verification progress stats"""
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

def get_next_verification_file():
    """Get next unverified file from MOBILE_DATASET that hasn't been verified yet"""
    if not os.path.exists(MOBILE_DATASET_FOLDER):
        return None
    
    json_files = glob.glob(os.path.join(MOBILE_DATASET_FOLDER, "*.json"))
    for json_path in json_files:
        json_file = os.path.basename(json_path)
        # Check if already verified (exists in MOBILE_VERIFIED_FOLDER)
        verified_json = os.path.join(MOBILE_VERIFIED_FOLDER, json_file)
        if not os.path.exists(verified_json):
            # Also check if there's a corresponding wav
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
    """Delete JSON, WAV, TextGrid from MOBILE_DATASET"""
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

def revert_completion_status(json_file, original_submitter, duration_seconds):
    """Remove file from completed sets and subtract from user stats"""
    global completed_files
    # Remove from global completed set
    if json_file in completed_files:
        completed_files.remove(json_file)
        save_completed_files(completed_files)
    
    # Remove from user stats (decrement)
    update_user_stats(original_submitter, json_file, duration_seconds, increment=False)
    update_daily_stats(original_submitter, json_file, duration_seconds, increment=False)
    
    # Remove from file assignments if present
    release_file_assignment(json_file)
    
    # Remove from skipped files if present
    clear_skipped_file(original_submitter, json_file)
    
    # Also remove from user's submission folder if exists
    user_submit_path = os.path.join(USER_SUBMISSIONS_FOLDER, original_submitter, json_file)
    if os.path.exists(user_submit_path):
        os.remove(user_submit_path)
    
    # Remove from SUBMIT_FOLDER backup
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
    
    # Ensure duration_ms is present
    wav_path = os.path.join(MOBILE_DATASET_FOLDER, json_data['wav_file'])
    if 'duration_ms' not in json_data or json_data['duration_ms'] == 0:
        json_data['duration_ms'] = get_audio_length(wav_path)
    
    return jsonify(json_data)

@app.route("/verify/submit", methods=["POST"])
@verifier_login_required
def verify_submit():
    data = request.json
    json_file = data.get('json_file')
    action = data.get('action')  # 'verify' or 'reject'
    verifier_name = session.get('verifier_name', 'Verifier')
    
    if not json_file:
        return jsonify({"error": "No file specified"}), 400
    
    if action == 'verify':
        # Get original submitter and duration from the data
        original_submitter = data.get('submitted_by', 'unknown')
        duration_ms = data.get('duration_ms', 0)
        duration_seconds = duration_ms / 1000.0
        
        # Update verification metadata
        data['verified_by'] = verifier_name
        data['verified_at'] = datetime.now().isoformat()
        data['verification_status'] = 'verified'
        
        # Save to MOBILE_VERIFIED_FOLDER
        wav_path = os.path.join(MOBILE_DATASET_FOLDER, data['wav_file'])
        save_to_mobile_dataset(data, original_submitter, wav_path, json_file, verified=True)
        
        # Also update/overwrite in MOBILE_DATASET with corrected version
        save_to_mobile_dataset(data, original_submitter, wav_path, json_file, verified=False)
        
        return jsonify({
            "message": "File verified and saved to verified folder",
            "has_more": True,
            "verified": True
        })
    
    elif action == 'reject':
        # Load original data to get submitter and duration
        original_data = load_mobile_json(json_file)
        if not original_data:
            return jsonify({"error": "Could not load file data"}), 400
        
        original_submitter = original_data.get('submitted_by', 'unknown')
        duration_ms = original_data.get('duration_ms', 0)
        duration_seconds = duration_ms / 1000.0
        
        # Delete from MOBILE_DATASET
        delete_from_mobile_dataset(json_file)
        
        # Revert completion status (so file goes back to annotation pool)
        revert_completion_status(json_file, original_submitter, duration_seconds)
        
        return jsonify({
            "message": "File rejected and removed from dataset. It will be re-annotated.",
            "has_more": True,
            "rejected": True
        })
    
    else:
        return jsonify({"error": "Invalid action"}), 400

# Helper for daily stats in verification
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

if __name__ == "__main__":
    print("=" * 50)
    print("Annotation Tool Server")
    print("=" * 50)
    print(f"Mode: {'PRODUCTION' if BASE_PATH else 'DEVELOPMENT'}")
    print(f"Base URL: {BASE_PATH if BASE_PATH else '/'}")
    print(f"Debug: {DEBUG}")
    print(f"Server: http://{HOST}:{PORT}{BASE_PATH}/")
    print("=" * 50)
    app.run(host=HOST, port=PORT, debug=DEBUG)