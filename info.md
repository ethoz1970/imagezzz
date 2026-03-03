# Symphony AI Image Generator

This project provides a local, highly-stylized web interface for generating images using a two-step "Brain and Brush" pipeline. 

## The Pipeline
1. **Brain:** A Vision Language Model (`llama3.2-vision` running via Ollama) expands a simple user intent into a highly descriptive, prompt-optimized string.
2. **Brush:** A state-of-the-art diffusion model (`FLUX.1-schnell` running via PyTorch) synthesizes the detailed prompt into a high-fidelity image.

## Setup & Running the UI

Follow these instructions to spin up the local web environment.

### 1. Automated Setup (Recommended)

If you are on an Apple Silicon Mac, you can run the provided setup script which will automatically verify your python version, pull the required Ollama models, create your virtual environment, and install all dependencies:

```bash
# Make sure Ollama desktop app is running in the background, then execute:
chmod +x setup.sh
./setup.sh
```

### 2. Manual Setup

If you prefer to set up the environment manually:

1. Make sure you have Ollama serving the Vision model:
   ```bash
   ollama serve
   ollama pull llama3.2-vision
   ```
2. Create and activate a Python virtual environment:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

### 3. Start the Web Server
The server is built with Flask and handles the API requests from the frontend UI. Start it using the command below. 

```bash
python3 server.py
```

### 4. Access the UI
Once the terminal indicates the server is running, open your web browser and navigate to:

[http://127.0.0.1:5075](http://127.0.0.1:5075)

Type what you'd like to create, and click **Generate Image**! The Brain will expand your prompt, and the Brush will paint it. Depending on your hardware, generation usually takes 15 - 45 seconds.

### 5. Shut Down the Servers
To shut down the servers, you can return to the terminal windows where they are running and press `Ctrl+C`. 

If you started them in the background and want to stop all related server processes, you can run the following commands:
```bash
pkill -f "python.*server.py"
pkill ollama
```

## Hosting Online

Because this application relies on a **15+ GB Vision LLM** and a **12+ GB Image Diffusion Model**, hosting it online requires significant GPU resources. Furthermore, we specifically architected this app to use Apple's `mlx` framework so it runs optimally on your Mac's Unified Memory. 

If you want to access this web UI from anywhere in the world, you have three main options:

### Option 1: Expose your Mac to the Internet (Free, Easiest)
The absolute easiest way to "host" this online is to keep it running on your Mac at home, and use a secure tunnel to expose the `localhost:5075` port to the public internet.

1. Install [ngrok](https://ngrok.com/) or use Cloudflare Tunnels (`cloudflared`).
2. Run `ngrok http 5075`.
3. Ngrok will give you a public URL (e.g., `https://1a2b-3c4d.ngrok-free.app`). 
4. You can open that URL on your phone or any computer in the world, and it will securely route the traffic back to your Mac to generate the images.

*Note: Your Mac must stay awake and connected to the internet for this to work.*

### Option 2: Cloud GPU Hosting (Scalable, Intermediate)
You could rent a Virtual Machine in the cloud from AWS, GCP, or a boutique GPU host like RunPod to host the backend generation servers.
* **Apple Silicon (This branch):** If you want to deploy *this exact codebase* using `mflux`, you can rent an **Apple Silicon Mac instance** from AWS (EC2 Mac instances) or Scaleway. This is very expensive (often $0.50 - $1.00+ per hour, 24/7).
* **NVIDIA/Linux GPUs (Alternative branch):** You can rent standard Linux NVIDIA GPUs (like RTX 4090s or A100s, which are widely available and much cheaper) if you check out the *original* branch of this project before we migrated to `mflux`. The original branch uses standard `PyTorch` and `Diffusers` which are natively designed to run on Linux machines.

### Option 3: Use Cloud APIs (Scalable, Modern)
If you want to host this robustly for many users, the standard industry practice is to *not* host the AI models yourself. 
1. Host the Flask Web Server (the UI and `server.py`) on a cheap $5/mo server (like DigitalOcean, Vercel, or Heroku).
2. Modify `pipeline.py` to make API calls to external providers instead of running local python scripts.
   * Send text to **OpenAI** or **Anthropic** for the "Brain" elaboration.
   * Send the elaborated text to **Replicate** or **Fal.ai** (they have incredibly fast FLUX.1 endpoints) for the image generation.
3. You pay pennies per generation rather than hundreds of dollars a month for a 24/7 GPU server.
