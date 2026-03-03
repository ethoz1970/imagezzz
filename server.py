from flask import Flask, request, jsonify, send_from_directory, render_template
import os
from pipeline import enhance_prompt_with_ollama, generate_image_with_flux
from flask_cors import CORS
import time

app = Flask(__name__)
CORS(app)

# Ensure output directory exists
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "static", "outputs")
os.makedirs(OUTPUT_DIR, exist_ok=True)

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/generate", methods=["POST"])
def generate():
    try:
        data = request.json
        if not data or "prompt" not in data:
            return jsonify({"error": "Missing 'prompt' in request body"}), 400

        user_prompt = data["prompt"]
        skip_brain = data.get("skip_brain", False)

        # Step 1: Brain (Expand Prompt)
        if skip_brain:
            final_prompt = user_prompt
            print(f"[API] Skipped Brain. Using raw prompt: '{final_prompt}'")
        else:
            final_prompt = enhance_prompt_with_ollama(user_prompt)

        # Step 2: Brush (Generate Image)
        # Create a unique filename based on timestamp
        filename = f"generated_{int(time.time())}.png"
        output_path = os.path.join(OUTPUT_DIR, filename)
        
        generate_image_with_flux(final_prompt, output_path)

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
