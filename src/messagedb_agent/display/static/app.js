// Chat UI logic for the agent display service
// This script handles user input and HTML rendering

const THREAD_ID = window.THREAD_ID;
let currentHTML = null;
let isProcessing = false;

/**
 * Refresh the display by calling the /render endpoint
 * @param {string|null} userMessage - Optional user message to send
 */
async function refresh(userMessage = null) {
    try {
        // Show loading state when processing user message
        if (userMessage) {
            isProcessing = true;
            updateUIState();
        }

        const resp = await fetch('/render', {
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

        const data = await resp.json();
        currentHTML = data.html;

        // Update display
        document.getElementById('content').innerHTML = data.html;

        // Scroll to bottom
        const content = document.getElementById('content');
        content.scrollTop = content.scrollHeight;

    } catch (error) {
        console.error('Refresh failed:', error);
        document.getElementById('content').innerHTML =
            `<div style="color: red; padding: 20px;">Error: ${error.message}</div>`;
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
    const content = document.getElementById('content');

    input.disabled = isProcessing;
    button.disabled = isProcessing;
    button.textContent = isProcessing ? 'Processing...' : 'Send';

    if (isProcessing) {
        content.classList.add('loading');
    } else {
        content.classList.remove('loading');
        // Return focus to input field after processing completes
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

// Initial load only - no auto-refresh
refresh();
