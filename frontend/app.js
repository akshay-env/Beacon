document.addEventListener('DOMContentLoaded', () => {
    const chatForm = document.getElementById('chat-form');
    const userInput = document.getElementById('user-input');
    const chatContainer = document.getElementById('chat-container');
    const sendButton = document.getElementById('send-button');
    const statusIndicator = document.querySelector('.status-indicator');

    // Setup marked.js options
    marked.setOptions({
        breaks: true,
        gfm: true
    });

    chatForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const query = userInput.value.trim();
        if (!query) return;

        // Add user message to UI
        appendMessage('user', query);
        userInput.value = '';
        userInput.disabled = true;
        sendButton.disabled = true;
        updateStatus('Thinking...', 'var(--accent)');

        // Create bot message container
        const botMessageEl = createMessageElement('bot', '');
        chatContainer.appendChild(botMessageEl);
        const contentEl = botMessageEl.querySelector('.message-content');
        
        // Add cursor
        contentEl.innerHTML = '<span class="cursor"></span>';
        scrollToBottom();

        try {
            const response = await fetch('/ask/stream', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ query: query })
            });

            if (!response.ok) {
                let errorMsg = 'An error occurred.';
                try {
                    const errorData = await response.json();
                    errorMsg = errorData.detail || errorMsg;
                } catch(e) {}
                contentEl.innerHTML = marked.parse(`**Error:** ${errorMsg}`);
                return;
            }

            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let fullText = '';
            let buffer = '';

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });
                
                // Process SSE format: "data: {...}\n\n"
                const parts = buffer.split('\n\n');
                buffer = parts.pop(); // Keep the last incomplete part in buffer

                for (const part of parts) {
                    if (part.startsWith('data: ')) {
                        const dataStr = part.slice(6);
                        try {
                            const data = JSON.parse(dataStr);
                            
                            if (data.token) {
                                fullText += data.token;
                                // Render markdown on the fly, append cursor
                                contentEl.innerHTML = marked.parse(fullText) + '<span class="cursor"></span>';
                                scrollToBottom();
                            }
                            
                            if (data.done) {
                                // Stream complete, remove cursor
                                contentEl.innerHTML = marked.parse(fullText);
                                
                                // Add sources pills
                                if (data.sources && data.sources.length > 0) {
                                    const sourcesDiv = document.createElement('div');
                                    sourcesDiv.className = 'sources-container';
                                    data.sources.forEach(src => {
                                        const pill = document.createElement('div');
                                        pill.className = 'source-pill';
                                        pill.textContent = src.split('\\').pop().split('/').pop(); // Just the filename
                                        pill.title = src;
                                        sourcesDiv.appendChild(pill);
                                    });
                                    botMessageEl.appendChild(sourcesDiv);
                                }
                                scrollToBottom();
                            }
                        } catch (err) {
                            console.error('Error parsing SSE data:', err);
                        }
                    }
                }
            }
        } catch (error) {
            console.error('Fetch error:', error);
            contentEl.innerHTML = marked.parse('**Connection Error:** Failed to reach the server.');
        } finally {
            userInput.disabled = false;
            sendButton.disabled = false;
            userInput.focus();
            updateStatus('Ready', 'var(--success)');
        }
    });

    function appendMessage(role, text) {
        const el = createMessageElement(role, text);
        chatContainer.appendChild(el);
        scrollToBottom();
    }

    function createMessageElement(role, text) {
        const div = document.createElement('div');
        div.className = `message ${role}`;
        
        const content = document.createElement('div');
        content.className = 'message-content';
        if (text) {
            content.textContent = text;
        }
        
        div.appendChild(content);
        return div;
    }

    function scrollToBottom() {
        chatContainer.scrollTop = chatContainer.scrollHeight;
    }

    function updateStatus(text, color) {
        statusIndicator.innerHTML = `<span class="dot" style="background-color: ${color}; box-shadow: 0 0 8px ${color}"></span> ${text}`;
    }
});
