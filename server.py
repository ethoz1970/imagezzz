from flask import Flask, request, jsonify, send_from_directory, render_template, Response, make_response
import os
import base64
import json
import uuid
import shutil
from pipeline import enhance_prompt_with_ollama, generate_image_with_flux
from flask_cors import CORS
import time
import datetime

app = Flask(__name__)
CORS(app)

# Ensure output and upload directories exist
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "static", "outputs")
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "static", "uploads")
SESSION_FILE = os.path.join(OUTPUT_DIR, "sessions.json")
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(UPLOAD_DIR, exist_ok=True)

def load_sessions():
    if not os.path.exists(SESSION_FILE):
        return {}
    try:
        with open(SESSION_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {}

def save_sessions(sessions_data):
    with open(SESSION_FILE, "w") as f:
        json.dump(sessions_data, f, indent=4)

DAILY_LIMITS_FILE = os.path.join(OUTPUT_DIR, "daily_limits.json")
FREE_LIMIT = 5
PRO_LIMIT = 25
LIMIT_WINDOW_HOURS = 8
PRO_USERS_FILE = os.path.join(OUTPUT_DIR, "pro_users.json")

def load_daily_limits():
    if not os.path.exists(DAILY_LIMITS_FILE):
        return {}
    try:
        with open(DAILY_LIMITS_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {}

def save_daily_limits(limits_data):
    with open(DAILY_LIMITS_FILE, "w") as f:
        json.dump(limits_data, f, indent=4)

def get_usage_in_window(tracking_id):
    """Return (count, oldest_timestamp_or_None) of generations within the rolling window, pruning old entries."""
    limits = load_daily_limits()
    cutoff = time.time() - LIMIT_WINDOW_HOURS * 3600
    timestamps = limits.get(tracking_id, [])
    # Migrate from old format (dict with date/count) to new format (list of timestamps)
    if isinstance(timestamps, dict):
        timestamps = []
    timestamps = sorted([t for t in timestamps if t > cutoff])
    limits[tracking_id] = timestamps
    save_daily_limits(limits)
    oldest = timestamps[0] if timestamps else None
    return len(timestamps), oldest

def record_generation(tracking_id):
    """Record a generation timestamp for the user."""
    limits = load_daily_limits()
    cutoff = time.time() - LIMIT_WINDOW_HOURS * 3600
    timestamps = limits.get(tracking_id, [])
    if isinstance(timestamps, dict):
        timestamps = []
    timestamps = [t for t in timestamps if t > cutoff]
    timestamps.append(time.time())
    limits[tracking_id] = timestamps
    save_daily_limits(limits)

def load_pro_users():
    if not os.path.exists(PRO_USERS_FILE):
        return {}
    try:
        with open(PRO_USERS_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {}

def save_pro_users(pro_users):
    with open(PRO_USERS_FILE, "w") as f:
        json.dump(pro_users, f, indent=4)

def ensure_tracking_cookie(resp):
    if not request.cookies.get("tracking_id"):
        # Set cookie for 10 years
        resp.set_cookie("tracking_id", str(uuid.uuid4()), max_age=60*60*24*365*10)
    return resp

def _check_admin():
    admin_password = os.environ.get('ADMIN_PASSWORD')
    if admin_password:
        auth_header = request.headers.get('Authorization')
        if auth_header and auth_header.startswith('Bearer '):
            token = auth_header.split(' ')[1]
            if token == admin_password:
                return True
        # Also check query parameter (for browser page navigations)
        token = request.args.get('token')
        if token and token == admin_password:
            return True
    return False

def _check_pro():
    tracking_id = request.cookies.get("tracking_id")
    if not tracking_id:
        return False
    pro_users = load_pro_users()
    return tracking_id in pro_users

def _get_user_role():
    if _check_admin():
        return "admin"
    if _check_pro():
        return "pro"
    return "free"

@app.route("/")
def index():
    resp = make_response(render_template("index.html"))
    return ensure_tracking_cookie(resp)

@app.route("/sessions")
def sessions_page():
    resp = make_response(render_template("sessions.html"))
    return ensure_tracking_cookie(resp)

@app.route("/gallery")
def gallery():
    role = _get_user_role()

    tracking_id = request.cookies.get("tracking_id")
    if not tracking_id:
        tracking_id = request.remote_addr or "unknown_user"

    all_sessions = load_sessions()

    # Private sessions: user's own (or all for admin)
    if role == "admin":
        private_sessions = dict(all_sessions)
    else:
        private_sessions = {k: v for k, v in all_sessions.items() if v.get('tracking_id') == tracking_id}

    # Public sessions: all sessions with public images, grouped by session
    public_sessions = {}

    # Enrich sessions with their images
    for sid in private_sessions.keys():
        private_sessions[sid]['images'] = []
        private_sessions[sid]['is_public'] = private_sessions[sid].get('public', False)

    # Read all images once
    if os.path.exists(OUTPUT_DIR):
        for filename in sorted(os.listdir(OUTPUT_DIR), reverse=True):
            if filename.endswith(".png"):
                image_path = os.path.join(OUTPUT_DIR, filename)
                metadata_path = image_path.replace('.png', '.json')

                meta = {}
                if os.path.exists(metadata_path):
                    try:
                        with open(metadata_path, 'r') as f:
                            meta = json.load(f)
                    except Exception:
                        pass

                sid = meta.get('session_id')
                is_public_image = meta.get('public', False)

                image_data = {
                    'filename': filename,
                    'url': f"/static/outputs/{filename}",
                    'prompt': meta.get('prompt', 'N/A'),
                    'original_prompt': meta.get('original_prompt', ''),
                    'generation_time': meta.get('generation_time', None),
                    'timestamp': meta.get('timestamp', os.path.getctime(image_path)),
                    'is_public': is_public_image
                }

                # Add to private sessions (user's own)
                is_owned = role == "admin" or meta.get('tracking_id') == tracking_id
                if is_owned and sid and sid in private_sessions:
                    private_sessions[sid]['images'].append(image_data)
                elif is_owned and role == "admin" and sid and sid not in private_sessions:
                    if "legacy" not in private_sessions:
                        private_sessions["legacy"] = {
                            "id": "legacy",
                            "name": "Legacy Images",
                            "created_at": 0,
                            "images": []
                        }
                    private_sessions["legacy"]['images'].append(image_data)

                # Add to public sessions (all public images from all users)
                if is_public_image and sid and sid in all_sessions:
                    if sid not in public_sessions:
                        public_sessions[sid] = {
                            "id": sid,
                            "name": all_sessions[sid].get("name", "Unnamed Session"),
                            "created_at": all_sessions[sid].get("created_at", 0),
                            "images": []
                        }
                    # Public view: only show safe fields (no tracking_id, no generation_time)
                    public_sessions[sid]['images'].append({
                        'filename': filename,
                        'url': f"/static/outputs/{filename}",
                        'original_prompt': meta.get('original_prompt', ''),
                        'timestamp': meta.get('timestamp', os.path.getctime(image_path))
                    })

    # Sort and filter
    private_list = list(private_sessions.values())
    private_list.sort(key=lambda x: x.get('created_at', 0), reverse=True)
    private_list = [s for s in private_list if len(s.get('images', [])) > 0]

    public_list = list(public_sessions.values())
    public_list.sort(key=lambda x: x.get('created_at', 0), reverse=True)

    resp = make_response(render_template("gallery.html", private_sessions=private_list, public_sessions=public_list))
    return ensure_tracking_cookie(resp)

@app.route("/api/elaborate_prompt", methods=["POST"])
def elaborate_prompt():
    try:
        data = request.get_json() or {}
        prompt = data.get("prompt")

        if not prompt:
            return jsonify({"error": "Missing 'prompt' in request body"}), 400

        # Step 1: Brain (Expand Prompt)
        final_prompt = enhance_prompt_with_ollama(prompt, None)
        
        return jsonify({"expanded_prompt": final_prompt}), 200

    except Exception as e:
        print(f"[API] Elaboration Outer Error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/generate", methods=["POST"])
def generate():
    try:
        data = request.get_json() or {}
        prompt = data.get("prompt")
        skip_brain = data.get("skip_brain", False)
        size = data.get("size", 768)
        reference_image = data.get("reference_image")
        image_strength = float(data.get("image_strength", 0.4))
        session_id = data.get("session_id")

        if not prompt:
            return jsonify({"error": "Missing 'prompt' in request body"}), 400

        role = _get_user_role()

        tracking_id = request.cookies.get("tracking_id")
        if not tracking_id:
            tracking_id = request.remote_addr or "unknown_user"

        if role == "free":
            if size > 512:
                return jsonify({"error": "Pro Access required for Medium and Large images."}), 403

            usage, _ = get_usage_in_window(tracking_id)
            if usage >= FREE_LIMIT:
                return jsonify({"error": f"You have reached your limit of {FREE_LIMIT} images per {LIMIT_WINDOW_HOURS} hours. Upgrade to Pro for more generations."}), 429
            record_generation(tracking_id)

        elif role == "pro":
            usage, _ = get_usage_in_window(tracking_id)
            if usage >= PRO_LIMIT:
                return jsonify({"error": f"You have reached your Pro limit of {PRO_LIMIT} images per {LIMIT_WINDOW_HOURS} hours."}), 429
            record_generation(tracking_id)

        # admin: no limits, no size restriction

        # Session tracking
        sessions = load_sessions()
        session_name = ""
        if not session_id or session_id not in sessions:
            session_id = str(uuid.uuid4())
            snip = prompt[:30] + ("..." if len(prompt) > 30 else "")
            session_name = snip
            sessions[session_id] = {
                "id": session_id,
                "name": session_name,
                "created_at": time.time(),
                "tracking_id": tracking_id
            }
            save_sessions(sessions)
        else:
            session_name = sessions[session_id].get("name", "Unnamed Session")

        def generate_stream():
            try:
                # Step 0: Track start time
                start_time = time.time()

                # Step 1: Brain (Expand Prompt)
                if skip_brain:
                    final_prompt = prompt
                    print(f"[API] Skipped Brain. Using raw prompt: '{final_prompt}'")
                    yield f"data: {json.dumps({'status': 'brain_done', 'expanded_prompt': final_prompt})}\n\n"
                else:
                    yield f"data: {json.dumps({'status': 'brain_start'})}\n\n"
                    final_prompt = enhance_prompt_with_ollama(prompt, None)
                    yield f"data: {json.dumps({'status': 'brain_done', 'expanded_prompt': final_prompt})}\n\n"

                # Step 2: Brush (Generate Image)
                filename = f"generated_{int(time.time())}.png"
                output_path = os.path.join(OUTPUT_DIR, filename)
                
                yield f"data: {json.dumps({'status': 'brush_start'})}\n\n"
                
                def progress_update(percent):
                    # We must use a separate yielding queue or similar trick for true async yielding from a sync callback in Flask.
                    # For simplicity in this generator, we will print it, 
                    # but if we yield from inside the callback it won't pipe out directly.
                    # Wait, we CANNOT yield from a callback that diffusers calls synchronously deep in its stack 
                    # unless we run diffusers in a thread and use a Queue to pass messages back to this generator.
                    pass
                
                # Let's import queue and threading right here for the generator scope
                import threading
                import queue
                q = queue.Queue()
                
                def thread_progress_callback(percent):
                    q.put({'status': 'brush_progress', 'progress': percent})
                    
                def run_generation():
                    try:
                        # Resolve relative references to absolute paths
                        init_image_path = None
                        if reference_image:
                            # e.g: '/static/outputs/generated_123.png' -> 'static/outputs/generated_123.png'
                            clean_rel_path = reference_image.lstrip('/')
                            init_image_path = os.path.join(os.path.dirname(__file__), clean_rel_path)

                        generate_image_with_flux(
                            prompt=final_prompt, 
                            output_path=output_path, 
                            size=size, 
                            init_image_path=init_image_path,
                            image_strength=image_strength,
                            progress_callback=thread_progress_callback
                        )
                        end_time = time.time()
                        generation_time = end_time - start_time
                        
                        # Save metadata
                        metadata = {
                            "prompt": final_prompt,
                            "original_prompt": prompt,
                            "timestamp": time.time(),
                            "generation_time": generation_time,
                            "session_id": session_id,
                            "tracking_id": tracking_id,
                            "public": False
                        }
                        meta_filename = filename.replace('.png', '.json')
                        with open(os.path.join(OUTPUT_DIR, meta_filename), 'w') as f:
                            json.dump(metadata, f)
                            
                        q.put({
                            'status': 'done', 
                            'image_url': f"/static/outputs/{filename}", 
                            'expanded_prompt': final_prompt, 
                            'generation_time': generation_time,
                            'session_id': session_id,
                            'session_name': session_name
                        })
                    except Exception as e:
                        q.put({'status': 'error', 'error': str(e)})

                thread = threading.Thread(target=run_generation)
                thread.start()
                
                # Consume the queue and yield to client
                while True:
                    msg = q.get()
                    yield f"data: {json.dumps(msg)}\n\n"
                    if msg.get('status') in ['done', 'error']:
                        break

                thread.join()

            except Exception as e:
                print(f"[API] Error: {e}")
                yield f"data: {json.dumps({'status': 'error', 'error': str(e)})}\n\n"
        
        # Ensure the stream doesn't get buffered by intermediate proxies or Flask
        return Response(generate_stream(), mimetype='text/event-stream', headers={'X-Accel-Buffering': 'no', 'Cache-Control': 'no-cache'})

    except Exception as e:
        print(f"[API] Outer Error: {e}")
        return jsonify({"error": str(e)}), 500

# --- Admin Authentication ---
from functools import wraps

def require_admin(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        admin_password = os.environ.get("ADMIN_PASSWORD")
        # If no password is set in the environment, we assume beta mode is OPEN (or you can disable it)
        # For security, let's require it to be set to perform destructive actions.
        if not admin_password:
            return jsonify({"error": "Admin password not configured on server"}), 403
            
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return jsonify({"error": "Unauthorized"}), 401
            
        token = auth_header.split(' ')[1]
        if token != admin_password:
            return jsonify({"error": "Invalid admin password"}), 403
            
        return f(*args, **kwargs)
    return decorated_function

# --- REST API For Sessions ---
@app.route("/api/sessions", methods=["GET"])
def get_sessions():
    role = _get_user_role()

    tracking_id = request.cookies.get("tracking_id")
    if not tracking_id:
        tracking_id = request.remote_addr or "unknown_user"

    sessions = load_sessions()

    # Filter sessions for non-admin users
    if role != "admin":
        sessions = {k: v for k, v in sessions.items() if v.get('tracking_id') == tracking_id}

    # Enrich sessions with their images
    for sid in sessions.keys():
        sessions[sid]['images'] = []
        sessions[sid]['is_public'] = sessions[sid].get('public', False)

    if os.path.exists(OUTPUT_DIR):
        for filename in sorted(os.listdir(OUTPUT_DIR), reverse=True):
            if filename.endswith(".png"):
                image_path = os.path.join(OUTPUT_DIR, filename)
                metadata_path = image_path.replace('.png', '.json')

                meta = {}
                if os.path.exists(metadata_path):
                    try:
                        with open(metadata_path, 'r') as f:
                            meta = json.load(f)
                    except Exception:
                        pass

                # Check image ownership for non-admin users
                if role != "admin" and meta.get('tracking_id') != tracking_id:
                    continue

                sid = meta.get('session_id')
                if sid and sid in sessions:
                    sessions[sid]['images'].append({
                        'filename': filename,
                        'url': f"/static/outputs/{filename}",
                        'prompt': meta.get('prompt', 'N/A'),
                        'original_prompt': meta.get('original_prompt', ''),
                        'generation_time': meta.get('generation_time', None),
                        'timestamp': meta.get('timestamp', os.path.getctime(image_path)),
                        'is_public': meta.get('public', False)
                    })

    # Return as list sorted by creation time (newest first)
    session_list = list(sessions.values())
    session_list.sort(key=lambda x: x.get('created_at', 0), reverse=True)
    return jsonify({"sessions": session_list}), 200

@app.route("/api/sessions/<session_id>", methods=["PUT"])
def rename_session(session_id):
    data = request.get_json() or {}
    new_name = data.get("name")
    if not new_name:
        return jsonify({"error": "Missing 'name'"}), 400

    sessions = load_sessions()
    if session_id not in sessions:
        return jsonify({"error": "Session not found"}), 404

    # Check ownership or admin
    tracking_id = request.cookies.get("tracking_id") or request.remote_addr or "unknown_user"
    if not _check_admin() and sessions[session_id].get('tracking_id') != tracking_id:
        return jsonify({"error": "Unauthorized"}), 403

    sessions[session_id]["name"] = new_name
    save_sessions(sessions)
    return jsonify({"success": True, "session": sessions[session_id]}), 200

@app.route("/api/sessions/<session_id>", methods=["DELETE"])
@require_admin
def delete_session(session_id):
    sessions = load_sessions()
    if session_id not in sessions:
        return jsonify({"error": "Session not found"}), 404
        
    # Delete the images
    if os.path.exists(OUTPUT_DIR):
        for filename in os.listdir(OUTPUT_DIR):
            if filename.endswith(".png"):
                metadata_path = os.path.join(OUTPUT_DIR, filename.replace('.png', '.json'))
                if os.path.exists(metadata_path):
                    try:
                        with open(metadata_path, 'r') as f:
                            meta = json.load(f)
                        if meta.get('session_id') == session_id:
                            # matches, delete png and json
                            os.remove(os.path.join(OUTPUT_DIR, filename))
                            os.remove(metadata_path)
                    except Exception as e:
                        print(f"Error deleting {filename}: {e}")
                        
    # Delete session entry
    del sessions[session_id]
    save_sessions(sessions)
    return jsonify({"success": True}), 200

@app.route("/api/limits", methods=["GET"])
def get_limits():
    role = _get_user_role()

    if role == "admin":
        return jsonify({"role": "admin", "is_pro": True, "remaining": "∞"})

    tracking_id = request.cookies.get("tracking_id")
    if not tracking_id:
        tracking_id = request.remote_addr or "unknown_user"

    usage, oldest = get_usage_in_window(tracking_id)
    resets_at = (oldest + LIMIT_WINDOW_HOURS * 3600) if oldest else None

    if role == "pro":
        remaining = max(0, PRO_LIMIT - usage)
        resp = {"role": "pro", "is_pro": True, "remaining": remaining, "total": PRO_LIMIT}
        if remaining == 0 and resets_at:
            resp["resets_at"] = resets_at
        return jsonify(resp)

    remaining = max(0, FREE_LIMIT - usage)
    resp = {"role": "free", "is_pro": False, "remaining": remaining, "total": FREE_LIMIT}
    if remaining == 0 and resets_at:
        resp["resets_at"] = resets_at
    return jsonify(resp)

@app.route("/api/image/<filename>", methods=["DELETE"])
@require_admin
def delete_image(filename):
    if not filename.endswith('.png'):
        return jsonify({"error": "Invalid file type"}), 400
        
    image_path = os.path.join(OUTPUT_DIR, filename)
    metadata_path = image_path.replace('.png', '.json')
    
    if os.path.exists(image_path):
        try:
            os.remove(image_path)
            if os.path.exists(metadata_path):
                os.remove(metadata_path)
            return jsonify({"success": True}), 200
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    else:
        return jsonify({"error": "Image not found"}), 404

@app.route("/api/image/<filename>/public", methods=["PATCH"])
def toggle_image_public(filename):
    if not filename.endswith('.png'):
        return jsonify({"error": "Invalid file type"}), 400

    metadata_path = os.path.join(OUTPUT_DIR, filename.replace('.png', '.json'))
    if not os.path.exists(metadata_path):
        return jsonify({"error": "Image metadata not found"}), 404

    try:
        with open(metadata_path, 'r') as f:
            meta = json.load(f)
    except Exception:
        return jsonify({"error": "Failed to read metadata"}), 500

    # Check ownership or admin
    tracking_id = request.cookies.get("tracking_id") or request.remote_addr or "unknown_user"
    is_admin = _check_admin()
    if not is_admin and meta.get('tracking_id') != tracking_id:
        return jsonify({"error": "Unauthorized"}), 403

    meta['public'] = not meta.get('public', False)
    with open(metadata_path, 'w') as f:
        json.dump(meta, f)

    return jsonify({"success": True, "public": meta['public']}), 200

@app.route("/api/sessions/<session_id>/public", methods=["PATCH"])
def toggle_session_public(session_id):
    sessions = load_sessions()
    if session_id not in sessions:
        return jsonify({"error": "Session not found"}), 404

    # Check ownership or admin
    tracking_id = request.cookies.get("tracking_id") or request.remote_addr or "unknown_user"
    is_admin = _check_admin()
    if not is_admin and sessions[session_id].get('tracking_id') != tracking_id:
        return jsonify({"error": "Unauthorized"}), 403

    new_public = not sessions[session_id].get('public', False)
    sessions[session_id]['public'] = new_public
    save_sessions(sessions)

    # Bulk-update all image metadata files in this session
    if os.path.exists(OUTPUT_DIR):
        for filename in os.listdir(OUTPUT_DIR):
            if filename.endswith(".json") and filename not in ("sessions.json", "daily_limits.json", "pro_users.json"):
                meta_path = os.path.join(OUTPUT_DIR, filename)
                try:
                    with open(meta_path, 'r') as f:
                        meta = json.load(f)
                    if meta.get('session_id') == session_id:
                        meta['public'] = new_public
                        with open(meta_path, 'w') as f:
                            json.dump(meta, f)
                except Exception:
                    pass

    return jsonify({"success": True, "public": new_public}), 200

@app.route("/api/pro", methods=["GET"])
@require_admin
def list_pro_users():
    pro_users = load_pro_users()
    return jsonify({"pro_users": pro_users}), 200

@app.route("/api/pro/<tracking_id>", methods=["POST"])
@require_admin
def grant_pro(tracking_id):
    pro_users = load_pro_users()
    pro_users[tracking_id] = {"granted_at": int(time.time())}
    save_pro_users(pro_users)
    return jsonify({"success": True, "tracking_id": tracking_id}), 200

@app.route("/api/pro/<tracking_id>", methods=["DELETE"])
@require_admin
def revoke_pro(tracking_id):
    pro_users = load_pro_users()
    if tracking_id not in pro_users:
        return jsonify({"error": "Tracking ID not found in pro users"}), 404
    del pro_users[tracking_id]
    save_pro_users(pro_users)
    return jsonify({"success": True, "tracking_id": tracking_id}), 200

@app.route("/admin")
def admin_panel():
    if not _check_admin():
        return "Forbidden", 403

    all_sessions = load_sessions()

    # Enrich sessions with their images
    for sid in all_sessions.keys():
        all_sessions[sid]['images'] = []

    if os.path.exists(OUTPUT_DIR):
        for filename in sorted(os.listdir(OUTPUT_DIR), reverse=True):
            if filename.endswith(".png"):
                image_path = os.path.join(OUTPUT_DIR, filename)
                metadata_path = image_path.replace('.png', '.json')

                meta = {}
                if os.path.exists(metadata_path):
                    try:
                        with open(metadata_path, 'r') as f:
                            meta = json.load(f)
                    except Exception:
                        pass

                sid = meta.get('session_id')
                image_data = {
                    'filename': filename,
                    'url': f"/static/outputs/{filename}",
                    'prompt': meta.get('prompt', 'N/A'),
                    'original_prompt': meta.get('original_prompt', ''),
                    'generation_time': meta.get('generation_time', None),
                    'timestamp': meta.get('timestamp', os.path.getctime(image_path)),
                    'is_public': meta.get('public', False)
                }

                if sid and sid in all_sessions:
                    all_sessions[sid]['images'].append(image_data)
                else:
                    if "legacy" not in all_sessions:
                        all_sessions["legacy"] = {
                            "id": "legacy",
                            "name": "Legacy Images",
                            "created_at": 0,
                            "tracking_id": "unknown",
                            "images": []
                        }
                    all_sessions["legacy"]['images'].append(image_data)

    session_list = list(all_sessions.values())
    session_list.sort(key=lambda x: x.get('created_at', 0), reverse=True)
    session_list = [s for s in session_list if len(s.get('images', [])) > 0]

    resp = make_response(render_template("admin.html", all_sessions=session_list))
    return ensure_tracking_cookie(resp)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5075))
    app.run(host="0.0.0.0", port=port, debug=True)
