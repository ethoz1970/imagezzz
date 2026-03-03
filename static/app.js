document.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('generate-form');
    const promptInput = document.getElementById('prompt-input');
    const skipBrainToggle = document.getElementById('skip-brain');
    const generateBtn = document.getElementById('generate-btn');
    const btnText = generateBtn.querySelector('.btn-text');
    const btnLoader = generateBtn.querySelector('.btn-loader');

    const resultContainer = document.getElementById('result-container');
    const generatedImage = document.getElementById('generated-image');
    const loadingOverlay = document.getElementById('loading-overlay');
    const statusText = document.getElementById('loading-text');

    const promptDetails = document.getElementById('prompt-details');
    const expandedPromptText = document.getElementById('expanded-prompt-text');
    const generationTimer = document.getElementById('generation-timer');
    const finalTimeText = document.getElementById('final-time-text');

    const dropZone = document.getElementById('drop-zone');
    const fileInput = document.getElementById('file-input');
    const previewContainer = document.getElementById('image-preview-container');
    const imagePreview = document.getElementById('image-preview');
    const removeBtn = document.getElementById('remove-image-btn');

    const strengthContainer = document.getElementById('strength-container');
    const strengthSlider = document.getElementById('strength-slider');
    const strengthVal = document.getElementById('strength-val');

    let currentImageFile = null;

    // Drag & Drop handlers
    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
        if (dropZone) dropZone.addEventListener(eventName, preventDefaults, false);
    });

    function preventDefaults(e) {
        e.preventDefault();
        e.stopPropagation();
    }

    ['dragenter', 'dragover'].forEach(eventName => {
        if (dropZone) dropZone.addEventListener(eventName, () => dropZone.classList.add('drop-zone--over'), false);
    });

    ['dragleave', 'drop'].forEach(eventName => {
        if (dropZone) dropZone.addEventListener(eventName, () => dropZone.classList.remove('drop-zone--over'), false);
    });

    if (dropZone) {
        dropZone.addEventListener('drop', (e) => {
            const dt = e.dataTransfer;
            const files = dt.files;
            handleFiles(files);
        });

        dropZone.addEventListener('click', () => {
            if (!currentImageFile) fileInput.click();
        });
    }

    if (fileInput) {
        fileInput.addEventListener('change', function () {
            handleFiles(this.files);
        });
    }

    function handleFiles(files) {
        if (files.length) {
            const file = files[0];
            if (file.type.startsWith('image/')) {
                currentImageFile = file;
                const reader = new FileReader();
                reader.readAsDataURL(file);
                reader.onload = () => {
                    imagePreview.src = reader.result;
                    previewContainer.classList.remove('hidden');
                    strengthContainer.classList.remove('hidden');
                };
            } else {
                alert("Please upload an image file.");
            }
        }
    }

    if (removeBtn) {
        removeBtn.addEventListener('click', (e) => {
            e.stopPropagation(); // prevent triggering the click on dropzone
            currentImageFile = null;
            fileInput.value = '';
            imagePreview.src = '';
            previewContainer.classList.add('hidden');
            strengthContainer.classList.add('hidden');
        });
    }

    // Slider value update
    if (strengthSlider) {
        strengthSlider.addEventListener('input', (e) => {
            strengthVal.textContent = parseFloat(e.target.value).toFixed(2);
        });
    }

    // Dynamic loading text phases
    const loadingStates = {
        brain: "Brain is analyzing intent and expanding prompt...",
        brush: "Brush is synthesizing image with FLUX...",
        finalizing: "Applying final polish..."
    };

    let loadingInterval;
    let timerInterval;
    let startTime;

    const updateLoadingText = (skipBrain) => {
        if (skipBrain) {
            statusText.textContent = loadingStates.brush;
        } else {
            statusText.textContent = loadingStates.brain;

            // Simulate progression to brush after a few seconds since we don't have SSE
            loadingInterval = setTimeout(() => {
                statusText.textContent = loadingStates.brush;
                statusText.style.animation = "shine 1s linear infinite"; // Faster animation for brush
            }, 3000); // Rough estimate for Ollama inference text time
        }
    };

    const setFormState = (isLoading) => {
        promptInput.disabled = isLoading;
        skipBrainToggle.disabled = isLoading;
        generateBtn.disabled = isLoading;

        if (isLoading) {
            btnText.style.opacity = '0';
            btnLoader.classList.remove('hidden');
        } else {
            btnText.style.opacity = '1';
            btnLoader.classList.add('hidden');
        }
    };

    const showLoadingPanel = (skipBrain) => {
        resultContainer.classList.remove('hidden');
        resultContainer.classList.add('fade-in');

        // Hide previous results
        generatedImage.style.opacity = '0';
        promptDetails.classList.add('hidden');

        // Show loading overlay
        loadingOverlay.classList.remove('hidden');
        loadingOverlay.style.opacity = '1';

        // Start timer
        startTime = Date.now();
        generationTimer.textContent = '0.0s';
        generationTimer.classList.remove('hidden');
        clearInterval(timerInterval);
        timerInterval = setInterval(() => {
            const elapsed = (Date.now() - startTime) / 1000;
            generationTimer.textContent = `${elapsed.toFixed(1)}s`;
        }, 100);

        updateLoadingText(skipBrain);
    };

    const displayResult = (imageUrl, expandedPrompt) => {
        clearTimeout(loadingInterval);
        clearInterval(timerInterval);
        const totalTime = ((Date.now() - startTime) / 1000).toFixed(1);
        finalTimeText.textContent = `${totalTime}s`;
        generationTimer.classList.add('hidden');

        // Load image unseen first to avoid flash, then fade in
        generatedImage.onload = () => {
            loadingOverlay.style.opacity = '0';
            setTimeout(() => {
                loadingOverlay.classList.add('hidden');
                generatedImage.style.opacity = '1';
            }, 300); // wait for fade out
        };

        generatedImage.src = imageUrl;

        // Ensure we always have some prompt details
        promptDetails.classList.remove('hidden');
        expandedPromptText.textContent = expandedPrompt || promptInput.value;
    };

    const handleError = (error) => {
        clearTimeout(loadingInterval);
        clearInterval(timerInterval);
        generationTimer.classList.add('hidden');
        loadingOverlay.classList.add('hidden');
        statusText.textContent = "Error generating image.";
        alert(`Synthesis failed: ${error.message || 'Unknown error'}`);
    };

    form.addEventListener('submit', async (e) => {
        e.preventDefault();

        const prompt = promptInput.value.trim();
        if (!prompt) return;

        const skipBrain = skipBrainToggle.checked;

        try {
            // UI Updates
            setFormState(true);
            showLoadingPanel(skipBrain);

            // Reset progress bar
            const progressContainer = document.getElementById('progress-container');
            const progressBar = document.getElementById('progress-bar');
            progressContainer.classList.add('hidden');
            progressBar.style.width = '0%';

            // API Call
            const formData = new FormData();
            formData.append('prompt', prompt);
            formData.append('skip_brain', skipBrain);

            if (currentImageFile) {
                formData.append('image', currentImageFile);
                formData.append('strength', strengthSlider.value);
            }

            const response = await fetch('/api/generate', {
                method: 'POST',
                body: formData
            });

            if (!response.ok) {
                const errText = await response.text();
                throw new Error(errText || 'Server returned an error');
            }

            // Stream Processing
            const reader = response.body.getReader();
            const decoder = new TextDecoder("utf-8");
            let buffer = "";

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n\n');

                // Keep the last partial chunk in the buffer
                buffer = lines.pop();

                for (const line of lines) {
                    if (line.startsWith('data: ')) {
                        const dataStr = line.slice(6);
                        try {
                            const data = JSON.parse(dataStr);

                            // Event handling
                            if (data.status === 'brain_start') {
                                statusText.textContent = "Brain is analyzing intent and expanding prompt...";
                            } else if (data.status === 'brain_done') {
                                // Brain finished, prompt expanded
                                expandedPromptText.textContent = data.expanded_prompt;
                            } else if (data.status === 'brush_start') {
                                statusText.textContent = "Brush is synthesizing image with FLUX...";
                                statusText.style.animation = "shine 1s linear infinite";
                                progressContainer.classList.remove('hidden');
                            } else if (data.status === 'brush_progress') {
                                progressBar.style.width = `${data.progress}%`;
                            } else if (data.status === 'done') {
                                // Success
                                displayResult(data.image_url, data.expanded_prompt);
                            } else if (data.status === 'error') {
                                throw new Error(data.error);
                            }
                        } catch (e) {
                            console.error("Failed to parse stream chunk", e, dataStr);
                        }
                    }
                }
            }

        } catch (error) {
            handleError(error);
        } finally {
            setFormState(false);
        }
    });

    // Auto-resize textarea
    promptInput.addEventListener('input', function () {
        this.style.height = 'auto';
        this.style.height = (this.scrollHeight) + 'px';
    });
});
