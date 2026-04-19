const user = JSON.parse(localStorage.getItem('educhat_user') || 'null');

if (!user || !user.name || !user.email) {
    window.location.href = 'index.html';
}

function getApiBase() {
    if (typeof import.meta !== 'undefined' && import.meta.env && import.meta.env.VITE_API_URL) {
        return import.meta.env.VITE_API_URL;
    }
    return localStorage.getItem('educhat_api_url') || 'http://localhost:8000';
}

const API_BASE = getApiBase();
let currentSessionId = null;
let attachedFiles = [];
let newChatMode = true;

function showToast(message, type = 'success') {
    const existing = document.querySelector('.custom-toast');
    if (existing) existing.remove();
    
    const toast = document.createElement('div');
    toast.className = `custom-toast toast-${type}`;
    toast.innerHTML = `
        <span class="toast-icon">${type === 'success' ? '✓' : type === 'error' ? '✕' : 'ℹ'}</span>
        <span class="toast-message">${message}</span>
    `;
    document.body.appendChild(toast);
    setTimeout(() => toast.classList.add('show'), 10);
    setTimeout(() => {
        toast.classList.remove('show');
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

function showToolModal(title, content) {
    const existing = document.getElementById('tool-modal');
    if (existing) existing.remove();
    
    const modal = document.createElement('div');
    modal.className = 'modal-overlay';
    modal.id = 'tool-modal';
    modal.innerHTML = `
        <div class="modal-content tool-modal-content">
            <button class="modal-close" id="close-tool-modal">&times;</button>
            <h2>${title}</h2>
            <div class="tool-modal-body">${content}</div>
        </div>
    `;
    document.body.appendChild(modal);
    
    document.getElementById('close-tool-modal').addEventListener('click', () => modal.remove());
    modal.addEventListener('click', (e) => { if (e.target === modal) modal.remove(); });
}

function parseMarkdown(text) {
    // Preserve code blocks from being altered
    const codeBlocks = [];
    text = text.replace(/```([\s\S]*?)```/g, (match) => {
        codeBlocks.push(match);
        return `%%CODEBLOCK_${codeBlocks.length - 1}%%`;
    });

    // Inline code
    text = text.replace(/`([^`]+)`/g, '<code>$1</code>');

    // Bold and italic (bold first to avoid conflict)
    text = text.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
    text = text.replace(/\*([^*]+)\*/g, '<em>$1</em>');

    // Process line by line for headings, lists, and paragraphs
    const lines = text.split('\n');
    let html = '';
    let inUl = false;
    let inOl = false;

    for (let i = 0; i < lines.length; i++) {
        let line = lines[i];

        // Headings
        if (line.match(/^### /)) { 
            if (inUl) { html += '</ul>'; inUl = false; }
            if (inOl) { html += '</ol>'; inOl = false; }
            html += '<h3>' + line.replace(/^### /, '') + '</h3>'; 
            continue; 
        }
        if (line.match(/^## /)) { 
            if (inUl) { html += '</ul>'; inUl = false; }
            if (inOl) { html += '</ol>'; inOl = false; }
            html += '<h2>' + line.replace(/^## /, '') + '</h2>'; 
            continue; 
        }
        if (line.match(/^# /)) { 
            if (inUl) { html += '</ul>'; inUl = false; }
            if (inOl) { html += '</ol>'; inOl = false; }
            html += '<h1>' + line.replace(/^# /, '') + '</h1>'; 
            continue; 
        }

        // Unordered list items: -, *, •
        if (line.match(/^\s*[-*•]\s+/)) {
            if (inOl) { html += '</ol>'; inOl = false; }
            if (!inUl) { html += '<ul>'; inUl = true; }
            html += '<li>' + line.replace(/^\s*[-*•]\s+/, '') + '</li>';
            continue;
        }

        // Ordered list items: 1. or 1)
        if (line.match(/^\s*\d+[.)]\s+/)) {
            if (inUl) { html += '</ul>'; inUl = false; }
            if (!inOl) { html += '<ol>'; inOl = true; }
            html += '<li>' + line.replace(/^\s*\d+[.)]\s+/, '') + '</li>';
            continue;
        }

        // Horizontal rule separator
        if (line.trim() === '---') {
            html += '<hr>';
            continue;
        }

        // Close any open list if we hit a non-list line
        if (inUl) { html += '</ul>'; inUl = false; }
        if (inOl) { html += '</ol>'; inOl = false; }

        // Empty lines become breaks, non-empty become paragraphs
        if (line.trim() === '') {
            html += '';
        } else {
            html += '<p>' + line + '</p>';
        }
    }

    // Close any dangling lists
    if (inUl) html += '</ul>';
    if (inOl) html += '</ol>';

    // Restore code blocks
    codeBlocks.forEach((block, idx) => {
        const code = block.replace(/```/g, '');
        html = html.replace(`%%CODEBLOCK_${idx}%%`, '<pre><code>' + code + '</code></pre>');
    });

    return html;
}

// Helper to fetch full extracted text for a note using streaming endpoint
async function fetchNoteFullText(noteId) {
    try {
        const response = await fetch(API_BASE + '/api/notes/' + noteId + '/content');
        if (!response.ok) return '';
        const reader = response.body.getReader();
        const decoder = new TextDecoder('utf-8');
        let buffer = '';
        let fullText = '';
        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });
            let eol;
            while ((eol = buffer.indexOf('\n')) >= 0) {
                const line = buffer.substring(0, eol).trim();
                buffer = buffer.substring(eol + 1);
                if (line.startsWith('data: ')) {
                    const jsonStr = line.slice(6).trim();
                    if (!jsonStr || jsonStr === '{"done":true}' || jsonStr === '{"done": true}') continue;
                    try {
                        const data = JSON.parse(jsonStr);
                        if (data.text) fullText += (fullText ? '\n\n' : '') + data.text;
                    } catch (e) {}
                }
            }
        }
        return fullText;
    } catch (e) {
        console.error('Failed to fetch note content', noteId, e);
        return '';
    }
}

async function loadChatHistory() {
    try {
        const response = await fetch(API_BASE + '/api/chat/history?user=' + encodeURIComponent(user.name));
        const data = await response.json();
        const container = document.querySelector('.chat-history-list');
        if (!container) return;
        
        container.innerHTML = '<li class="chat-history-item new-chat-btn"><span class="menu-icon" style="color: #c8b384;">➕</span> <span class="chat-title-text">New Chat</span></li>';
        
        if (data.sessions && data.sessions.length > 0) {
            container.innerHTML += data.sessions.map(session => `
                <li class="chat-history-item" data-session-id="${session.id}">
                    <span class="menu-icon" style="color: #9ca3af; font-size: 1rem;">💬</span>
                    <span class="chat-title-text">${session.title}</span>
                    <span class="delete-chat" data-delete-id="${session.id}">✕</span>
                </li>
            `).join('');
            currentSessionId = data.sessions[0].id;
            loadSession(currentSessionId);
        } else {
            newChatMode = true;
            showWelcomeMessage();
        }
        
        container.querySelectorAll('.chat-history-item').forEach(item => {
            item.addEventListener('click', (e) => {
                if (e.target.classList.contains('delete-chat')) return;
                if (item.classList.contains('new-chat-btn')) {
                    newChat();
                } else {
                    loadSession(parseInt(item.dataset.sessionId));
                }
            });
        });
        
        container.querySelectorAll('.delete-chat').forEach(btn => {
            btn.addEventListener('click', async (e) => {
                e.stopPropagation();
                const sessionId = parseInt(btn.dataset.deleteId);
                try {
                    await fetch(API_BASE + '/api/chat/session/' + sessionId, { method: 'DELETE' });
                    loadChatHistory();
                } catch (err) {
                    console.error('Failed to delete session:', err);
                }
            });
        });
    } catch (e) {
        console.error('Error loading chat history:', e);
    }
}

async function loadSession(sessionId) {
    try {
        const response = await fetch(API_BASE + '/api/chat/session/' + sessionId);
        const data = await response.json();
        
        if (data.messages) {
            currentSessionId = sessionId;
            newChatMode = false;
            const container = document.getElementById('messages-container');
            const header = container.querySelector('.bot-header');
            container.innerHTML = '';
            container.appendChild(header);
            
            data.messages.forEach(msg => {
                addMessage(msg.content, msg.role === 'user');
            });
        }
    } catch (e) {
        console.error('Failed to load session:', e);
    }
}

async function newChat() {
    try {
        const response = await fetch(API_BASE + '/api/chat/session', {
            method: 'POST',
            headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
            body: `user=${encodeURIComponent(user.name)}&title=New Chat`
        });
        
        const data = await response.json();
        if (data.session_id) {
            currentSessionId = data.session_id;
            newChatMode = false;
            const container = document.getElementById('messages-container');
            const header = container.querySelector('.bot-header');
            container.innerHTML = '';
            container.appendChild(header);
            addMessage(`Hi ${user.name.split(' ')[0]}! I'm your AI tutor. Ask me anything!`, false);
        }
    } catch (e) {
        console.error('Error creating session:', e);
    }
}

function showWelcomeMessage() {
    const container = document.getElementById('messages-container');
    const header = container.querySelector('.bot-header');
    container.innerHTML = '';
    if (header) container.appendChild(header);
    
    container.innerHTML += `
        <div class="welcome-message">
            <div class="welcome-icon">📚</div>
            <h2>Welcome to EduChat, ${user.name.split(' ')[0]}!</h2>
            <p>Your personal AI-powered learning assistant</p>
            <div class="feature-list">
                <div class="feature">📝 <strong>Chat</strong> - Ask any question</div>
                <div class="feature">📄 <strong>Upload</strong> - Upload PDFs, images, docs</div>
                <div class="feature">🗃️ <strong>Study Tools</strong> - Notes & flashcards</div>
            </div>
            <p class="welcome-hint">Send a message to get started!</p>
        </div>
    `;
}

function addMessage(content, isUser = false, attachments = []) {
    const container = document.getElementById('messages-container');
    if (newChatMode) {
        newChatMode = false;
    }
    
    const row = document.createElement('div');
    row.className = `message-row ${isUser ? 'user' : 'ai'}`;
    
    let avatar = isUser ? '' : '<div class="msg-avatar">📖</div>';
    let attachmentsHtml = '';
    if (attachments.length > 0) {
        attachmentsHtml = '<div class="msg-attachments">';
        attachments.forEach(att => {
            if (att.type && att.type.startsWith('image/')) {
                attachmentsHtml += `<img src="${att.preview}" alt="${att.name}" class="att-image">`;
            } else {
                attachmentsHtml += `<div class="att-file"><span class="att-icon">${att.icon}</span><span class="att-name">${att.name}</span></div>`;
            }
        });
        attachmentsHtml += '</div>';
    }
    
    const displayContent = isUser ? content : parseMarkdown(content);
    
    row.innerHTML = `
        ${avatar}
        <div class="msg-bubble ${isUser ? 'user-bubble' : 'ai-bubble'}">${displayContent}${attachmentsHtml}</div>
    `;
    container.appendChild(row);
    container.scrollTop = container.scrollHeight;
}

function getFileIcon(filename) {
    const ext = filename.split('.').pop().toLowerCase();
    const icons = {
        pdf: '📕', txt: '📄', doc: '📄', docx: '📄', ppt: '📊', pptx: '📊',
        png: '🖼️', jpg: '🖼️', jpeg: '🖼️', gif: '🖼️',
        mp3: '🎵', wav: '🎵', m4a: '🎵',
        mp4: '🎬', webm: '🎬', mov: '🎬'
    };
    return icons[ext] || '📁';
}

function formatFileSize(bytes) {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
}

function renderAttachment(file, index) {
    const preview = document.getElementById('attachments-preview');
    const div = document.createElement('div');
    div.className = 'attachment-item';
    div.dataset.fileIndex = index;
    div.innerHTML = `
        <span class="att-icon">${file.icon}</span>
        <span class="att-name">${file.name}</span>
        <span class="att-size">${formatFileSize(file.size)}</span>
        <button class="attachment-remove" title="Remove file">&times;</button>
    `;
    
    div.querySelector('.attachment-remove').addEventListener('click', (e) => {
        e.stopPropagation();
        attachedFiles = attachedFiles.filter((_, i) => i !== index);
        renderAllAttachments();
    });
    
    preview.appendChild(div);
}

function renderAllAttachments() {
    const preview = document.getElementById('attachments-preview');
    preview.innerHTML = '';
    attachedFiles.forEach((file, index) => renderAttachment(file, index));
    
    const clearBtn = document.getElementById('clear-attachments');
    if (clearBtn) {
        clearBtn.style.display = attachedFiles.length > 0 ? 'block' : 'none';
    }
}

function removeAttachmentByName(filename) {
    attachedFiles = attachedFiles.filter(f => f.name !== filename);
    renderAllAttachments();
}

document.querySelector('#app').innerHTML = `
    <div class="app-layout">
        <header class="top-navbar">
            <div class="logo-section">
                <button id="sidebar-toggle" class="nav-toggle-btn" title="Toggle Menu">☰</button>
                <span class="logo-icon-gold">📚</span>
                <h1 class="logo-text">EduChat <span class="ai-text">AI</span></h1>
            </div>
            <div class="search-section">
                <div class="search-box">
                    <span class="search-icon">🔍</span>
                    <input type="text" id="search-input" placeholder="Search topics, notes..." />
                </div>
                <div id="search-results" class="search-results"></div>
            </div>
            <div class="user-section">
                <button id="search-toggle-mobile" class="nav-toggle-btn mobile-only" title="Toggle Search">🔍</button>
                <div class="user-profile-display" id="user-profile-display" style="cursor: pointer;">
                    <span class="avatar-img">${user.name.charAt(0).toUpperCase()}</span>
                    <span class="user-name">${user.name}</span>
                </div>
            </div>
        </header>
        <div class="sidebar-overlay" id="sidebar-overlay"></div>
        
        <div class="main-content">
            <aside class="left-sidebar">
                <button class="sidebar-close-btn" id="left-sidebar-close" title="Close menu">&times;</button>
                <!-- Chat History Section -->
                <div style="padding: 16px 20px; border-bottom: 1px solid #e5e7eb;">
                    <h3 style="font-size: 0.75rem; text-transform: uppercase; color: #6b7280; letter-spacing: 1px;">Chat History</h3>
                </div>
                <ul class="chat-history-list" style="list-style: none; padding: 0; margin: 0; flex: 1; overflow-y: auto;"></ul>
                
                <!-- Study Tools Section -->
                <div style="padding: 16px 20px; border-top: 1px solid #e5e7eb; border-bottom: 1px solid #e5e7eb;">
                    <h3 style="font-size: 0.75rem; text-transform: uppercase; color: #6b7280; letter-spacing: 1px; margin-bottom: 12px;">Study Tools</h3>
                    <div style="display: flex; flex-direction: column; gap: 4px;">
                        <li class="menu-item" data-action="lecture-notes" style="padding: 8px 12px; display: flex; align-items: center; gap: 10px; cursor: pointer; color: #20242d; border-radius: 6px;"><span class="menu-icon">📄</span> <span style="font-size: 0.9rem;">Lecture Notes</span></li>
                        <li class="menu-item" data-action="flashcards" style="padding: 8px 12px; display: flex; align-items: center; gap: 10px; cursor: pointer; color: #20242d; border-radius: 6px;"><span class="menu-icon">🗃️</span> <span style="font-size: 0.9rem;">Flashcards</span></li>
                        <li class="menu-item" data-action="study-plans" style="padding: 8px 12px; display: flex; align-items: center; gap: 10px; cursor: pointer; color: #20242d; border-radius: 6px;"><span class="menu-icon">📅</span> <span style="font-size: 0.9rem;">Study Plans</span></li>
                    </div>
                </div>
                
                <!-- Settings Section -->
                <div style="padding: 16px 20px;">
                    <li class="menu-item" data-action="settings" style="padding: 8px 12px; display: flex; align-items: center; gap: 10px; cursor: pointer; color: #20242d; border-radius: 6px;"><span class="menu-icon">⚙️</span> <span style="font-size: 0.9rem;">Settings</span></li>
                </div>
            </aside>
            
            <main class="right-sidebar" style="flex: 1; overflow: hidden; display: flex; background-color: #f4f5f7; padding: 0;">
                
                <!-- Chat Section -->
                <div class="chat-view" id="chat-view" style="flex: 1; display: flex; flex-direction: column; min-width: 0; background: white; margin: 16px; border-radius: 12px; box-shadow: 0 2px 10px rgba(0,0,0,0.05);">
                    <div class="chat-title-header" style="padding: 16px 20px; border-bottom: 1px solid #e5e7eb; display: flex; justify-content: space-between; align-items: center;">
                        <h2 id="chat-title" style="font-size: 1.15rem; font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">Chat: Data Structures - Trees & Graphs</h2>
                        <button id="tools-toggle" class="nav-toggle-btn" title="Quick Tools">🛠️</button>
                    </div>
                    
                    <div class="messages-container" id="messages-container" style="padding: 24px 32px; gap: 20px;">
                        <div class="bot-header" style="display:none;"></div>
                    </div>
                    
                    <div class="chat-input-area" style="padding: 20px 32px;">
                        <div class="input-box-wrapper" style="border: 1.5px solid #c8b384; border-radius: 8px; padding: 12px; display: flex; flex-direction: column; gap: 8px;">
                            <textarea id="chat-input" placeholder="Ask EduChat about Trees..." rows="1" style="border: none; outline: none; width: 100%; resize: none; font-family: inherit; font-size: 0.95rem;"></textarea>
                            <div class="attachments-preview" id="attachments-preview"></div>
                            
                            <div class="input-toolbar" style="display: flex; justify-content: space-between; align-items: center; margin-top: 8px;">
                                <div class="toolbar-left" style="display: flex; gap: 8px;">
                                    <label for="file-input" class="icon-btn label-btn" title="Upload from device" style="background: none;">📄</label>
                                    <input type="file" id="file-input" accept=".txt,.pdf,.doc,.docx,.ppt,.pptx,.png,.jpg,.jpeg,.gif,.mp3,.wav,.mp4,.webm" multiple hidden>
                                    <button class="icon-btn" id="attach-from-notes" title="Attach from saved notes" style="background: none;">📎</button>
                                </div>
                                <div class="toolbar-right" style="display: flex; gap: 8px; align-items: center;">
                                    <button class="icon-btn" id="clear-attachments" title="Clear attachments" style="display: none; background: #fee2e2; color: #dc2626;">✕</button>
                                    <button class="icon-btn" id="voice-btn" title="Voice input" style="background: none; border-radius: 50%; border: 1px solid #e5e7eb;">🎤</button>
                                    <button class="send-btn" id="send-btn" style="background-color: #14284b; color: white; border-radius: 20px; padding: 6px 16px; margin-left: 8px; font-weight: 500;">Send →</button>
                                </div>
                            </div>
                        </div>
                        <div class="file-size-warning" id="file-size-warning"></div>
                    </div>
                </div>
                
                <!-- Right Sidebar - Quick Tools -->
                <div class="quick-tools-sidebar" style="width: 280px; background: white; padding: 24px; display: flex; flex-direction: column; gap: 16px; margin: 16px 16px 16px 0; border-radius: 12px; box-shadow: 0 2px 10px rgba(0,0,0,0.05);">
                    <button class="sidebar-close-btn" id="right-sidebar-close" title="Close tools">&times;</button>
                    <h3 style="font-size: 0.85rem; text-transform: uppercase; font-weight: 600; color: #374151; letter-spacing: 1px; margin-bottom: 8px;">Quick Tools</h3>
                    
                    <button class="tool-btn" id="quick-flashcard" style="padding: 10px; background: white; border: 1px solid #e5e7eb; border-radius: 20px; cursor: pointer; text-align: center; font-weight: 500; font-size: 0.9rem; color: #374151;">
                        Create Flashcard
                    </button>
                    
                    <button class="tool-btn" id="quick-summarize" style="padding: 10px; background: white; border: 1px solid #e5e7eb; border-radius: 20px; cursor: pointer; text-align: center; font-weight: 500; font-size: 0.9rem; color: #374151;">
                        Summarize Notes
                    </button>
                    
                    <button class="tool-btn" id="quick-quiz" style="padding: 10px; background: white; border: 1px solid #e5e7eb; border-radius: 20px; cursor: pointer; text-align: center; font-weight: 500; font-size: 0.9rem; color: #374151;">
                        Generate Quiz
                    </button>
                </div>
                
            </main>
                
            </main>
        </div>
    </div>
`;

const fileInput = document.getElementById('file-input');
const attachmentsPreview = document.getElementById('attachments-preview');
const clearAttachmentsBtn = document.getElementById('clear-attachments');
const fileSizeWarning = document.getElementById('file-size-warning');
const chatInput = document.getElementById('chat-input');

// Responsive Sidebar Toggles
const sidebarToggle = document.getElementById('sidebar-toggle');
const toolsToggle = document.getElementById('tools-toggle');
const searchToggleMobile = document.getElementById('search-toggle-mobile');
const sidebarOverlay = document.getElementById('sidebar-overlay');
const leftSidebar = document.querySelector('.left-sidebar');
const rightSidebar = document.querySelector('.quick-tools-sidebar');
const rightSidebarContainer = document.querySelector('.right-sidebar');
const searchSection = document.querySelector('.search-section');

function toggleLeftSidebar() {
    leftSidebar.classList.toggle('active');
    sidebarOverlay.classList.toggle('active');
    rightSidebar.classList.remove('active');
    rightSidebarContainer.classList.remove('tools-active'); // Ensure tools closed
}

function toggleRightSidebar() {
    rightSidebar.classList.toggle('active');
    sidebarOverlay.classList.toggle('active');
    leftSidebar.classList.remove('active');
    rightSidebarContainer.classList.toggle('tools-active');
}

function closeAllSidebars() {
    leftSidebar.classList.remove('active');
    rightSidebar.classList.remove('active');
    sidebarOverlay.classList.remove('active');
    rightSidebarContainer.classList.remove('tools-active');
}

sidebarToggle?.addEventListener('click', toggleLeftSidebar);
toolsToggle?.addEventListener('click', toggleRightSidebar);
sidebarOverlay?.addEventListener('click', closeAllSidebars);

document.getElementById('left-sidebar-close')?.addEventListener('click', closeAllSidebars);
document.getElementById('right-sidebar-close')?.addEventListener('click', closeAllSidebars);

searchToggleMobile?.addEventListener('click', () => {
    searchSection.classList.toggle('mobile-visible');
});

// Close sidebars on menu item click (mobile)
document.querySelectorAll('.menu-item, .chat-history-item').forEach(item => {
    item.addEventListener('click', () => {
        if (window.innerWidth <= 768) closeAllSidebars();
    });
});

// More robust responsive handling
function handleResize() {
    const width = window.innerWidth;
    
    // Close sidebars on resize to large screens
    if (width > 1024) {
        closeAllSidebars();
        searchSection.classList.remove('mobile-visible');
    }
    
    // Update chat title based on screen
    const chatTitle = document.getElementById('chat-title');
    if (chatTitle) {
        if (width <= 400) {
            chatTitle.style.maxWidth = '180px';
        } else if (width <= 600) {
            chatTitle.style.maxWidth = '220px';
        } else {
            chatTitle.style.maxWidth = '';
        }
    }
}

// Handle window resize
window.addEventListener('resize', handleResize);
handleResize();

// Handle orientation change for mobile
window.addEventListener('orientationchange', () => {
    setTimeout(handleResize, 100);
});

// Prevent accidental back swipe on mobile
document.addEventListener('touchmove', (e) => {
    if (e.target.closest('.left-sidebar.active')) {
        // Allow scroll in sidebar
    }
}, { passive: true });
const sendBtn = document.getElementById('send-btn');
const messagesContainer = document.getElementById('messages-container');
const newChatBtn = document.getElementById('new-chat-btn');
const summarizeBtn = document.getElementById('summarize-notes-btn');

const MAX_SIZE = 4.5 * 1024 * 1024;

function handleFileSelect(e) {
    const files = Array.from(e.target.files);
    attachedFiles = [];
    attachmentsPreview.innerHTML = '';
    fileSizeWarning.innerHTML = '';
    
    files.forEach(file => {
        if (file.size > MAX_SIZE) {
            fileSizeWarning.innerHTML = '<span class="warning">⚠️ File exceeds 4.5MB limit</span>';
        }
        
        const icon = getFileIcon(file.name);
        const fileObj = { name: file.name, size: file.size, type: file.type, icon: icon, file: file };
        
        if (file.type.startsWith('image/')) {
            const reader = new FileReader();
            reader.onload = (e) => {
                fileObj.preview = e.target.result;
                attachedFiles.push(fileObj);
                renderAllAttachments();
            };
            reader.readAsDataURL(file);
        } else {
            attachedFiles.push(fileObj);
            renderAllAttachments();
        }
    });
}

fileInput.addEventListener('change', handleFileSelect);

clearAttachmentsBtn.addEventListener('click', () => {
    attachedFiles = [];
    fileInput.value = '';
    fileSizeWarning.innerHTML = '';
    renderAllAttachments();
});

newChatBtn?.addEventListener('click', newChat);

summarizeBtn?.addEventListener('click', async () => {
    const container = document.getElementById('messages-container');
    const messages = container.querySelectorAll('.msg-bubble');
    if (messages.length === 0) {
        showToolModal('Summarize', '<p class="tool-intro">No chat history to summarize.</p>');
        return;
    }
    
    let allText = '';
    messages.forEach(msg => {
        allText += msg.textContent + '\n';
    });
    
    showToolModal('Summarize', '<div class="tool-loading">Generating summary...</div>');
    
    try {
        const response = await fetch(API_BASE + '/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
            body: `message=Summarize: ${allText.substring(0, 2000)}&user=${encodeURIComponent(user.name)}&save_history=false`
        });
        const data = await response.json();
        if (data.reply) {
            showToolModal('Summary', `<div class="summary-result">${parseMarkdown(data.reply)}</div>`);
        }
    } catch (err) {
        showToolModal('Error', `<p>${err.message}</p>`);
    }
});

document.getElementById('quick-summarize')?.addEventListener('click', async () => {
    showToolModal('Summarize Notes', `
        <div class="summarize-form">
            <div class="form-group">
                <label>What to summarize?</label>
                <select id="summarize-source">
                    <option value="chat">Current Chat History</option>
                    <option value="notes">My Lecture Notes</option>
                </select>
            </div>
            <div class="form-group">
                <label>Summary Style</label>
                <select id="summarize-style">
                    <option value="bullet">Bullet Points</option>
                    <option value="concept">Key Concepts Only</option>
                    <option value="brief">Brief Summary</option>
                    <option value="detailed">Detailed Summary</option>
                </select>
            </div>
            <button class="btn-primary full-width" id="generate-summary-btn">Generate Summary</button>
        </div>
    `);
    
    document.getElementById('generate-summary-btn').onclick = async () => {
        const source = document.getElementById('summarize-source').value;
        const style = document.getElementById('summarize-style').value;
        let textToSummarize = '';
        
        document.querySelector('.tool-modal-body').innerHTML = '<div class="tool-loading">Generating summary...</div>';
        
        if (source === 'chat') {
            const container = document.getElementById('messages-container');
            const messages = container.querySelectorAll('.msg-bubble');
            if (messages.length === 0) {
                showToolModal('Summary', '<p class="tool-intro">No chat history to summarize.</p>');
                return;
            }
            messages.forEach(msg => { textToSummarize += msg.textContent + '\n'; });
        } else {
            try {
                const response = await fetch(API_BASE + '/api/notes?user=' + encodeURIComponent(user.name));
                const data = await response.json();
                const notes = data.notes || [];
                if (notes.length === 0) {
                    showToolModal('Summary', '<p class="tool-intro">No lecture notes to summarize.</p>');
                    return;
                }
                for (const note of notes) {
                const extracted = await fetchNoteFullText(note.id);
                textToSummarize += extracted + '\n---\n';
            }
            } catch (e) {
                showToolModal('Error', '<p>Could not load notes.</p>');
                return;
            }
        }
        
        let stylePrompt = '';
        if (style === 'bullet') stylePrompt = 'STRICT REQUIREMENT: Format as clean bullet points with subheadings. DO NOT output any paragraphs, preambles, or conversational text. Output ONLY bullet points.';
        else if (style === 'concept') stylePrompt = 'STRICT REQUIREMENT: List only key concepts as numbered points. DO NOT output any paragraphs, preambles, or conversational text.';
        else if (style === 'brief') stylePrompt = 'Give a brief 2-paragraph summary.';
        else stylePrompt = 'Give a detailed summary with explanations.';
        
        try {
            const summaryMessage = `Summarize the following text:\n\n${textToSummarize.substring(0, 3000)}\n\n${stylePrompt}`;
            const params = new URLSearchParams();
            params.append('message', summaryMessage);
            params.append('user', user.name);
            params.append('save_history', 'false');
            const response = await fetch(API_BASE + '/api/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                body: params.toString()
            });
            const data = await response.json();
            if (data.reply) {
                const summaryText = data.reply.replace(/SUMMARY:/g, '').trim();
                showToolModal('Summary', `<div class="summary-result improved">${parseMarkdown(summaryText)}</div>`);
            }
        } catch (err) {
            showToolModal('Error', `<p>${err.message}</p>`);
        }
    };
});

document.getElementById('quick-quiz')?.addEventListener('click', () => showQuizGenerator());
document.getElementById('quick-flashcard')?.addEventListener('click', () => showFlashcardGenerator());

const attachFromNotesBtn = document.getElementById('attach-from-notes');
attachFromNotesBtn?.addEventListener('click', async () => {
    let notes = [];
    
    try {
        const response = await fetch(API_BASE + '/api/notes?user=' + encodeURIComponent(user.name));
        const data = await response.json();
        notes = data.notes || [];
    } catch (e) {
        console.log('API unavailable, trying localStorage');
    }
    
    if (notes.length === 0) {
        const localNotes = JSON.parse(localStorage.getItem('lecture_notes') || '[]');
        if (localNotes.length > 0) {
            notes = localNotes.map(n => ({ id: n.id, name: n.name, content: n.content, file_type: n.fileType, created_at: n.createdAt }));
        }
    }
    
    if (notes.length === 0) {
        showToolModal('Attach from Notes', '<p class="tool-intro">No saved lecture notes to attach.</p>');
        return;
    }
    
    showToolModal('Attach from Notes', `
        <div class="attach-from-notes-list">
            ${notes.map(note => `
                <div class="attach-note-item">
                    <label class="note-checkbox-label">
                        <input type="checkbox" class="attach-note-checkbox" data-name="${note.name}" data-content="${encodeURIComponent(note.content || '')}" data-type="${note.file_type || ''}">
                        <span class="note-icon">📄</span>
                        <span class="note-name">${note.name}</span>
                    </label>
                </div>
            `).join('')}
        </div>
        <button class="btn-primary" id="confirm-attach-notes" style="margin-top: 12px;">Attach Selected</button>
    `);
    
    document.getElementById('confirm-attach-notes').onclick = function() {
        const checkboxes = document.querySelectorAll('.attach-note-checkbox:checked');
        if (checkboxes.length === 0) {
            showToast('Please select at least one note', 'error');
            return;
        }
        checkboxes.forEach(cb => {
            const name = cb.dataset.name;
            const content = decodeURIComponent(cb.dataset.content);
            const fileType = cb.dataset.type;
            let fileData;
            // Try to decode base64 content (new storage format)
            try {
                const binaryString = atob(content);
                const len = binaryString.length;
                const bytes = new Uint8Array(len);
                for (let i = 0; i < len; i++) {
                    bytes[i] = binaryString.charCodeAt(i);
                }
                fileData = bytes;
            } catch (e) {
                // Fallback: treat as plain text (old notes with extracted text)
                fileData = content;
            }
            const fileObj = {
                name,
                size: fileData.length,
                type: fileType,
                file: new File([fileData], name, { type: fileType }),
                icon: '📄'
            };
            attachedFiles.push(fileObj);
        });
        renderAllAttachments();
        document.getElementById('tool-modal')?.remove();
        showToast(`Attached ${checkboxes.length} file(s) from notes!`, 'success');
    };
});

const voiceBtn = document.getElementById('voice-btn');
if (voiceBtn && ('SpeechRecognition' in window || 'webkitSpeechRecognition' in window)) {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    const recognition = new SpeechRecognition();
    recognition.continuous = false;
    recognition.interimResults = false;
    recognition.lang = 'en-US';
    
    recognition.onstart = () => {
        voiceBtn.style.background = '#fee2e2';
        voiceBtn.textContent = '🔴';
    };
    
    recognition.onend = () => {
        voiceBtn.style.background = '';
        voiceBtn.textContent = '🎤';
    };
    
    recognition.onresult = (event) => {
        const transcript = event.results[0][0].transcript;
        chatInput.value = transcript;
    };
    
    voiceBtn.addEventListener('click', () => recognition.start());
}

async function sendMessage() {
    const message = chatInput.value.trim();
    if (message === '' && attachedFiles.length === 0) return;
    
    const isNewChat = newChatMode;
    
    const userAttachments = attachedFiles.map(f => ({
        name: f.name,
        size: f.size,
        type: f.type,
        icon: f.icon,
        preview: f.preview || null
    }));
    
    const msgHtml = message || (attachedFiles.length > 0 ? `<em>Uploaded ${attachedFiles.length} file(s)</em>` : '');
    addMessage(msgHtml, true, userAttachments);
    
    chatInput.value = '';
    const oldFiles = [...attachedFiles];
    attachedFiles = [];
    attachmentsPreview.innerHTML = '';
    fileInput.value = '';
    fileSizeWarning.innerHTML = '';
    
    chatInput.style.height = 'auto';
    
    const typingDiv = document.createElement('div');
    typingDiv.className = 'message-row ai';
    typingDiv.id = 'typing-indicator';
    typingDiv.innerHTML = `
        <div class="msg-avatar">📖</div>
        <div class="msg-bubble ai-bubble typing">
            <span class="typing-dots"><span></span><span></span><span></span></span>
        </div>
    `;
    messagesContainer.appendChild(typingDiv);
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
    
    try {
        const formData = new FormData();
        formData.append('message', message);
        formData.append('user', user.name);
        if (currentSessionId) formData.append('session_id', currentSessionId);
        
        for (const f of oldFiles) {
            formData.append('files', f.file);
        }
        
        const response = await fetch(API_BASE + '/api/chat', {
            method: 'POST',
            body: formData
        });
        
        const data = await response.json();
        const typing = document.getElementById('typing-indicator');
        if (typing) typing.remove();
        
        if (data.reply) {
            addMessage(data.reply, false);
            if (currentSessionId && message && isNewChat) {
                const title = message.split(' ').slice(0, 4).join(' ');
                const shortTitle = title.length > 25 ? title.substring(0, 25) + '...' : title;
                fetch(API_BASE + '/api/chat/session/' + currentSessionId, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                    body: `title=${encodeURIComponent(shortTitle)}`
                }).then(() => loadChatHistory());
            }
        } else if (data.error) {
            addMessage(`Error: ${data.error}`, false);
        }
    } catch (e) {
        const typing = document.getElementById('typing-indicator');
        if (typing) typing.remove();
        addMessage(`Sorry, I encountered an error: ${e.message}`, false);
    }
}

sendBtn.addEventListener('click', sendMessage);

chatInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
    }
});

chatInput.addEventListener('input', function() {
    this.style.height = 'auto';
    this.style.height = (this.scrollHeight) + 'px';
});

document.querySelectorAll('.menu-item').forEach(item => {
    item.addEventListener('click', () => {
        const action = item.dataset.action;
        
        document.querySelectorAll('.menu-item').forEach(i => i.classList.remove('active'));
        item.classList.add('active');
        
        if (action === 'lecture-notes') {
            loadLectureNotes();
        } else if (action === 'flashcards') {
            loadFlashcards();
        } else if (action === 'study-plans') {
            loadStudyPlans();
        } else if (action === 'settings') {
            showSettingsModal();
        }
    });
});

function loadLectureNotes() {
    showToolModal('Lecture Notes', `
        <div class="notes-content" style="min-height: 200px;">
            <div class="upload-area" id="notes-upload-area" style="text-align: center; border: 2px dashed #cbd5e1; padding: 20px; border-radius: 8px; margin-bottom: 20px; cursor: pointer; transition: all 0.2s;">
                <input type="file" id="notes-file-input" accept=".txt,.pdf,.md,.doc,.docx,.ppt,.pptx" hidden>
                <label for="notes-file-input" class="upload-label" style="cursor: pointer; display: block; color: #64748b;">
                    <div style="font-size: 24px; margin-bottom: 8px;">📄</div>
                    <span>Click to upload a document (PDF, Word, PowerPoint, Text)</span>
                </label>
            </div>
            
            <div id="notes-list" class="notes-list">
                <div class="tool-loading">Loading notes...</div>
            </div>
        </div>
    `);
    
    setTimeout(() => {
        const fileInput = document.getElementById('notes-file-input');
        if (fileInput) {
            fileInput.addEventListener('change', async (e) => {
                const file = e.target.files[0];
                if (!file) return;
                
                const fileType = file.name.split('.').pop().toLowerCase();
                const allowedTypes = ['txt', 'pdf', 'md', 'doc', 'docx', 'ppt', 'pptx'];
                if (!allowedTypes.includes(fileType)) {
                    showToast('Unsupported file type', 'error');
                    return;
                }
                
                showToast('Uploading note...', 'info');
                document.getElementById('notes-list').innerHTML = '<div class="tool-loading">Processing document...</div>';
                
                try {
                    const reader = new FileReader();
                    reader.onload = async (event) => {
                        let b64Content = "";
                        if (fileType === 'txt' || fileType === 'md') {
                            b64Content = btoa(unescape(encodeURIComponent(event.target.result)));
                        } else {
                            b64Content = event.target.result.split(',')[1];
                        }
                        
                        if (b64Content) {
                            const saveForm = new FormData();
                            saveForm.append('user', user.name);
                            saveForm.append('name', file.name);
                            saveForm.append('content', b64Content);
                            saveForm.append('file_type', fileType);
                            
await fetch(API_BASE + '/api/notes', { method: 'POST', body: saveForm });
                             showToast('Upload complete! File will be extracted when you view it.', 'success');
                         } else {
                             showToast('Upload failed', 'error');
                         }
                         
                         loadLectureNotes();
                     };
                     
                     if (fileType === 'txt' || fileType === 'md') {
                         reader.readAsText(file);
                     } else {
                         reader.readAsDataURL(file);
                     }
                 } catch (e) {
                     showToast('Upload failed: ' + e.message, 'error');
                     loadLectureNotes();
                 }
             });
         }
         
         const container = document.getElementById('notes-list');
         if (!container) return;
         
         fetch(API_BASE + '/api/notes?user=' + encodeURIComponent(user.name))
            .then(res => res.json())
            .then(data => {
                const notes = data.notes || [];
                if (notes.length === 0) {
                    container.innerHTML = '<p class="empty-message">No notes uploaded yet.</p>';
                    return;
                }
                container.innerHTML = notes.map(note => `
                    <div class="note-item" style="display: flex; justify-content: space-between; align-items: center; padding: 12px; border: 1px solid #e5e7eb; border-radius: 8px; margin-bottom: 8px;">
                        <span class="note-name" style="overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 60%;">📄 ${note.name}</span>
                        <div class="note-actions" style="display: flex; gap: 8px;">
                            <button class="icon-btn view-note-btn" data-id="${note.id}" title="View Note">👁️</button>
                            <button class="icon-btn delete-note-btn" data-id="${note.id}" title="Delete" style="color: #dc2626;">✕</button>
                        </div>
                    </div>
                `).join('');
                
container.querySelectorAll('.view-note-btn').forEach(btn => {
                    btn.addEventListener('click', async () => {
                        const noteId = btn.dataset.id;
                        const note = notes.find(n => n.id == noteId);
                        if (!note) return;
                        
                        const name = note.name;
                        const fileType = note.file_type;
                        
                        showToolModal('View Note: ' + name, `
                            <div class="note-viewer" style="max-height: 60vh; overflow-y: auto; background: #fafafa; padding: 20px; border-radius: 8px; border: 1px solid #e5e7eb;">
                                <div id="note-content-area" style="color: #374151; font-family: inherit; font-size: 0.95rem; line-height: 1.8; word-wrap: break-word; white-space: pre-wrap;">Loading...</div>
                            </div>
                            <div style="display: flex; gap: 8px; margin-top: 16px;">
                                <button id="back-to-notes-btn" class="btn-primary" style="flex: 1;">Back to Notes</button>
                                <button id="copy-note-btn" class="btn-secondary" style="flex: 1;">Copy Text</button>
                            </div>
                        `);
                        
                        const contentArea = document.getElementById('note-content-area');
                        let extractedChunks = [];
                        let pageMarkers = [];
                        
                        try {
                            const response = await fetch(API_BASE + '/api/notes/' + noteId + '/content');
                            if (!response.ok) {
                                contentArea.innerHTML = note.content ? parseMarkdown(note.content) : 'Error loading note';
                                return;
                            }
                            
                            const reader = response.body.getReader();
                            const decoder = new TextDecoder("utf-8");
                            let buffer = '';
                            
                            function processLine(line) {
                                if (!line.startsWith('data: ')) return;
                                const jsonStr = line.slice(6).trim();
                                if (!jsonStr || jsonStr === '{"done":true}' || jsonStr === '{"done": true}') {
                                    if (jsonStr === '{"done":true}' || jsonStr === '{"done": true}') {
                                        updateDisplay(contentArea, extractedChunks, pageMarkers, fileType, true);
                                    }
                                    return;
                                }
                                
                                try {
                                    const data = JSON.parse(jsonStr);
                                    if (data.text && !data.done) {
                                        extractedChunks.push(data.text);
                                        if (fileType === 'ppt' || fileType === 'pptx') {
                                            pageMarkers.push(`=== Slide ${data.page_num} ===`);
                                        } else if (data.total_pages > 1) {
                                            pageMarkers.push(`--- Page ${data.page_num} ---`);
                                        }
                                        updateDisplay(contentArea, extractedChunks, pageMarkers, fileType, false);
                                    }
                                } catch (e) {}
                            }
                            
                            while (true) {
                                const { done, value } = await reader.read();
                                if (done) {
                                    if (buffer.trim()) {
                                        processLine(buffer.trim());
                                    }
                                    break;
                                }
                                
                                buffer += decoder.decode(value, { stream: true });
                                let eol;
                                while ((eol = buffer.indexOf('\n')) >= 0) {
                                    const line = buffer.substring(0, eol).trim();
                                    buffer = buffer.substring(eol + 1);
                                    if (line) processLine(line);
                                }
                            }
                        } catch (err) {
                            contentArea.textContent = 'Error: ' + err.message;
                        }
                        
                        function updateDisplay(area, chunks, markers, type, done) {
                            let text = chunks.join('\n\n');
                            let html = '';
                            
                            if (type === 'ppt' || type === 'pptx') {
                                html = parseMarkdown(text.replace(/=== Slide (\d+) ===/g, '\n\n## Slide $1\n\n'));
                            } else if (type === 'pdf' || type === 'doc' || type === 'docx') {
                                html = parseMarkdown(text.replace(/\n{3,}/g, '\n\n').replace(/([a-z])\n([a-z])/gi, '$1 $2'));
                            } else {
                                html = parseMarkdown(text);
                            }
                            
                            if (done && markers.length > 0) {
                                html += '<div style="margin-top: 24px; padding-top: 12px; border-top: 2px solid #e5e7eb; color: #6b7280; font-size: 0.85rem;">' + 
                                        `Total pages/slides: ${markers.length}` + 
                                        '</div>';
                            }
                            
                            area.innerHTML = html;
                        }
                        
                        setTimeout(() => {
                            const backBtn = document.getElementById('back-to-notes-btn');
                            if (backBtn) {
                                backBtn.addEventListener('click', loadLectureNotes);
                            }
                            const copyBtn = document.getElementById('copy-note-btn');
                            if (copyBtn) {
                                const fullText = extractedChunks.join('\n\n');
                                copyBtn.addEventListener('click', () => {
                                    navigator.clipboard.writeText(fullText || note.content || '').then(() => {
                                        showToast('Copied to clipboard!', 'success');
                                    });
                                });
                            }
                        }, 50);
                    });
                });
                
                container.querySelectorAll('.delete-note-btn').forEach(btn => {
                    btn.addEventListener('click', async () => {
                        const noteId = btn.dataset.id;
                        try {
                            await fetch(API_BASE + '/api/notes/' + noteId, { method: 'DELETE' });
                            loadLectureNotes();
                            showToast('Note deleted!', 'success');
                        } catch (err) {
                            showToast('Error deleting note', 'error');
                        }
                    });
                });
            }).catch(err => {
                container.innerHTML = '<p class="empty-message">Could not load notes.</p>';
            });
    }, 50);
}

function loadFlashcards() {
    const cards = JSON.parse(localStorage.getItem('flashcards') || '[]');
    let contentHtml = '';
    
    if (cards.length === 0) {
        contentHtml = '<p class="empty-message">No flashcards yet. Create your first one from Quick Tools!</p>';
    } else {
        contentHtml = `
            <div class="flashcards-display">
                ${cards.map((card, i) => `
                    <div class="flashcard-item" onclick="this.classList.toggle('flipped')">
                        <div class="flashcard-number">Card ${i + 1}</div>
                        <div class="flashcard-q">${card.question}</div>
                        <div class="flashcard-a">${card.answer}</div>
                    </div>
                `).join('')}
            </div>
        `;
    }
    
    showToolModal('Saved Flashcards', contentHtml);
}

function loadStudyPlans() {
    showToolModal('Create Study Plan', `
        <div class="study-plan-form">
            <div class="form-group">
                <label>Target Topic or Subject</label>
                <input type="text" id="study-topic" placeholder="e.g., Learn Python, Data Structures" />
            </div>
            <div class="form-group">
                <label>Timeframe</label>
                <select id="study-timeframe">
                    <option value="1 week">1 Week</option>
                    <option value="1 month">1 Month</option>
                    <option value="3 months">3 Months</option>
                </select>
            </div>
            <button class="btn-primary full-width" id="create-plan-btn">Generate Plan</button>
        </div>
    `);
    
    setTimeout(() => {
        document.getElementById('create-plan-btn').onclick = async () => {
            const topic = document.getElementById('study-topic').value;
            const timeframe = document.getElementById('study-timeframe').value;
            if (!topic) return showToast('Please enter a topic', 'error');
            
            document.querySelector('.tool-modal-body').innerHTML = '<div class="tool-loading">Generating study plan...</div>';
            
            try {
                const formData = new URLSearchParams();
                formData.append('message', `Create a detailed structured ${timeframe} study plan to learn ${topic}. Format logically with days/weeks.`);
                formData.append('user', user.name);
                formData.append('save_history', 'false');
                
                const response = await fetch(API_BASE + '/api/chat', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                    body: formData
                });
                const data = await response.json();
                
                if (data.reply) {
                    showToolModal('Your Study Plan', `<div class="study-plan-result" style="max-height: 400px; overflow-y: auto; padding-right: 12px;">${parseMarkdown(data.reply)}</div><button class="btn-primary full-width" style="margin-top: 16px;" onclick="loadStudyPlans()">Create Another Plan</button>`);
                }
            } catch(e) {
                showToast('Failed to generate plan', 'error');
                loadStudyPlans();
            }
        };
    }, 50);
}

function formatUserDuration(startDateStr) {
    if (!startDateStr) return 'using first time as sign up';
    const start = new Date(startDateStr);
    const now = new Date();
    const diffMs = now - start;
    
    if (diffMs < 5000) return 'using first time as sign up'; // Just joined
    
    // Calculate difference in months and days
    let months = (now.getFullYear() - start.getFullYear()) * 12 + (now.getMonth() - start.getMonth());
    let days = now.getDate() - start.getDate();
    
    // Adjust if days are negative
    if (days < 0) {
        months--;
        const prevMonth = new Date(now.getFullYear(), now.getMonth(), 0);
        days += prevMonth.getDate();
    }
    
    if (months === 0 && days === 0) return 'User since today';
    
    const monthPart = months > 0 ? `${months} month${months > 1 ? 's' : ''}` : '';
    const dayPart = days > 0 ? `${days} day${days > 1 ? 's' : ''}` : '';
    
    if (monthPart && dayPart) return `User since ${monthPart}, ${dayPart}`;
    return `User since ${monthPart || dayPart}`;
}

function showProfileModal() {
    const duration = formatUserDuration(user.signedUp);
    showToolModal('User Profile', `
        <div class="profile-view-container">
            <div class="profile-header">
                <div class="profile-avatar">${user.name.charAt(0).toUpperCase()}</div>
                <h3 class="profile-name">${user.name}</h3>
                <p class="profile-email">${user.email}</p>
            </div>
            <div class="profile-details">
                <div class="profile-detail-item">
                    <span class="detail-label">Experience</span>
                    <span class="detail-value">${duration}</span>
                </div>
            </div>
            <div class="profile-actions" style="margin-top: 24px;">
                <button class="btn-secondary full-width" id="logout-btn" style="background: #fee2e2; color: #dc2626; border-color: #fecaca;">Logout</button>
            </div>
        </div>
    `);
    
    document.getElementById('logout-btn')?.addEventListener('click', () => {
        localStorage.removeItem('educhat_user');
        window.location.href = 'index.html';
    });
}

function showSettingsModal() {
    const currentApiUrl = localStorage.getItem('educhat_api_url') || API_BASE;
    showToolModal('Settings', `
        <div class="settings-container">
            <div class="settings-section">
                <h4>Account Settings</h4>
                <form id="settings-profile-form">
                    <div class="form-group">
                        <label>Display Name</label>
                        <input type="text" id="settings-name" value="${user.name}" required />
                    </div>
                    <div class="form-group">
                        <label>New Password</label>
                        <input type="password" id="settings-pass" placeholder="Leave blank to keep current" />
                    </div>
                    <div class="form-group">
                        <label>Confirm Password</label>
                        <input type="password" id="settings-pass-confirm" placeholder="Confirm new password" />
                    </div>
                    <button type="submit" class="btn-primary full-width">Save Changes</button>
                </form>
            </div>
            <div class="settings-section" style="margin-top: 20px;">
                <h4>API Configuration</h4>
                <form id="settings-api-form">
                    <div class="form-group">
                        <label>Backend API URL</label>
                        <input type="text" id="settings-api-url" value="${currentApiUrl}" placeholder="http://localhost:8000" />
                        <small style="color: #6b7280; font-size: 0.8rem;">Change this to connect to a different backend server</small>
                    </div>
                    <button type="submit" class="btn-primary full-width">Save API URL</button>
                </form>
            </div>
        </div>
    `);
    
    document.getElementById('settings-profile-form')?.addEventListener('submit', (e) => {
        e.preventDefault();
        const name = document.getElementById('settings-name').value;
        const pass = document.getElementById('settings-pass').value;
        const confirm = document.getElementById('settings-pass-confirm').value;
        
        if (pass && pass !== confirm) {
            showToast('Passwords do not match!', 'error');
            return;
        }
        
        if (name) {
            const updatedUser = { ...user, name };
            if (pass) updatedUser.password = pass; 
            
            localStorage.setItem('educhat_user', JSON.stringify(updatedUser));
            showToast('Settings updated! Refreshing...', 'success');
            setTimeout(() => window.location.reload(), 1500);
        }
    });
    
    document.getElementById('settings-api-form')?.addEventListener('submit', (e) => {
        e.preventDefault();
        const apiUrl = document.getElementById('settings-api-url').value.trim();
        if (apiUrl) {
            localStorage.setItem('educhat_api_url', apiUrl);
            showToast('API URL saved! Refreshing...', 'success');
            setTimeout(() => window.location.reload(), 1500);
        }
    });
}

document.getElementById('user-profile-display').addEventListener('click', showProfileModal);

function showFlashcardGenerator() {
    showToolModal('Create Flashcards', `
        <div class="flashcard-form">
            <div class="form-group">
                <label>Topic</label>
                <input type="text" id="flashcard-topic" placeholder="e.g., Python, Data Structures, Biology" />
            </div>
            <div class="form-group">
                <label>Number of Cards</label>
                <select id="flashcard-count">
                    <option value="3">3 cards</option>
                    <option value="5" selected>5 cards</option>
                    <option value="10">10 cards</option>
                </select>
            </div>
            <button class="btn-primary full-width" id="generate-flashcards-btn">Generate Flashcards</button>
        </div>
    `);
    
    document.getElementById('generate-flashcards-btn').onclick = async () => {
        const topic = document.getElementById('flashcard-topic').value.trim();
        const count = document.getElementById('flashcard-count').value;
        
        if (!topic) {
            showToast('Please enter a topic', 'error');
            return;
        }
        
        document.querySelector('.tool-modal-body').innerHTML = '<div class="tool-loading">Generating flashcards...</div>';
        
        try {
            const formData = new URLSearchParams();
            formData.append('topic', topic);
            formData.append('num_cards', count);
            formData.append('user', user.name);
            
            const response = await fetch(API_BASE + '/api/chat/generate-flashcards', {
                method: 'POST',
                headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                body: formData
            });
            const data = await response.json();
            
            console.log('Flashcard API response:', data);
            
            if (data.flashcards) {
                const flashcards = parseFlashcards(data.flashcards);
                displayFlashcards(flashcards);
                saveFlashcardsToStorage(flashcards);
            } else if (data.error) {
                showToolModal('Error', `<p>${data.error}</p>`);
            }
        } catch (err) {
            console.error('Flashcard error:', err);
            showToolModal('Error', `<p>${err.message}</p>`);
        }
    };
}

function parseFlashcards(text) {
    const cards = [];
    const lines = text.split('\n');
    let currentQ = '';
    let currentA = '';
    let inAnswer = false;
    
    for (let line of lines) {
        line = line.trim();
        if (!line) continue;
        
        if (line.match(/^Q:/i) || line.match(/^\d+[\.):]/)) {
            if (currentQ && currentA) {
                cards.push({ question: currentQ, answer: currentA });
            }
            currentQ = line.replace(/^Q:|^[\d+[\.):]\s*/, '').trim();
            currentA = '';
            inAnswer = false;
        } else if (line.match(/^A:/i)) {
            currentA = line.replace(/^A:\s*/, '').trim();
            inAnswer = true;
        } else if (inAnswer) {
            currentA += ' ' + line;
        }
    }
    
    if (currentQ && currentA) {
        cards.push({ question: currentQ, answer: currentA });
    }
    
    return cards;
}

function displayFlashcards(cards) {
    if (cards.length === 0) {
        showToolModal('Flashcards', '<p class="tool-intro">No flashcards generated. Try a different topic.</p>');
        return;
    }
    
    showToolModal('Flashcards', `
        <div class="flashcards-display">
            ${cards.map((card, i) => `
                <div class="flashcard-item" onclick="this.classList.toggle('flipped')">
                    <div class="flashcard-number">Card ${i + 1}</div>
                    <div class="flashcard-q">${card.question}</div>
                    <div class="flashcard-a">${card.answer}</div>
                </div>
            `).join('')}
        </div>
    `);
}

function saveFlashcardsToStorage(cards) {
    const existing = JSON.parse(localStorage.getItem('flashcards') || '[]');
    const all = [...existing, ...cards];
    localStorage.setItem('flashcards', JSON.stringify(all));
    showToast(`Saved ${cards.length} flashcards!`, 'success');
}

function showQuizGenerator() {
    showToolModal('Generate Quiz', `
        <div class="quiz-form">
            <div class="form-group">
                <label>Topic</label>
                <input type="text" id="quiz-topic" placeholder="e.g., Python, Data Structures, Biology" />
            </div>
            <div class="form-group">
                <label>Difficulty</label>
                <select id="quiz-difficulty">
                    <option value="Easy">Easy</option>
                    <option value="Medium" selected>Medium</option>
                    <option value="Hard">Hard</option>
                </select>
            </div>
            <div class="form-group">
                <label>Number of Questions</label>
                <select id="quiz-count">
                    <option value="5" selected>5 questions</option>
                    <option value="10">10 questions</option>
                    <option value="20">20 questions</option>
                    <option value="30">30 questions</option>
                    <option value="50">50 questions</option>
                    <option value="100">100 questions</option>
                </select>
            </div>
            <button class="btn-primary full-width" id="generate-quiz-btn">Generate Quiz</button>
        </div>
    `);
    
    document.getElementById('generate-quiz-btn').onclick = async () => {
        const topic = document.getElementById('quiz-topic').value.trim();
        const difficulty = document.getElementById('quiz-difficulty').value;
        const count = document.getElementById('quiz-count').value;
        
        if (!topic) {
            showToast('Please enter a topic', 'error');
            return;
        }
        
        document.querySelector('.tool-modal-body').innerHTML = '<div class="tool-loading">Generating quiz...</div>';
        
        try {
            const formData = new URLSearchParams();
            formData.append('topic', topic);
            formData.append('difficulty', difficulty);
            formData.append('num_questions', count);
            formData.append('user', user.name);
            
            const response = await fetch(API_BASE + '/api/chat/generate-quiz', {
                method: 'POST',
                headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                body: formData
            });
            const data = await response.json();
            
            if (data.quiz) {
                const quiz = parseQuiz(data.quiz);
                displayQuiz(quiz);
            }
        } catch (err) {
            showToolModal('Error', `<p>${err.message}</p>`);
        }
    };
}

function parseQuiz(text) {
    const questions = [];
    const lines = text.split('\n');
    let currentQ = '';
    let options = [];
    let correctAnswer = '';
    let correctIndex = -1;
    
    for (let line of lines) {
        line = line.trim();
        if (!line) continue;
        
        if (line.match(/^Q\d+[\):]/)) {
            if (currentQ && options.length > 0) {
                questions.push({ question: currentQ, options: options.slice(0, 4), correctAnswer: correctAnswer, correctIndex: correctIndex });
            }
            currentQ = line.replace(/^Q\d+[\):]\s*/, '').trim();
            options = [];
            correctAnswer = '';
            correctIndex = -1;
        } else if (line.match(/^[A-D]\)/i)) {
            const optionText = line.replace(/^[A-D]\)\s*/, '').trim();
            const letterMatch = line.match(/^([A-D])\)/i);
            if (letterMatch) {
                const letter = letterMatch[1].toUpperCase();
                options.push(letter + ') ' + optionText);
                if (line.toLowerCase().includes('[correct]') || line.includes('*') || letterMatch.index === 0) {
                    correctAnswer = letter + ') ' + optionText;
                    correctIndex = options.length - 1;
                }
            } else {
                options.push(optionText);
            }
        } else if (line.toLowerCase().startsWith('answer:') || line.toLowerCase().startsWith('correct answer:')) {
            const answerStr = line.replace(/^(answer:|correct answer:)\s*/i, '').trim().toUpperCase();
            const letterMatch = answerStr.match(/^([A-D])/);
            if (letterMatch) {
                const letter = letterMatch[1];
                correctAnswer = letter;
                const idx = letter.charCodeAt(0) - 65;
                if (idx >= 0 && idx < options.length) {
                    correctIndex = idx;
                    correctAnswer = options[idx];
                }
            }
        }
    }
    
    if (currentQ && options.length > 0) {
        questions.push({ question: currentQ, options: options.slice(0, 4), correctAnswer: correctAnswer, correctIndex: correctIndex });
    }
    
    return questions;
}

function displayQuiz(quiz) {
    if (quiz.length === 0) {
        showToolModal('Quiz', '<p class="tool-intro">No quiz generated. Try a different topic.</p>');
        return;
    }
    
    showToolModal('Quiz', `
        <div class="quiz-display">
            <form id="quiz-form">
                ${quiz.map((q, i) => `
                    <div class="quiz-question">
                        <div class="question-text">${i + 1}. ${q.question}</div>
                        <div class="options">
                            ${q.options.map((opt, j) => `
                                <label class="option-label" id="option-${i}-${j}">
                                    <input type="radio" name="q${i}" value="${j}" data-option="${opt}" />
                                    <span class="option-text">${opt}</span>
                                </label>
                            `).join('')}
                        </div>
                    </div>
                `).join('')}
                <button type="submit" class="btn-primary full-width" id="submit-quiz-btn">Submit Answers</button>
            </form>
        </div>
    `);
    
    document.getElementById('quiz-form').onsubmit = async (e) => {
        e.preventDefault();
        let correct = 0;
        let answered = 0;
        const total = quiz.length;
        
        let resultsHtml = '';
        
        for (let i = 0; i < quiz.length; i++) {
            const q = quiz[i];
            const selected = document.querySelector('input[name="q' + i + '"]:checked');
            const selectedValue = selected ? parseInt(selected.value) : -1;
            let isCorrect = false;
            let status = 'unanswered';
            
            if (selected) {
                answered++;
                isCorrect = (selectedValue === q.correctIndex);
                
                if (isCorrect) {
                    correct++;
                    status = 'correct';
                } else {
                    status = 'incorrect';
                }
            }
            
            // Build options HTML for this question
            let optionHtml = '';
            for (let j = 0; j < q.options.length; j++) {
                let opt = q.options[j];
                let isThisCorrect = (j === q.correctIndex);
                let isUserSelected = (selectedValue === j);
                
                let optClass = '';
                let optLabel = '';
                
                if (status === 'unanswered') {
                    // Unanswered: show all options plain, do NOT reveal correct answer
                    optClass = 'quiz-result-opt-neutral';
                } else {
                    // Answered: highlight selected and correct
                    if (isThisCorrect && isUserSelected) {
                        optClass = 'quiz-result-opt-correct';
                        optLabel = ' ✓ Your Answer (Correct)';
                    } else if (isThisCorrect) {
                        optClass = 'quiz-result-opt-correct';
                        optLabel = ' ✓ Correct Answer';
                    } else if (isUserSelected) {
                        optClass = 'quiz-result-opt-wrong';
                        optLabel = ' ✗ Your Answer';
                    } else {
                        optClass = 'quiz-result-opt-neutral';
                    }
                }
                
                optionHtml += '<div class="quiz-result-opt ' + optClass + '">'
                    + '<span class="quiz-result-opt-letter">' + String.fromCharCode(65 + j) + '</span>'
                    + '<span class="quiz-result-opt-text">' + opt + '</span>'
                    + (optLabel ? '<span class="quiz-result-opt-label">' + optLabel + '</span>' : '')
                    + '</div>';
            }
            
            // Status badge
            let statusBadge = '';
            let cardClass = '';
            if (status === 'correct') {
                statusBadge = '<span class="quiz-result-badge badge-correct">✓ Correct</span>';
                cardClass = 'quiz-result-q-correct';
            } else if (status === 'incorrect') {
                statusBadge = '<span class="quiz-result-badge badge-wrong">✗ Wrong</span>';
                cardClass = 'quiz-result-q-wrong';
            } else {
                statusBadge = '<span class="quiz-result-badge badge-skipped">— Skipped</span>';
                cardClass = 'quiz-result-q-skipped';
            }
            
            resultsHtml += '<div class="quiz-result-q ' + cardClass + '">'
                + '<div class="quiz-result-q-header">'
                + '<span class="quiz-result-q-num">Q' + (i + 1) + '</span>'
                + statusBadge
                + '</div>'
                + '<div class="quiz-result-q-text">' + q.question + '</div>'
                + '<div class="quiz-result-opts">' + optionHtml + '</div>'
                + '</div>';
        }
        
        // Performance summary
        const percentage = Math.round((correct / total) * 100);
        let resultMessage = '';
        let perfClass = '';
        if (percentage >= 90) { resultMessage = 'Outstanding! 🏆'; perfClass = 'perf-band-excellent'; }
        else if (percentage >= 80) { resultMessage = 'Excellent! 🌟'; perfClass = 'perf-band-excellent'; }
        else if (percentage >= 60) { resultMessage = 'Good job! 👍'; perfClass = 'perf-band-good'; }
        else if (percentage >= 40) { resultMessage = 'Keep practicing 💪'; perfClass = 'perf-band-average'; }
        else { resultMessage = 'Need more study 📖'; perfClass = 'perf-band-poor'; }
        
        const perfHtml = '<div class="quiz-perf-summary ' + perfClass + '">'
            + '<div class="quiz-perf-row">'
            + '<div class="quiz-perf-main">'
            + '<span class="quiz-perf-pct">' + percentage + '%</span>'
            + '<span class="quiz-perf-label">' + resultMessage + '</span>'
            + '</div>'
            + '<div class="quiz-perf-stats">'
            + '<div class="quiz-perf-stat"><span class="quiz-perf-stat-num">' + correct + '</span> correct</div>'
            + '<div class="quiz-perf-stat"><span class="quiz-perf-stat-num">' + (answered - correct) + '</span> wrong</div>'
            + '<div class="quiz-perf-stat"><span class="quiz-perf-stat-num">' + (total - answered) + '</span> skipped</div>'
            + '</div>'
            + '</div>'
            + '</div>';
        
        showToolModal('Quiz Results', '<div class="quiz-results-container">'
            + '<div class="quiz-results-scroll">' + resultsHtml + '</div>'
            + perfHtml
            + '</div>');
    };
}

document.addEventListener('DOMContentLoaded', async () => {
    await loadChatHistory();
    document.getElementById('app').classList.add('loaded');
});