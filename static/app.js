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

    const promptReviewPanel = document.getElementById('prompt-review-panel');
    const elaboratedPromptTextarea = document.getElementById('elaborated-prompt');
    const rerollBtn = document.getElementById('reroll-btn');

    let currentPhase = 'initial'; // 'initial' or 'review'

    // Dynamic loading text phases


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
        rerollBtn.disabled = isLoading;
        elaboratedPromptTextarea.disabled = isLoading;

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

    const handleElaborationPhase = async (prompt, skipBrain) => {
        setFormState(true);
        btnText.textContent = "Elaborating Prompt...";

        try {
            const response = await fetch('/api/elaborate_prompt', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ prompt: prompt })
            });

            if (!response.ok) {
                const errText = await response.text();
                throw new Error(errText || 'Server returned an error during elaboration');
            }

            const data = await response.json();

            // Show review panel
            elaboratedPromptTextarea.value = data.expanded_prompt;
            promptReviewPanel.classList.remove('hidden');

            // Update buttons
            btnText.textContent = "Approve & Generate Image";
            promptInput.parentElement.classList.add('hidden');
            skipBrainToggle.parentElement.classList.add('hidden');
            currentPhase = 'review';

        } catch (error) {
            alert(`Elaboration failed: ${error.message || 'Unknown error'}`);
        } finally {
            setFormState(false);
        }
    };

    const handleGenerationPhase = async (finalPrompt) => {
        setFormState(true);
        btnText.textContent = "Generating...";
        showLoadingPanel(true); // Always true because brain is done

        const progressContainer = document.getElementById('progress-container');
        const progressBar = document.getElementById('progress-bar');
        progressContainer.classList.add('hidden');
        progressBar.style.width = '0%';

        try {
            const response = await fetch('/api/generate', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ prompt: finalPrompt, skip_brain: true })
            });

            if (!response.ok) {
                const errText = await response.text();
                throw new Error(errText || 'Server returned an error');
            }

            const reader = response.body.getReader();
            const decoder = new TextDecoder("utf-8");
            let buffer = "";

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n\n');
                buffer = lines.pop();

                for (const line of lines) {
                    if (line.startsWith('data: ')) {
                        const dataStr = line.slice(6);
                        try {
                            const data = JSON.parse(dataStr);
                            if (data.status === 'brush_start') {
                                statusText.textContent = "Brush is synthesizing image with FLUX...";
                                statusText.style.animation = "shine 1s linear infinite";
                                progressContainer.classList.remove('hidden');
                            } else if (data.status === 'brush_progress') {
                                progressBar.style.width = `${data.progress}%`;
                            } else if (data.status === 'done') {
                                displayResult(data.image_url, finalPrompt);
                                resetToInitialState();
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
    };

    const resetToInitialState = () => {
        currentPhase = 'initial';
        promptReviewPanel.classList.add('hidden');
        promptInput.parentElement.classList.remove('hidden');
        skipBrainToggle.parentElement.classList.remove('hidden');
        btnText.textContent = "Generate Image";
    }

    form.addEventListener('submit', async (e) => {
        e.preventDefault();

        if (currentPhase === 'initial') {
            const prompt = promptInput.value.trim();
            if (!prompt) return;
            const skipBrain = skipBrainToggle.checked;

            if (skipBrain) {
                handleGenerationPhase(prompt);
            } else {
                handleElaborationPhase(prompt, false);
            }
        } else if (currentPhase === 'review') {
            const finalPrompt = elaboratedPromptTextarea.value.trim();
            if (!finalPrompt) return;
            handleGenerationPhase(finalPrompt);
        }
    });

    rerollBtn.addEventListener('click', () => {
        const prompt = promptInput.value.trim();
        if (!prompt) return;
        handleElaborationPhase(prompt, false);
    });

    // Auto-resize textarea
    promptInput.addEventListener('input', function () {
        this.style.height = 'auto';
        this.style.height = (this.scrollHeight) + 'px';
    });
});
