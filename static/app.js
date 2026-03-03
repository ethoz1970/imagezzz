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

        updateLoadingText(skipBrain);
    };

    const displayResult = (imageUrl, expandedPrompt) => {
        clearTimeout(loadingInterval);

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
                body: formData // Browser automatically sets Content-Type to multipart/form-data with bounds
            });

            const data = await response.json();

            if (!response.ok || !data.success) {
                throw new Error(data.error || 'Server returned an error');
            }

            // Success Update
            displayResult(data.image_url, data.expanded_prompt);

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
