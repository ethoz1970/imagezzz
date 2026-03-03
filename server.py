from flask import Flask, request, jsonify, send_from_directory, render_template, Response
import os
import base64
import json
from pipeline import enhance_prompt_with_ollama, generate_image_with_flux
from flask_cors import CORS
import time

app = Flask(__name__)
CORS(app)

# Ensure output and upload directories exist
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "static", "outputs")
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "static", "uploads")
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(UPLOAD_DIR, exist_ok=True)

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/gallery")
def gallery():
    images = []
    if os.path.exists(OUTPUT_DIR):
        for filename in sorted(os.listdir(OUTPUT_DIR), reverse=True):
            if filename.endswith(".png"):
                image_path = os.path.join(OUTPUT_DIR, filename)
                metadata_path = image_path.replace('.png', '.json')
                
                metadata = {}
                try:
                    if os.path.exists(metadata_path):
                        with open(metadata_path, 'r') as f:
                            metadata = json.load(f)
                except Exception as e:
                    print(f"Error loading metadata for {filename}: {e}")
                
                # Provide defaults if metadata is missing
                images.append({
                    'filename': filename,
                    'url': f"/static/outputs/{filename}",
                    'prompt': metadata.get('prompt', 'N/A'),
                    'generation_time': metadata.get('generation_time', None),
                    'timestamp': metadata.get('timestamp', os.path.getctime(image_path))
                })
    return render_template("gallery.html", images=images)

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

        if not prompt:
            return jsonify({"error": "Missing 'prompt' in request body"}), 400

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
                        generate_image_with_flux(final_prompt, output_path, thread_progress_callback)
                        end_time = time.time()
                        generation_time = end_time - start_time
                        
                        # Save metadata
                        metadata = {
                            "prompt": final_prompt,
                            "original_prompt": prompt,
                            "timestamp": time.time(),
                            "generation_time": generation_time
                        }
                        meta_filename = filename.replace('.png', '.json')
                        with open(os.path.join(OUTPUT_DIR, meta_filename), 'w') as f:
                            json.dump(metadata, f)
                            
                        q.put({'status': 'done', 'image_url': f"/static/outputs/{filename}", 'expanded_prompt': final_prompt, 'generation_time': generation_time})
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

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5075, debug=True)
