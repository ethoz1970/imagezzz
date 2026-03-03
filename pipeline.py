import requests
import json
import argparse
import sys
import os
import subprocess
import re

# Configuration
OLLAMA_API_URL = "http://localhost:11434/api/generate"
VLM_MODEL = "llama3.2-vision" # We use this as our 'Brain'
MAX_IMAGE_SIZE = 768 # Limit resolution to save RAM

def enhance_prompt_with_ollama(user_intent: str, image_base64: str = None) -> str:
    """
    Acts as the 'Brain' computing node.
    Takes a simple user intent and uses a Vision Language Model to expand it into 
    a highly detailed, descriptive prompt suitable for a diffusion model.
    """
    print(f"\n[Brain] Analyzing intent: '{user_intent}'")
    
    system_prompt = (
        "You are an expert prompt engineer for advanced text-to-image diffusion models like FLUX. "
        "Your task is to take a simple user concept and expand it into a highly detailed, visually descriptive prompt. "
        "Include details about lighting, camera angle, focal length, color grading, atmosphere, and artistic style if applicable. "
        "Keep the description highly concise and under 300 words to avoid exceeding diffusion token limits. "
        "Do not include any introductory or explanatory text. Output ONLY the raw descriptive prompt."
    )
    
    payload = {
        "model": VLM_MODEL,
        "system": system_prompt,
        "prompt": user_intent,
        "stream": False
    }
    
    if image_base64:
        payload["images"] = [image_base64]
        print("[Brain] Reference image included for prompt expansion.")
    
    try:
        response = requests.post(OLLAMA_API_URL, json=payload)
        response.raise_for_status()
        data = response.json()
        detailed_prompt = data.get("response", "").strip()
        print(f"[Brain] Generated Expanded Prompt:\n--> {detailed_prompt}\n")
        return detailed_prompt
    except Exception as e:
        print(f"[Brain] Error communicating with Ollama: {e}")
        print("[Brain] Falling back to original prompt.")
        return user_intent

def generate_image_with_flux(prompt: str, output_path: str, progress_callback: callable = None):
    """
    Acts as the 'Brush' computing node.
    Takes a detailed prompt and synthesizes a high-fidelity image using Apple MLX (mflux).
    Runs via subprocess to ensure memory is released perfectly after generation.
    Optionally reports generation progress by parsing tqdm output.
    """
    print(f"[Brush] Initializing FLUX.1 [schnell] via MLX (mflux-generate @ {MAX_IMAGE_SIZE}x{MAX_IMAGE_SIZE})...")
    
    cmd = [
        "mflux-generate",
        "--model", "schnell",
        "--quantize", "4",
        "--prompt", prompt,
        "--steps", "4",
        "--height", str(MAX_IMAGE_SIZE),
        "--width", str(MAX_IMAGE_SIZE),
        "--output", output_path
    ]
    
    try:
        # Run mflux-generate and capture output to parse progress
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True
        )
        
        # Regex to catch tqdm progress percentage
        progress_pattern = re.compile(r'(\d{1,3})%\|')
        
        for line in process.stdout:
            # sys.stdout.write(line) # optional: echo to terminal if desired
            if progress_callback:
                match = progress_pattern.search(line)
                if match:
                    percent = int(match.group(1))
                    progress_callback(percent)
                    
        process.wait()
        
        if process.returncode == 0:
            print(f"[Brush] Success! Image saved to: {output_path}")
        else:
            print(f"[Brush] Error during image synthesis. Process exited with code {process.returncode}")
            
    except Exception as e:
        print(f"[Brush] Error invoking mflux: {e}")

def main():
    parser = argparse.ArgumentParser(description="Brain-and-Brush Multimodal Image Synthesis Pipeline")
    parser.add_argument("prompt", type=str, help="The simple user intent or idea to generate.")
    parser.add_argument("--output", type=str, default="output.png", help="Path to save the generated image.")
    parser.add_argument("--skip-brain", action="store_true", help="Skip the LLM expansion and use the raw prompt directly.")
    
    args = parser.parse_args()
    
    # Run script
    
    # Step 1: Brain (Expand Prompt)
    if args.skip_brain:
        final_prompt = args.prompt
        print(f"[Brain] Skipped. Using raw prompt: '{final_prompt}'")
    else:
        # Note: CLI doesn't currently support image base64, so it passes None
        final_prompt = enhance_prompt_with_ollama(args.prompt)
        
    # Step 2: Brush (Generate Image)
    # Note: CLI doesn't currently accept image, we pass None
    generate_image_with_flux(final_prompt, args.output)

if __name__ == "__main__":
    main()
