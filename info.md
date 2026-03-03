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

*Note: We include `PYTORCH_ENABLE_MPS_FALLBACK=1` to ensure PyTorch can safely fall back to CPU operations if it encounters memory limitations on the Apple Silicon GPU during the memory-intensive FLUX generation process.*

```bash
PYTORCH_ENABLE_MPS_FALLBACK=1 python3 server.py
```

### 4. Access the UI
Once the terminal indicates the server is running, open your web browser and navigate to:

[http://127.0.0.1:5075](http://127.0.0.1:5075)

Type what you'd like to create, and click **Generate Image**! The Brain will expand your prompt, and the Brush will paint it. Depending on your hardware, generation usually takes 15 - 45 seconds.
