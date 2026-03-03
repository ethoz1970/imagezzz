from flask import Flask, request, jsonify, send_from_directory, render_template
import os
import base64
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

@app.route("/api/generate", methods=["POST"])
def generate():
    try:
        # Check if the request is multipart/form-data
        if not request.content_type.startswith('multipart/form-data'):
             # fallback to old behavior if JSON is still sent randomly
             prompt = request.json.get("prompt") if request.json else None
             skip_brain = request.json.get("skip_brain", False) if request.json else False
             strength = 0.75
             image_file = None
        else:
             prompt = request.form.get("prompt")
             skip_brain_str = request.form.get("skip_brain", "false").lower()
             skip_brain = skip_brain_str == "true" or skip_brain_str == "on"
             strength_str = request.form.get("strength")
             strength = float(strength_str) if strength_str else 0.75
             image_file = request.files.get("image")

        if not prompt:
            return jsonify({"error": "Missing 'prompt' in request body"}), 400

        init_image_path = None
        image_base64 = None
        
        # Save uploaded image and prepare for processing
        if image_file and image_file.filename != '':
            timestamp = int(time.time())
            init_image_path = os.path.join(UPLOAD_DIR, f"upload_{timestamp}_{image_file.filename}")
            image_file.save(init_image_path)
            
            with open(init_image_path, "rb") as image_f:
                image_base64 = base64.b64encode(image_f.read()).decode("utf-8")

        # Step 1: Brain (Expand Prompt)
        if skip_brain:
            final_prompt = prompt
            print(f"[API] Skipped Brain. Using raw prompt: '{final_prompt}'")
        else:
            final_prompt = enhance_prompt_with_ollama(prompt, image_base64)

        # Step 2: Brush (Generate Image)
        # Create a unique filename based on timestamp
        filename = f"generated_{int(time.time())}.png"
        output_path = os.path.join(OUTPUT_DIR, filename)
        
        generate_image_with_flux(final_prompt, output_path, init_image_path, strength)

        # Cleanup uploaded image
        if init_image_path and os.path.exists(init_image_path):
            try:
                os.remove(init_image_path)
            except Exception as e:
                print(f"[API] Cleanup error: {e}")

        # Return the public URL for the generated image and the expanded prompt
        image_url = f"/static/outputs/{filename}"
        
        return jsonify({
            "success": True,
            "image_url": image_url,
            "expanded_prompt": final_prompt
        })

    except Exception as e:
        print(f"[API] Error: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5075, debug=True)
