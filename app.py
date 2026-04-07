from flask import Flask, render_template, request, jsonify, send_from_directory, session, redirect, url_for
import wave
import math
import os
import shutil
from datetime import datetime
import json
import glob
from functools import wraps

app = Flask(__name__)
app.secret_key = 'your-secret-key-change-this-in-production'  # Change this to a secure key

@app.before_request
def fix_script_name():
    from flask import request
    request.environ['SCRIPT_NAME'] = BASE_PATH

# IMPORTANT: Add BASE_PATH for nginx reverse proxy
BASE_PATH = "/mobile-annotator"

app.config['APPLICATION_ROOT'] = '/mobile-annotator'

# Folders
AUDIO_FOLDER = "data"
SUBMIT_FOLDER = "annotation_submitted"
USERS_FILE = "users.json"
COMPLETED_LOG = "completed_files.json"
MOBILE_DATASET_FOLDER = "MOBILE_DATASET"
USER_SUBMISSIONS_FOLDER = "user_submissions"
FILE_ASSIGNMENTS_FILE = "file_assignments.json"  # NEW: Track which file is assigned to which user
USER_STATS_FILE = "user_stats.json"  # NEW: Track user statistics

# Create all necessary folders
os.makedirs(SUBMIT_FOLDER, exist_ok=True)
os.makedirs(MOBILE_DATASET_FOLDER, exist_ok=True)
os.makedirs(USER_SUBMISSIONS_FOLDER, exist_ok=True)

from werkzeug.middleware.proxy_fix import ProxyFix

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

# ============= NEW: File Assignment Tracking =============
def load_file_assignments():
    """Load file assignments from JSON file"""
    if os.path.exists(FILE_ASSIGNMENTS_FILE):
        with open(FILE_ASSIGNMENTS_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_file_assignments(assignments):
    """Save file assignments to JSON file"""
    with open(FILE_ASSIGNMENTS_FILE, 'w') as f:
        json.dump(assignments, f, indent=2)

def load_user_stats():
    """Load user statistics from JSON file"""
    if os.path.exists(USER_STATS_FILE):
        with open(USER_STATS_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_user_stats(stats):
    """Save user statistics to JSON file"""
    with open(USER_STATS_FILE, 'w') as f:
        json.dump(stats, f, indent=2)

def update_user_stats(username, json_file, duration_seconds):
    """Update user statistics when a file is completed"""
    stats = load_user_stats()
    
    if username not in stats:
        stats[username] = {
            "completed_files": [],
            "total_files_completed": 0,
            "total_duration_seconds": 0,
            "total_duration_formatted": "0s",
            "last_active": None
        }
    
    # Add file to completed list if not already there
    if json_file not in stats[username]["completed_files"]:
        stats[username]["completed_files"].append(json_file)
        stats[username]["total_files_completed"] += 1
        stats[username]["total_duration_seconds"] += duration_seconds
        
        # Format duration
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
    """Get statistics for a specific user"""
    stats = load_user_stats()
    return stats.get(username, {
        "completed_files": [],
        "total_files_completed": 0,
        "total_duration_seconds": 0,
        "total_duration_formatted": "0s",
        "last_active": None
    })

def assign_file_to_user(username):
    """
    Assign a new file to the user that hasn't been completed or assigned to anyone else
    """
    file_assignments = load_file_assignments()
    user_stats = get_user_stats(username)
    completed_by_user = set(user_stats.get("completed_files", []))
    
    # Get all available files
    all_json_files = glob.glob(os.path.join(AUDIO_FOLDER, "*.json"))
    available_files = []
    
    for json_path in all_json_files:
        base_name = os.path.basename(json_path)
        wav_name = base_name.replace('.json', '.wav')
        wav_path = os.path.join(AUDIO_FOLDER, wav_name)
        
        if os.path.exists(wav_path):
            # Check if file is already completed globally
            if base_name in completed_files:
                continue
            
            # Check if file is already assigned to someone else and not expired
            if base_name in file_assignments:
                assignment = file_assignments[base_name]
                # Check if assignment is older than 30 minutes (timeout)
                assigned_time = datetime.fromisoformat(assignment["assigned_at"])
                if datetime.now().timestamp() - assigned_time.timestamp() > 1800:  # 30 minutes timeout
                    # Assignment expired, can reassign
                    pass
                elif assignment["assigned_to"] != username:
                    # Assigned to someone else and not expired
                    continue
            
            # Check if user already completed this file
            if base_name in completed_by_user:
                continue
            
            available_files.append(base_name)
    
    if not available_files:
        return None
    
    # Assign the first available file
    assigned_file = available_files[0]
    file_assignments[assigned_file] = {
        "assigned_to": username,
        "assigned_at": datetime.now().isoformat(),
        "status": "assigned"
    }
    save_file_assignments(file_assignments)
    
    return assigned_file

def release_file_assignment(json_file):
    """Release a file assignment (when skipped or expired)"""
    file_assignments = load_file_assignments()
    if json_file in file_assignments:
        del file_assignments[json_file]
        save_file_assignments(file_assignments)

# Login required decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session:
            return jsonify({
                "error": "Please login first", 
                "redirect": f"{BASE_PATH}/login"
            }), 401
        return f(*args, **kwargs)
    return decorated_function

# Get all available JSON files (not completed) - DEPRECATED, use assign_file_to_user instead
def get_available_files():
    all_json_files = glob.glob(os.path.join(AUDIO_FOLDER, "*.json"))
    available = []
    
    for json_path in all_json_files:
        base_name = os.path.basename(json_path)
        wav_name = base_name.replace('.json', '.wav')
        wav_path = os.path.join(AUDIO_FOLDER, wav_name)
        
        if os.path.exists(wav_path) and base_name not in completed_files:
            available.append({
                'json_file': base_name,
                'wav_file': wav_name,
                'name': base_name.replace('.json', '')
            })
    
    return sorted(available, key=lambda x: x['name'])

# Get audio length (ms)
def get_audio_length(file_path):
    try:
        with wave.open(file_path, 'rb') as wf:
            frames = wf.getnframes()
            rate = wf.getframerate()
            duration = frames / float(rate)
            return int(duration * 1000)
    except:
        return 5000

# Load existing JSON data
def load_json_data(json_file):
    json_path = os.path.join(AUDIO_FOLDER, json_file)
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading {json_file}: {e}")
        return None

# Generate TextGrid from frames
def generate_textgrid(frames, duration, sentence, annotator, full_sequence):
    """
    Generate a Praat TextGrid file from frames data
    """
    tg_lines = []
    
    tg_lines.append('File type = "ooTextFile"')
    tg_lines.append('Object class = "TextGrid"\n')
    
    tg_lines.append(f"xmin = 0")
    tg_lines.append(f"xmax = {duration}")
    tg_lines.append("tiers? <exists>")
    tg_lines.append("size = 3")
    tg_lines.append("item []:")
    
    # Tier 1: sentence
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
    
    # Tier 2: annotations (frames)
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
    
    # Tier 3: annotator
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

# Save to MOBILE_DATASET with annotated JSON, WAV, and TextGrid
def save_to_mobile_dataset(annotated_data, username, original_wav_path, json_filename):
    """
    Save the submitted annotation to MOBILE_DATASET folder
    """
    try:
        base_name = json_filename.replace('.json', '')
        
        # 1. Save ANNOTATED JSON file
        json_output_path = os.path.join(MOBILE_DATASET_FOLDER, json_filename)
        with open(json_output_path, 'w', encoding='utf-8') as f:
            json.dump(annotated_data, f, indent=2, ensure_ascii=False)
        
        # 2. Copy WAV file
        wav_filename = f"{base_name}.wav"
        if original_wav_path and os.path.exists(original_wav_path):
            wav_output_path = os.path.join(MOBILE_DATASET_FOLDER, wav_filename)
            shutil.copy2(original_wav_path, wav_output_path)
        
        # 3. Generate and save TextGrid file
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
        
        textgrid_output_path = os.path.join(MOBILE_DATASET_FOLDER, f"{base_name}.TextGrid")
        with open(textgrid_output_path, 'w', encoding='utf-8') as f:
            f.write(textgrid_content)
        
        print(f"✅ Saved annotated data to MOBILE_DATASET: {base_name}")
        return True
        
    except Exception as e:
        print(f"❌ Error saving to MOBILE_DATASET: {e}")
        return False

# ============= ROUTES =============

@app.route("/")
def index():
    if 'username' in session:
        return render_template("index.html", username=session['username'])
    return redirect(f"{BASE_PATH}/login")

@app.route("/login")
def login_page():
    return render_template("login.html")

@app.route("/register")
def register_page():
    return render_template("register.html")

# API: Register
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
        "created_at": datetime.now().isoformat()
    }
    save_users(users)
    
    # Create user-specific folders
    user_folder = os.path.join(USER_SUBMISSIONS_FOLDER, username)
    os.makedirs(user_folder, exist_ok=True)
    
    return jsonify({"message": "Account created successfully"})

# API: Login
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
    
    return jsonify({"message": "Login successful", "username": username})

# API: Logout
@app.route("/api/logout", methods=["POST"])
def api_logout():
    session.clear()
    return jsonify({"message": "Logged out successfully"})

# API: Get current user
@app.route("/api/current-user")
def api_current_user():
    if 'username' in session:
        return jsonify({
            "username": session['username'],
            "phone": session.get('phone', ''),
            "logged_in": True
        })
    return jsonify({"logged_in": False})

# Get next file to annotate - UPDATED with assignment tracking
@app.route("/get-next-file")
@login_required
def get_next_file():
    username = session.get('username')
    
    # Check if user already has an assigned file
    file_assignments = load_file_assignments()
    assigned_file = None
    
    for filename, assignment in file_assignments.items():
        if assignment.get("assigned_to") == username and assignment.get("status") == "assigned":
            # Check if assignment is not expired (30 minutes timeout)
            assigned_time = datetime.fromisoformat(assignment["assigned_at"])
            if datetime.now().timestamp() - assigned_time.timestamp() < 1800:
                # Check if file is not already completed
                if filename not in completed_files:
                    assigned_file = filename
                    break
            else:
                # Assignment expired, remove it
                release_file_assignment(filename)
    
    if assigned_file:
        # Return the already assigned file
        json_data = load_json_data(assigned_file)
        if json_data:
            wav_file = assigned_file.replace('.json', '.wav')
            json_data['wav_file'] = wav_file
            json_data['json_file'] = assigned_file
            
            wav_path = os.path.join(AUDIO_FOLDER, wav_file)
            duration_ms = get_audio_length(wav_path)
            json_data['duration_ms'] = duration_ms
            
            return jsonify(json_data)
    
    # Assign a new file
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

# Update frame text
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

# Submit annotation - UPDATED with user stats tracking
@app.route("/submit", methods=["POST"])
@login_required
def submit():
    data = request.json
    json_file = data.get('json_file')
    username = session.get('username')
    
    wav_file = data.get('wav_file', json_file.replace('.json', '.wav'))
    original_wav_path = os.path.join(AUDIO_FOLDER, wav_file)
    
    # Get audio duration for stats
    duration_ms = data.get('duration_ms', 0)
    duration_seconds = duration_ms / 1000.0
    
    data["status"] = "submitted"
    data["submitted_at"] = datetime.now().isoformat()
    data["submitted_by"] = username
    data["submitted_by_phone"] = session.get('phone', '')
    data["annotator"] = username
    
    # Save to user-specific subfolder
    user_submit_folder = os.path.join(USER_SUBMISSIONS_FOLDER, username)
    os.makedirs(user_submit_folder, exist_ok=True)
    
    user_submit_path = os.path.join(user_submit_folder, json_file)
    with open(user_submit_path, "w", encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    # Save to old SUBMIT_FOLDER for backward compatibility
    old_submit_path = os.path.join(SUBMIT_FOLDER, f"{username}_{json_file}")
    with open(old_submit_path, "w", encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    # Save to MOBILE_DATASET
    save_to_mobile_dataset(data, username, original_wav_path, json_file)
    
    # Update user statistics
    update_user_stats(username, json_file, duration_seconds)
    
    # Mark as completed globally
    completed_files.add(json_file)
    save_completed_files(completed_files)
    
    # Release file assignment
    release_file_assignment(json_file)
    
    # Check if there are more files
    all_json_files = glob.glob(os.path.join(AUDIO_FOLDER, "*.json"))
    total = len(all_json_files)
    remaining = total - len(completed_files)
    has_more = remaining > 0
    
    # Get updated user stats
    user_stats = get_user_stats(username)
    
    return jsonify({
        "message": "Submitted successfully", 
        "file": json_file,
        "user_folder": f"user_submissions/{username}",
        "has_more": has_more,
        "remaining": remaining,
        "user_stats": user_stats
    })

# Skip file - release assignment
@app.route("/skip-file", methods=["POST"])
@login_required
def skip_file():
    data = request.json
    json_file = data.get('json_file')
    username = session.get('username')
    
    if json_file:
        release_file_assignment(json_file)
    
    return jsonify({"message": "File skipped", "has_more": True})

# Get progress - UPDATED with user stats
@app.route("/progress")
@login_required
def progress():
    username = session.get('username')
    all_json_files = glob.glob(os.path.join(AUDIO_FOLDER, "*.json"))
    total = len(all_json_files)
    completed = len(completed_files)
    remaining = total - completed
    
    user_stats = get_user_stats(username)
    
    return jsonify({
        "total": total,
        "completed": completed,
        "remaining": remaining,
        "completed_list": list(completed_files),
        "username": username,
        "user_stats": user_stats
    })

# NEW: Get user statistics
@app.route("/api/user-stats")
@login_required
def get_user_stats_endpoint():
    username = session.get('username')
    stats = get_user_stats(username)
    return jsonify(stats)

# NEW: Get all user statistics (for admin)
@app.route("/api/all-user-stats")
@login_required
def get_all_user_stats():
    # You can add admin check here if needed
    stats = load_user_stats()
    return jsonify(stats)

# Serve audio files
@app.route("/audio/<path:filename>")
@login_required
def serve_audio(filename):
    return send_from_directory(AUDIO_FOLDER, filename)

# Endpoint to list user submissions
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

# Endpoint to list MOBILE_DATASET files
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

# Download from MOBILE_DATASET
@app.route("/mobile-dataset/<filename>")
@login_required
def download_mobile_dataset(filename):
    return send_from_directory(MOBILE_DATASET_FOLDER, filename, as_attachment=True)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8889, debug=False)