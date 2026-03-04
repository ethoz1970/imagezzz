from flask import Flask, request, jsonify, send_from_directory, render_template, Response
import os
import base64
import json
import uuid
import shutil
from pipeline import enhance_prompt_with_ollama, generate_image_with_flux
from flask_cors import CORS
import time

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

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/sessions")
def sessions_page():
    return render_template("sessions.html")

@app.route("/gallery")
def gallery():
    sessions = load_sessions()
    
    # Enrich sessions with their images
    for sid in sessions.keys():
        sessions[sid]['images'] = []

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
                if sid and sid in sessions:
                    sessions[sid]['images'].append({
                        'filename': filename,
                        'url': f"/static/outputs/{filename}",
                        'prompt': meta.get('prompt', 'N/A'),
                        'original_prompt': meta.get('original_prompt', ''),
                        'generation_time': meta.get('generation_time', None),
                        'timestamp': meta.get('timestamp', os.path.getctime(image_path))
                    })
                else:
                    # If an image has no session (e.g. from old version), make a dummy legacy session or group them?
                    # For now we'll put them in a "Legacy Images" session
                    if "legacy" not in sessions:
                        sessions["legacy"] = {
                            "id": "legacy",
                            "name": "Legacy Images",
                            "created_at": 0,
                            "images": []
                        }
                    sessions["legacy"]['images'].append({
                        'filename': filename,
                        'url': f"/static/outputs/{filename}",
                        'prompt': meta.get('prompt', 'N/A'),
                        'original_prompt': meta.get('original_prompt', ''),
                        'generation_time': meta.get('generation_time', None),
                        'timestamp': meta.get('timestamp', os.path.getctime(image_path))
                    })
                    
    # Return as list sorted by creation time (newest first)
    session_list = list(sessions.values())
    session_list.sort(key=lambda x: x.get('created_at', 0), reverse=True)
    
    # Filter out empty sessions just for the gallery view
    session_list = [s for s in session_list if len(s.get('images', [])) > 0]
    
    return render_template("gallery.html", sessions=session_list)

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

        # Session tracking
        sessions = load_sessions()
        session_name = ""
        if not session_id or session_id not in sessions:
            session_id = str(uuid.uuid4())
            snip = prompt[:30] + ("..." if len(prompt) > 30 else "")
            session_name = f"Session: {snip}"
            sessions[session_id] = {
                "id": session_id,
                "name": session_name,
                "created_at": time.time()
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
                            "session_id": session_id
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
    sessions = load_sessions()
    
    # Enrich sessions with their images
    for sid in sessions.keys():
        sessions[sid]['images'] = []

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
                if sid and sid in sessions:
                    sessions[sid]['images'].append({
                        'filename': filename,
                        'url': f"/static/outputs/{filename}",
                        'prompt': meta.get('prompt', 'N/A'),
                        'original_prompt': meta.get('original_prompt', ''),
                        'generation_time': meta.get('generation_time', None),
                        'timestamp': meta.get('timestamp', os.path.getctime(image_path))
                    })
                    
    # Return as list sorted by creation time (newest first)
    session_list = list(sessions.values())
    session_list.sort(key=lambda x: x.get('created_at', 0), reverse=True)
    return jsonify({"sessions": session_list}), 200

@app.route("/api/sessions/<session_id>", methods=["PUT"])
@require_admin
def rename_session(session_id):
    data = request.get_json() or {}
    new_name = data.get("name")
    if not new_name:
        return jsonify({"error": "Missing 'name'"}), 400
        
    sessions = load_sessions()
    if session_id not in sessions:
        return jsonify({"error": "Session not found"}), 404
        
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

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5075))
    app.run(host="0.0.0.0", port=port, debug=True)
