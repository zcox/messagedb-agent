// Chat UI logic for the agent display service
// This script handles user input and HTML rendering with streaming progress

const THREAD_ID = window.THREAD_ID;
let currentHTML = null;
let isProcessing = false;
let agentMessageEl = null;
let htmlBuffer = '';
let toolIndicators = {};

/**
 * Update the progress indicator
 * @param {string} message - Progress message to display
 * @param {object|null} details - Optional progress details
 */
function updateProgress(message, details = null) {
    const progressDiv = document.getElementById('progress-indicator');
    if (!progressDiv) return;

    progressDiv.style.display = 'block';
    progressDiv.querySelector('.progress-message').textContent = message;

    // Update details if provided
    if (details) {
        const detailsText = Object.entries(details)
            .map(([key, value]) => `${key}: ${value}`)
            .join(', ');
        progressDiv.querySelector('.progress-details').textContent = detailsText;
    }
}

/**
 * Hide the progress indicator
 */
function hideProgress() {
    const progressDiv = document.getElementById('progress-indicator');
    if (progressDiv) {
        progressDiv.style.display = 'none';
    }
}

/**
 * Display a real-time agent event in the event log
 * @param {object} event - Agent event from Message DB
 */
function displayAgentEvent(event) {
    const progressDiv = document.getElementById('progress-indicator');
    if (!progressDiv) return;

    progressDiv.style.display = 'block';

    // Format event for display
    const eventType = event.type || 'Unknown';
    const timestamp = new Date(event.time).toLocaleTimeString();

    // Create a summary message based on event type
    let message = `${timestamp} - ${eventType}`;
    let details = null;

    // Customize display based on event type
    if (eventType === 'UserMessageAdded') {
        message = `${timestamp} - User message: ${event.data.message?.substring(0, 50) || ''}...`;
    } else if (eventType === 'LLMResponseReceived') {
        const text = event.data.text || event.data.content || '';
        message = `${timestamp} - LLM response (${text.length} chars)`;
        details = { tool_calls: event.data.tool_calls?.length || 0 };
    } else if (eventType === 'ToolExecutionRequested') {
        message = `${timestamp} - Calling tool: ${event.data.name || 'unknown'}`;
        details = event.data.arguments || {};
    } else if (eventType === 'ToolExecutionCompleted') {
        message = `${timestamp} - Tool result: ${event.data.name || 'unknown'}`;
    } else if (eventType.includes('Error')) {
        message = `${timestamp} - ⚠️ ${eventType}`;
    }

    updateProgress(message, details);
}

/**
 * Create a streaming message bubble for agent responses
 * @param {string} role - Message role ('agent' or 'user')
 * @returns {HTMLElement} The created message element
 */
function createStreamingMessageBubble(role) {
    let container = document.getElementById('rendered-content');
    if (!container) {
        container = document.createElement('div');
        container.id = 'rendered-content';
        document.body.insertBefore(container, document.body.firstChild);
    }

    const messageDiv = document.createElement('div');
    messageDiv.className = `message message-${role} message-streaming`;
    messageDiv.innerHTML = '<div class="message-content"></div><div class="message-tools"></div>';
    container.appendChild(messageDiv);

    // Scroll to bottom
    container.scrollTop = container.scrollHeight;

    return messageDiv;
}

/**
 * Append text to a streaming message
 * @param {HTMLElement} messageEl - The message element
 * @param {string} text - Text to append
 */
function appendTextToMessage(messageEl, text) {
    if (!messageEl) return;

    const contentDiv = messageEl.querySelector('.message-content');
    if (!contentDiv) return;

    contentDiv.textContent += text;

    // Scroll to bottom
    const container = document.getElementById('rendered-content');
    if (container) {
        container.scrollTop = container.scrollHeight;
    }
}

/**
 * Show a tool call indicator in the message
 * @param {HTMLElement} messageEl - The message element
 * @param {string} name - Tool name
 * @param {string} id - Tool call ID
 */
function showToolCallIndicator(messageEl, name, id) {
    if (!messageEl) return;

    const toolsDiv = messageEl.querySelector('.message-tools');
    if (!toolsDiv) return;

    const indicator = document.createElement('div');
    indicator.className = 'tool-indicator tool-pending';
    indicator.id = `tool-${id}`;
    indicator.innerHTML = `<span class="tool-name">${name}</span><span class="tool-status">pending</span>`;
    toolsDiv.appendChild(indicator);

    toolIndicators[name] = indicator;
}

/**
 * Update tool execution status
 * @param {string} name - Tool name
 * @param {string} status - Status ('executing' or 'complete')
 */
function updateToolStatus(name, status) {
    const indicator = toolIndicators[name];
    if (!indicator) return;

    indicator.className = `tool-indicator tool-${status}`;
    indicator.querySelector('.tool-status').textContent = status;
}

/**
 * Show token usage information
 * @param {object} tokenUsage - Token usage data
 */
function showTokenUsage(tokenUsage) {
    if (!tokenUsage) return;

    updateProgress('LLM processing complete', {
        input_tokens: tokenUsage.input_tokens,
        output_tokens: tokenUsage.output_tokens
    });
}

/**
 * Finalize the agent message (remove streaming indicator)
 * @param {HTMLElement} messageEl - The message element
 */
function finalizeAgentMessage(messageEl) {
    if (!messageEl) return;

    messageEl.classList.remove('message-streaming');
}

/**
 * Show rendering progress
 * @param {number} bytesReceived - Number of bytes received
 */
function showRenderingProgress(bytesReceived) {
    updateProgress('Rendering formatted view...', {
        bytes: bytesReceived
    });
}

/**
 * Display final HTML in the container
 * @param {string} html - HTML content to display
 */
function displayFinalHTML(html) {
    let container = document.getElementById('rendered-content');
    if (!container) {
        container = document.createElement('div');
        container.id = 'rendered-content';
        document.body.insertBefore(container, document.body.firstChild);
    }

    container.innerHTML = html;

    // Scroll to bottom
    container.scrollTop = container.scrollHeight;
}

/**
 * Refresh the display using Server-Sent Events for progress updates
 * @param {string|null} userMessage - Optional user message to send
 */
async function refresh(userMessage = null) {
    try {
        // Show loading state when processing user message
        if (userMessage) {
            isProcessing = true;
            updateUIState();
            updateProgress('Starting...', null);
        }

        // Use fetch to POST the request, then process SSE stream
        const resp = await fetch('/render-stream', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                thread_id: THREAD_ID,
                user_message: userMessage,
                previous_html: currentHTML
            })
        });

        if (!resp.ok) {
            throw new Error(`HTTP ${resp.status}: ${resp.statusText}`);
        }

        // Process the SSE stream
        const reader = resp.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
            const {done, value} = await reader.read();
            if (done) break;

            // Decode the chunk and add to buffer
            buffer += decoder.decode(value, {stream: true});

            // Process complete SSE messages (ending with \n\n)
            const messages = buffer.split('\n\n');
            buffer = messages.pop() || ''; // Keep incomplete message in buffer

            for (const message of messages) {
                if (!message.trim()) continue;

                // Parse SSE message
                const lines = message.split('\n');
                let eventType = 'message';
                let data = null;

                for (const line of lines) {
                    if (line.startsWith('event: ')) {
                        eventType = line.substring(7);
                    } else if (line.startsWith('data: ')) {
                        data = JSON.parse(line.substring(6));
                    }
                }

                // Handle different event types
                if (eventType === 'message' && data) {
                    // Progress update (legacy)
                    updateProgress(data.message, data.details);
                } else if (eventType === 'agent_event' && data) {
                    // Real-time agent event from Message DB subscriber
                    displayAgentEvent(data);
                } else if (eventType === 'agent_start' && data) {
                    // Agent streaming started - create message bubble
                    agentMessageEl = createStreamingMessageBubble('agent');
                    toolIndicators = {};
                    updateProgress('Agent processing...', null);
                } else if (eventType === 'agent_delta' && data) {
                    // Agent streaming delta - handle different delta types
                    switch (data.type) {
                        case 'llm_text':
                            appendTextToMessage(agentMessageEl, data.text);
                            break;
                        case 'llm_tool_call':
                            showToolCallIndicator(agentMessageEl, data.name, data.id);
                            break;
                        case 'tool_executing':
                            updateToolStatus(data.name, 'executing');
                            updateProgress(`Executing tool: ${data.name}`, null);
                            break;
                        case 'tool_complete':
                            updateToolStatus(data.name, 'complete');
                            break;
                        case 'llm_done':
                            showTokenUsage(data.token_usage);
                            break;
                    }
                } else if (eventType === 'agent_complete' && data) {
                    // Agent streaming completed
                    finalizeAgentMessage(agentMessageEl);
                    updateProgress('Rendering formatted view...', null);
                } else if (eventType === 'html_start' && data) {
                    // HTML rendering started
                    htmlBuffer = '';
                    showRenderingProgress(0);
                } else if (eventType === 'html_chunk' && data) {
                    // HTML chunk received
                    htmlBuffer += data.chunk;
                    showRenderingProgress(htmlBuffer.length);
                } else if (eventType === 'result' && data) {
                    // Final result
                    currentHTML = data.html;
                    displayFinalHTML(data.html);
                    hideProgress();
                } else if (eventType === 'error' && data) {
                    // Error occurred
                    throw new Error(data.error);
                }
            }
        }

    } catch (error) {
        console.error('Refresh failed:', error);

        // Create or get the container for error display
        let container = document.getElementById('rendered-content');
        if (!container) {
            container = document.createElement('div');
            container.id = 'rendered-content';
            // Insert at the beginning of body
            document.body.insertBefore(container, document.body.firstChild);
        }

        container.innerHTML =
            `<div style="color: red; padding: 20px;">Error: ${error.message}</div>`;
        hideProgress();
    } finally {
        if (userMessage) {
            isProcessing = false;
            updateUIState();
        }
    }
}

/**
 * Send user message and trigger refresh
 */
async function sendMessage() {
    const input = document.getElementById('message-input');
    const message = input.value.trim();

    if (!message || isProcessing) return;

    // Clear input immediately (optimistic UI)
    input.value = '';

    // Send message and refresh
    await refresh(message);
}

/**
 * Update UI state based on processing status
 */
function updateUIState() {
    const input = document.getElementById('message-input');
    const button = document.getElementById('send-button');
    const container = document.getElementById('rendered-content');

    input.disabled = isProcessing;
    button.disabled = isProcessing;
    button.textContent = isProcessing ? 'Processing...' : 'Send';

    if (container) {
        if (isProcessing) {
            container.classList.add('loading');
        } else {
            container.classList.remove('loading');
        }
    }

    // Return focus to input field after processing completes
    if (!isProcessing) {
        input.focus();
    }
}

// Event listeners
document.getElementById('send-button').addEventListener('click', sendMessage);
document.getElementById('message-input').addEventListener('keypress', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
    }
});

const newThreadButton = document.getElementById('new-thread-button');
if (newThreadButton) {
    newThreadButton.addEventListener('click', () => {
        window.location.href = '/';
    });
}

// Initial load only - no auto-refresh
refresh();
