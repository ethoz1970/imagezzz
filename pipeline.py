import requests
import json
import torch
import argparse
import sys
import os
import base64
from PIL import Image
from diffusers import FluxPipeline, FluxImg2ImgPipeline

# Configuration
OLLAMA_API_URL = "http://localhost:11434/api/generate"
VLM_MODEL = "llama3.2-vision" # We use this as our 'Brain'
FLUX_MODEL_ID = "black-forest-labs/FLUX.1-schnell" # We use this as our 'Brush'

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

def generate_image_with_flux(prompt: str, output_path: str, init_image_path: str = None, strength: float = 0.75):
    """
    Acts as the 'Brush' computing node.
    Takes a detailed prompt and synthesizes a high-fidelity image using FLUX.1 [schnell] 
    on the Apple MPS backend.
    """
    print("[Brush] Initializing FLUX.1 [schnell] pipeline on MPS...")
    
    # 1. Device and dtype Selection for Apple Silicon (M4)
    # MPS (Metal Performance Shaders) is required for hardware acceleration on Mac.
    # bfloat16 helps keep the large FLUX model within the 24GB Unified Memory limit.
    device = "mps"
    dtype = torch.bfloat16
    
    try:
        # 2. Load the Pipeline
        if init_image_path:
            pipe = FluxImg2ImgPipeline.from_pretrained(
                FLUX_MODEL_ID,
                torch_dtype=dtype
            )
        else:
            pipe = FluxPipeline.from_pretrained(
                FLUX_MODEL_ID,
                torch_dtype=dtype
            )
        
        # Enable model CPU offloading and VAE optimizations to save system memory
        pipe.enable_model_cpu_offload(device=device)
        pipe.vae.enable_slicing()
        pipe.vae.enable_tiling()
        
        # 3. Generate Image
        if init_image_path:
            print(f"[Brush] Synthesizing Image-to-Image (strength {strength})...")
            init_image = Image.open(init_image_path).convert("RGB")
            
            # Optionally resize image to save memory, but we'll try full res first
            image = pipe(
                prompt=prompt,
                image=init_image,
                strength=strength,
                num_inference_steps=4,
                guidance_scale=0.0,
                generator=torch.Generator("cpu").manual_seed(0)
            ).images[0]
        else:
            print(f"[Brush] Synthesizing image (4 steps)...")
            image = pipe(
                prompt=prompt,
                guidance_scale=0.0,
                num_inference_steps=4,
                max_sequence_length=256,
                generator=torch.Generator("cpu").manual_seed(0) 
            ).images[0]
        
        # 4. Save Output
        image.save(output_path)
        print(f"[Brush] Success! Image saved to: {output_path}")
        
    except Exception as e:
        print(f"[Brush] Error during image synthesis: {e}")
        print("[Brush] Note: If encountering memory errors, ensure PYTORCH_ENABLE_MPS_FALLBACK=1 is set.")

def main():
    parser = argparse.ArgumentParser(description="Brain-and-Brush Multimodal Image Synthesis Pipeline")
    parser.add_argument("prompt", type=str, help="The simple user intent or idea to generate.")
    parser.add_argument("--output", type=str, default="output.png", help="Path to save the generated image.")
    parser.add_argument("--skip-brain", action="store_true", help="Skip the LLM expansion and use the raw prompt directly.")
    
    args = parser.parse_args()
    
    # Check if PYTORCH_ENABLE_MPS_FALLBACK is set, warn if not
    if not os.environ.get("PYTORCH_ENABLE_MPS_FALLBACK"):
        print("Warning: PYTORCH_ENABLE_MPS_FALLBACK is not set. Some PyTorch ops for FLUX might crash on MPS.")
        print("Consider running with: PYTORCH_ENABLE_MPS_FALLBACK=1 python pipeline.py ...\n")
    
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
