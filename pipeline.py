import requests
import json
import argparse
import sys
import os
import subprocess
import re
import platform

# Configuration
OLLAMA_API_URL = "http://localhost:11434/api/generate"
VLM_MODEL = "llama3.2-vision" # We use this as our 'Brain'

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
    
    openai_key = os.environ.get("OPENAI_API_KEY")
    if openai_key:
        print(f"\n[Brain] OpenAI API Key Detected. Routing to gpt-4o-mini...")
        headers = {
            "Authorization": f"Bearer {openai_key}",
            "Content-Type": "application/json"
        }
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_intent}
        ]
        
        if image_base64:
            # Format base64 for OpenAI Vision
            messages[1]["content"] = [
                {"type": "text", "text": user_intent},
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{image_base64}"
                    }
                }
            ]
            print("[Brain] Reference image included for OpenAI vision expansion.")
            
        payload = {
            "model": "gpt-4o-mini",
            "messages": messages,
            "max_tokens": 150
        }
        
        try:
            response = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
            detailed_prompt = data["choices"][0]["message"]["content"].strip()
            print(f"[Brain] Generated Expanded Prompt (OpenAI):\n--> {detailed_prompt}\n")
            return detailed_prompt
        except requests.exceptions.HTTPError as e:
            err_msg = e.response.text if e.response else str(e)
            print(f"[Brain] OpenAI API Error: {err_msg}")
            raise Exception(f"OpenAI Error: {err_msg}")
        except Exception as e:
            print(f"[Brain] Error communicating with OpenAI: {e}")
            raise Exception(f"Failed to connect to OpenAI: {e}")
            
    # Fallback to local Ollama
    print(f"\n[Brain] Local Execution. Routing to Ollama ({VLM_MODEL})...")
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
        raise Exception("Ollama is not running locally. Please start Ollama or add an OPENAI_API_KEY to your environment variables.")

def generate_image_with_flux(prompt: str, output_path: str, size: int = 768, init_image_path: str = None, image_strength: float = 0.4, progress_callback: callable = None):
    """
    Acts as the 'Brush' computing node.
    Dynamically routes to Apple MLX (mflux) on Mac, or PyTorch (diffusers) on Linux.
    """
    fal_key = os.environ.get("FAL_KEY")
    if fal_key:
        print(f"[Brush] Fal.ai Key Detected. Routing to fal-ai/flux/schnell @ {size}x{size}...")
        headers = {
            "Authorization": f"Key {fal_key}",
            "Content-Type": "application/json"
        }
        
        # Fal.ai expects specific dimensions or custom
        image_size = "square_hd"
        if size == 1024:
            image_size = "square_hd"
        elif size == 512:
            image_size = "square"
            
        payload = {
            "prompt": prompt,
            "image_size": image_size,
            "num_inference_steps": 4,
            "num_images": 1,
            "enable_safety_checker": False
        }
        
        # If image to image is supported by fal's schnell, we would add the image URL here.
        # For now, fal-ai/flux/schnell is primarily T2I.
        if init_image_path:
            print("[Brush] WARNING: Image-to-Image requires specific endpoints on Fal.ai. Generating Text-to-Image.")
            
        try:
            if progress_callback:
                progress_callback(50) # Fake progress for API delay
                
            response = requests.post("https://fal.run/fal-ai/flux/schnell", headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
            
            if progress_callback:
                progress_callback(90)
                
            img_url = data.get("images", [])[0].get("url")
            
            # Download the resulting image to the local output_path
            img_data = requests.get(img_url).content
            with open(output_path, 'wb') as handler:
                handler.write(img_data)
                
            if progress_callback:
                progress_callback(100)
                
            print(f"[Brush] Success! Cloud image downloaded and saved to: {output_path}")
            return
            
        except Exception as e:
            print(f"[Brush] Error communicating with Fal.ai: {e}")
            print("[Brush] Falling back to local generation...")
            # Fall through to local generation below if cloud fails

    if platform.system() == "Darwin":
        print(f"[Brush] Apple Silicon Detected. Initializing FLUX.1 [schnell] via MLX (mflux-generate @ {size}x{size})...")
        
        cmd = [
            "mflux-generate",
            "--model", "schnell",
            "--quantize", "4",
            "--prompt", prompt,
            "--steps", "4",
            "--height", str(size),
            "--width", str(size),
            "--output", output_path
        ]
        
        if init_image_path:
            cmd.extend([
                "--image-path", init_image_path,
                "--image-strength", str(image_strength)
            ])
        
        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True
            )
            
            progress_pattern = re.compile(r'(\d{1,3})%\|')
            
            for line in process.stdout:
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

    else:
        # Linux / Windows fallback using standard Diffusers Pipeline
        print(f"[Brush] Linux Detected. Initializing FLUX.1 [schnell] via PyTorch/Diffusers @ {size}x{size}...")
        import torch
        from diffusers import FluxPipeline
        
        try:
            pipe = FluxPipeline.from_pretrained(
                "black-forest-labs/FLUX.1-schnell", 
                torch_dtype=torch.bfloat16
            )
            pipe.enable_model_cpu_offload() # Safest memory fallback for cloud instances by default
            
            def progress_fn(pipeline, step_index, timestep, callback_kwargs):
                if progress_callback:
                    percent = int((step_index / 4) * 100)
                    progress_callback(percent)
                return callback_kwargs

            if init_image_path:
                print("[Brush] WARNING: Image-to-Image requires specific Img2Img pipelines in Diffusers. Generating Text-to-Image for this node.")

            image = pipe(
                prompt,
                guidance_scale=0.0,
                num_inference_steps=4,
                max_sequence_length=256,
                height=size,
                width=size,
                callback_on_step_end=progress_fn
            ).images[0]
            
            image.save(output_path)
            print(f"[Brush] Success! Image saved to: {output_path}")
            
            # Explicitly free memory if moving back and forth
            del pipe
            if torch.cuda.is_available():
                torch.cuda.empty_cache()

        except Exception as e:
            print(f"[Brush] Error invoking Diffusers: {e}")

def main():
    parser = argparse.ArgumentParser(description="Brain-and-Brush Multimodal Image Synthesis Pipeline")
    parser.add_argument("prompt", type=str, help="The simple user intent or idea to generate.")
    parser.add_argument("--output", type=str, default="output.png", help="Path to save the generated image.")
    parser.add_argument("--size", type=int, default=768, help="Size of the image (e.g. 512, 768, 1024).")
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
    generate_image_with_flux(final_prompt, args.output, args.size)

if __name__ == "__main__":
    main()
