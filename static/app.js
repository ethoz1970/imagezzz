document.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('generate-form');
    const promptInput = document.getElementById('prompt-input');
    const skipBrainToggle = document.getElementById('skip-brain');
    const sizeRadios = document.querySelectorAll('input[name="size"]');
    const freemiumRadios = document.querySelectorAll('.freemium-restricted');

    const generateBtn = document.getElementById('generate-btn');
    const btnText = generateBtn.querySelector('.btn-text');
    const btnLoader = generateBtn.querySelector('.btn-loader');

    const resultContainer = document.getElementById('result-container');
    const imageQueue = document.getElementById('image-queue');

    const promptDetails = document.getElementById('prompt-details');
    const expandedPromptText = document.getElementById('expanded-prompt-text');
    const finalTimeText = document.getElementById('final-time-text');

    const promptReviewPanel = document.getElementById('prompt-review-panel');
    const elaboratedPromptTextarea = document.getElementById('elaborated-prompt');
    const rerollBtn = document.getElementById('reroll-btn');
    const newPromptBtn = document.getElementById('new-prompt-btn');

    const referencePanel = document.getElementById('reference-panel');
    const referenceThumbnail = document.getElementById('reference-thumbnail');
    const imageStrengthSlider = document.getElementById('image-strength-slider');
    const imageStrengthValue = document.getElementById('image-strength-value');
    const clearReferenceBtn = document.getElementById('clear-reference-btn');

    const sessionHeaderContainer = document.getElementById('session-header-container');
    const currentSessionName = document.getElementById('current-session-name');

    const generationCounter = document.getElementById('generation-counter');
    const generationsLeftText = document.getElementById('generations-left');

    let currentPhase = 'initial'; // 'initial' or 'review'
    let activeReferenceImage = null;
    let currentSessionId = null;

    // Fetch and display limits
    const updateLimitsDisplay = async () => {
        try {
            const headers = {};
            const adminToken = localStorage.getItem('admin_token');
            if (adminToken) {
                headers['Authorization'] = `Bearer ${adminToken}`;
            }

            const response = await fetch('/api/limits', { headers });
            if (response.ok) {
                const data = await response.json();
                generationCounter.classList.remove('hidden');

                if (data.is_pro) {
                    generationsLeftText.textContent = "Pro User";
                    generationsLeftText.style.color = "var(--accent-glow)";
                } else {
                    generationsLeftText.textContent = `${data.remaining}/${data.total} Left`;
                    if (data.remaining === 0) {
                        generationsLeftText.style.color = "#ff4444";
                    } else {
                        generationsLeftText.style.color = "white";
                    }
                }
            }
        } catch (e) {
            console.error("Failed to fetch limits", e);
        }
    };

    // Initial fetch
    updateLimitsDisplay();

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

    // Freemium Radio Listeners
    freemiumRadios.forEach(radio => {
        radio.addEventListener('click', (e) => {
            if (!localStorage.getItem('admin_token')) {
                e.preventDefault();
                window.openUpsellModal();
            }
        });
    });

    // Image Modal Event Delegation
    document.addEventListener('click', (e) => {
        if (e.target.classList.contains('generated-image')) {
            window.openModal(e.target.src);
        }
    });

    const updateLoadingText = (skipBrain, statusTextElement) => {
        if (skipBrain) {
            statusTextElement.textContent = loadingStates.brush;
        } else {
            statusTextElement.textContent = loadingStates.brain;

            // Simulate progression to brush after a few seconds since we don't have SSE
            loadingInterval = setTimeout(() => {
                statusTextElement.textContent = loadingStates.brush;
                statusTextElement.style.animation = "shine 1s linear infinite"; // Faster animation for brush
            }, 3000); // Rough estimate for Ollama inference text time
        }
    };

    const setFormState = (isLoading) => {
        promptInput.disabled = isLoading;
        skipBrainToggle.disabled = isLoading;
        sizeRadios.forEach(radio => radio.disabled = isLoading);
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

    const showLoadingPanel = (skipBrain, prompt) => {
        resultContainer.classList.remove('hidden');
        resultContainer.classList.add('fade-in');

        // Create new image wrapper for the queue
        const wrapper = document.createElement('div');
        wrapper.className = 'image-wrapper';
        wrapper.innerHTML = `
            <div style="position: relative;">
                <img class="generated-image" src="" alt="Generated artwork" style="opacity: 0; width: 100%; height: auto; object-fit: contain; transition: opacity 0.5s ease; border-radius: 8px;">
                <div class="image-overlay">
                    <div class="spinner"></div>
                    <p class="status-text">${skipBrain ? loadingStates.brush : loadingStates.brain}</p>
                    <div class="progress-container hidden">
                        <div class="progress-bar" style="width: 0%;"></div>
                    </div>
                    <p class="generation-timer" style="font-size: 0.9rem; margin-top: 0.5rem;">0.0s</p>
                </div>
            </div>
            <div class="image-actions" style="margin-top: 0.75rem; display: flex; gap: 0.5rem; width: 100%; padding: 0.5rem 1rem 1rem 1rem;">
                <a href="#" download class="action-btn download-btn hidden" style="flex: 0 0 auto; padding: 0.5rem 1rem; justify-content: center;" title="Download Artwork">
                    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
                        <polyline points="7 10 12 15 17 10"></polyline>
                        <line x1="12" y1="15" x2="12" y2="3"></line>
                    </svg>
                    <span style="margin-left: 0.4rem; font-size: 0.85rem;">Download</span>
                </a>
                <button type="button" class="action-btn set-reference-btn hidden" title="Use as Reference Image for next generation" style="flex: 1; padding: 0.5rem; justify-content: center;">
                    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="margin-right: 0.4rem;">
                        <circle cx="12" cy="12" r="10"></circle>
                        <line x1="12" y1="8" x2="12" y2="12"></line>
                        <line x1="12" y1="16" x2="12.01" y2="16"></line>
                    </svg>
                    Use as Reference
                </button>
            </div>
        `;

        // Prepend to top of queue
        imageQueue.insertBefore(wrapper, imageQueue.firstChild);
        promptDetails.classList.remove('hidden'); // Ensure details are visible

        const timeDisplay = wrapper.querySelector('.generation-timer');
        const statusTextDisplay = wrapper.querySelector('.status-text');

        // Start timer for this specific card
        startTime = Date.now();
        clearInterval(timerInterval);
        timerInterval = setInterval(() => {
            const elapsed = (Date.now() - startTime) / 1000;
            timeDisplay.textContent = `${elapsed.toFixed(1)}s`;
        }, 100);

        updateLoadingText(skipBrain, statusTextDisplay);

        // Return refs so fetch loop can update the specific elements
        return {
            wrapper: wrapper,
            img: wrapper.querySelector('.generated-image'),
            overlay: wrapper.querySelector('.image-overlay'),
            statusText: statusTextDisplay,
            progressContainer: wrapper.querySelector('.progress-container'),
            progressBar: wrapper.querySelector('.progress-bar'),
            timerDisplay: timeDisplay,
            setRefBtn: wrapper.querySelector('.set-reference-btn'),
            downloadBtn: wrapper.querySelector('.download-btn')
        };
    };

    const displayResult = (uiRefs, imageUrl, expandedPrompt) => {
        clearTimeout(loadingInterval);
        clearInterval(timerInterval);
        const totalTime = ((Date.now() - startTime) / 1000).toFixed(1);
        finalTimeText.textContent = `${totalTime}s`;
        uiRefs.timerDisplay.classList.add('hidden');

        // Load image unseen first to avoid flash, then fade in
        uiRefs.img.onload = () => {
            uiRefs.overlay.style.opacity = '0';
            setTimeout(() => {
                uiRefs.overlay.classList.add('hidden');
                uiRefs.img.style.opacity = '1';
            }, 300); // wait for fade out
        };

        uiRefs.img.src = imageUrl;

        // Hook up the reference button
        if (uiRefs.setRefBtn) {
            uiRefs.setRefBtn.classList.remove('hidden');
            // If this image is currently the active reference, style it as selected
            if (activeReferenceImage === imageUrl) {
                uiRefs.setRefBtn.classList.add('selected-reference');
            }
            uiRefs.setRefBtn.addEventListener('click', (e) => {
                e.preventDefault();
                setAsReference(imageUrl, uiRefs.setRefBtn);
            });
        }

        // Set up the download button
        if (uiRefs.downloadBtn) {
            uiRefs.downloadBtn.href = imageUrl;
            const filename = imageUrl.split('/').pop();
            uiRefs.downloadBtn.download = filename;
            uiRefs.downloadBtn.classList.remove('hidden');
        }

        // Ensure we always have some prompt details
        expandedPromptText.textContent = expandedPrompt || promptInput.value;
    };

    const setAsReference = (imageUrl, clickedBtn) => {
        activeReferenceImage = imageUrl;
        referenceThumbnail.src = imageUrl;
        referencePanel.classList.remove('hidden');

        // Remove selected styling from all reference buttons
        document.querySelectorAll('.set-reference-btn, .set-ref-btn').forEach(btn => {
            btn.classList.remove('selected-reference');
        });
        // Add styling to the clicked one
        if (clickedBtn) {
            clickedBtn.classList.add('selected-reference');
        }

        window.scrollTo({ top: 0, behavior: 'smooth' }); // scroll up to see controls
    };

    const handleError = (uiRefs, error) => {
        clearTimeout(loadingInterval);
        clearInterval(timerInterval);
        uiRefs.timerDisplay.classList.add('hidden');
        uiRefs.overlay.classList.add('hidden');
        uiRefs.statusText.textContent = "Error generating image.";
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
            skipBrainToggle.parentElement.classList.add('hidden');
            rerollBtn.classList.remove('hidden');
            newPromptBtn.classList.remove('hidden');
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
        const uiRefs = showLoadingPanel(true, finalPrompt); // Always true because brain is done

        try {
            const selectedSizeElement = document.querySelector('input[name="size"]:checked');
            const selectedSize = selectedSizeElement ? selectedSizeElement.value : '768';

            const headers = {
                'Content-Type': 'application/json'
            };

            const adminToken = localStorage.getItem('admin_token');
            if (adminToken) {
                headers['Authorization'] = `Bearer ${adminToken}`;
            }

            const response = await fetch('/api/generate', {
                method: 'POST',
                headers: headers,
                body: JSON.stringify({
                    prompt: finalPrompt,
                    skip_brain: true,
                    size: parseInt(selectedSize) || 768,
                    reference_image: activeReferenceImage,
                    image_strength: parseFloat(imageStrengthSlider.value),
                    session_id: currentSessionId
                })
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

                let shouldBreak = false;

                for (const line of lines) {
                    if (line.startsWith('data: ')) {
                        const dataStr = line.slice(6);
                        try {
                            const data = JSON.parse(dataStr);
                            if (data.status === 'brush_start') {
                                uiRefs.statusText.textContent = "Brush is synthesizing image with FLUX...";
                                uiRefs.statusText.style.animation = "shine 1s linear infinite";
                                uiRefs.progressContainer.classList.remove('hidden');
                            } else if (data.status === 'brush_progress') {
                                uiRefs.progressBar.style.width = `${data.progress}%`;
                            } else if (data.status === 'done') {
                                if (data.session_id) {
                                    currentSessionId = data.session_id;
                                    if (data.session_name) {
                                        currentSessionName.innerText = data.session_name;
                                        sessionHeaderContainer.classList.remove('hidden');
                                    }
                                }
                                displayResult(uiRefs, data.image_url, finalPrompt);
                                updateLimitsDisplay(); // Update limits after generation
                                shouldBreak = true;
                            } else if (data.status === 'error') {
                                throw new Error(data.error);
                            }
                        } catch (e) {
                            // If the parsing fails above or we purposefully throw an Error to exit
                            if (e.message && e.message !== "Failed to parse stream chunk") {
                                throw e; // Let it propagate to the outer catch(error)
                            } else {
                                console.error("Failed to parse stream chunk", e, dataStr);
                            }
                        }
                    }
                }

                if (shouldBreak) break;
            }
        } catch (error) {
            handleError(uiRefs, error);
        } finally {
            setFormState(false);
            if (currentPhase === 'review') {
                btnText.textContent = "Generate Another";
            } else {
                btnText.textContent = "Generate Image";
            }
        }
    };

    const resetToInitialState = () => {
        currentPhase = 'initial';
        promptReviewPanel.classList.add('hidden');
        referencePanel.classList.add('hidden');
        activeReferenceImage = null;
        promptInput.parentElement.classList.remove('hidden');
        skipBrainToggle.parentElement.classList.remove('hidden');
        rerollBtn.classList.add('hidden');
        newPromptBtn.classList.add('hidden');
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

    newPromptBtn.addEventListener('click', () => {
        promptInput.value = '';
        elaboratedPromptTextarea.value = '';
        imageQueue.innerHTML = '';
        resultContainer.classList.add('hidden');
        promptInput.style.height = 'auto'; // reset textarea expansion

        activeReferenceImage = null;
        referencePanel.classList.add('hidden');
        sessionHeaderContainer.classList.add('hidden');

        resetToInitialState();
        promptInput.focus();
    });

    // Reference Panel controls
    imageStrengthSlider.addEventListener('input', (e) => {
        imageStrengthValue.textContent = parseFloat(e.target.value).toFixed(2);
    });

    clearReferenceBtn.addEventListener('click', () => {
        activeReferenceImage = null;
        referencePanel.classList.add('hidden');
        // Remove selected state from buttons
        document.querySelectorAll('.set-reference-btn, .set-ref-btn').forEach(btn => {
            btn.classList.remove('selected-reference');
        });
    });

    // Active session rename logic
    currentSessionName.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            currentSessionName.blur();
        }
    });

    currentSessionName.addEventListener('blur', async () => {
        if (!currentSessionId) return;
        const newName = currentSessionName.innerText.trim();
        if (!newName) return;

        try {
            await fetch(`/api/sessions/${currentSessionId}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name: newName })
            });
        } catch (e) {
            console.error("Failed to rename active session", e);
        }
    });

    // Auto-resize textarea
    promptInput.addEventListener('input', function () {
        this.style.height = 'auto';
        this.style.height = (this.scrollHeight) + 'px';
    });

    // Handle initialization for resuming sessions
    const urlParams = new URLSearchParams(window.location.search);
    const sessionIdToResume = urlParams.get('session_id');

    if (sessionIdToResume) {
        currentSessionId = sessionIdToResume;
        // Fetch session data to rebuild queue
        fetch('/api/sessions')
            .then(res => res.json())
            .then(data => {
                const session = data.sessions.find(s => s.id === sessionIdToResume);
                if (session && session.images && session.images.length > 0) {
                    // pre-load the prompt
                    const latestImage = session.images[0]; // Assuming newest first
                    promptInput.value = latestImage.original_prompt || latestImage.prompt;

                    if (session.name) {
                        currentSessionName.innerText = session.name;
                        sessionHeaderContainer.classList.remove('hidden');
                    }

                    // Set up review panel directly without re-rolling prompt
                    elaboratedPromptTextarea.value = latestImage.prompt;
                    promptReviewPanel.classList.remove('hidden');

                    btnText.textContent = "Generate Another";
                    skipBrainToggle.parentElement.classList.add('hidden');
                    rerollBtn.classList.remove('hidden');
                    newPromptBtn.classList.remove('hidden');
                    currentPhase = 'review';

                    // Rebuild the queue visually
                    resultContainer.classList.remove('hidden');
                    session.images.forEach(img => {
                        const wrapper = document.createElement('div');
                        wrapper.className = 'image-wrapper fade-in';

                        // Action buttons block
                        const actionsHtml = `
                            <div class="image-actions">
                                <a href="${img.url}" download="${img.filename}" class="action-btn" style="margin-right: 0.5rem;" title="Download Artwork">
                                    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
                                        <polyline points="7 10 12 15 17 10"></polyline>
                                        <line x1="12" y1="15" x2="12" y2="3"></line>
                                    </svg>
                                </a>
                                <button class="action-btn set-ref-btn" data-url="${img.url}" title="Use as Reference Image for next generation">
                                    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="margin-right: 0.4rem;">
                                        <circle cx="12" cy="12" r="10"></circle>
                                        <line x1="12" y1="8" x2="12" y2="12"></line>
                                        <line x1="12" y1="16" x2="12.01" y2="16"></line>
                                    </svg>
                                    Use as Reference
                                </button>
                            </div>
                        `;

                        wrapper.innerHTML = `
                            <div class="result-image-container">
                                <img src="${img.url}" alt="${img.prompt}" class="generated-image" style="cursor: pointer;">
                                ${actionsHtml}
                            </div>
                        `;

                        // Add listener for reference button
                        const setRefBtn = wrapper.querySelector('.set-ref-btn');
                        if (setRefBtn) {
                            if (activeReferenceImage === img.url) {
                                setRefBtn.classList.add('selected-reference');
                            }
                            setRefBtn.addEventListener('click', (e) => {
                                e.preventDefault();
                                setAsReference(img.url, setRefBtn);
                            });
                        }

                        imageQueue.appendChild(wrapper);
                    });
                }
            })
            .catch(err => console.error("Error loading resumed session:", err));
    }
});

// Modal Logic
window.openModal = function (imageSrc) {
    const modal = document.getElementById('image-modal');
    const modalImg = document.getElementById('modal-image');
    if (modal && modalImg) {
        modalImg.src = imageSrc;
        modal.classList.add('active');
        document.body.style.overflow = 'hidden';
    }
};

window.closeModal = function () {
    const modal = document.getElementById('image-modal');
    if (modal) {
        modal.classList.remove('active');
        document.body.style.overflow = '';
    }
};

window.openUpsellModal = function () {
    const modal = document.getElementById('upsell-modal');
    if (modal) {
        modal.classList.add('active');
        document.body.style.overflow = 'hidden';
    }
};

window.closeUpsellModal = function () {
    const modal = document.getElementById('upsell-modal');
    if (modal) {
        modal.classList.remove('active');
        document.body.style.overflow = '';
    }
};

// Admin Login Shortcut (Ctrl+Shift+A)
document.addEventListener('keydown', (e) => {
    if (e.ctrlKey && e.shiftKey && e.key.toLowerCase() === 'a') {
        e.preventDefault();
        const pwd = prompt("Enter Admin Password:");
        if (pwd) {
            localStorage.setItem('admin_token', pwd);
            alert("Admin token saved locally. Pro features unlocked.");
            location.reload(); // Reload to update UI and Limits
        } else {
            localStorage.removeItem('admin_token');
            alert("Admin token cleared.");
            location.reload();
        }
    }
});
