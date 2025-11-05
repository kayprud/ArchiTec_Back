class ChatApp {
    constructor() {
        this.sessionId = this.generateSessionId();
        this.pdfUrl = null;
        this.isRecording = false;
        this.recognition = null;
        this.mode = null;
        this.inputType = null;
        this.productList = [];
        
        this.initializeElements();
        this.initializeSpeechRecognition();
        this.bindEvents();
    }
    
    generateSessionId() {
        return 'session_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
    }
    
    initializeElements() {
        // Screens
        this.initialScreen = document.getElementById('initialScreen');
        this.chatScreen = document.getElementById('chatScreen');
        
        // Initial screen elements
        this.projectInput = document.getElementById('projectInput');
        this.initialVoiceBtn = document.getElementById('initialVoiceBtn');
        
        // Chat screen elements
        this.chatMessages = document.getElementById('chatMessages');
        this.messageInput = document.getElementById('messageInput');
        this.sendBtn = document.getElementById('sendBtn');
        this.voiceBtn = document.getElementById('voiceBtn');
        this.backBtn = document.getElementById('backBtn');
        this.voiceModal = document.getElementById('voiceModal');
        this.stopVoiceBtn = document.getElementById('stopVoiceBtn');
        this.typingIndicator = document.getElementById('typingIndicator');
        this.pdfArea = document.getElementById('pdfArea');
        this.downloadBtn = document.getElementById('downloadBtn');
        this.generateQuoteBtn = document.getElementById('generateQuoteBtn');
        this.clearListBtn = document.getElementById('clearListBtn');
        this.listContent = document.getElementById('listContent');
        this.welcomeText = document.getElementById('welcomeText');
        this.voiceText = document.getElementById('voiceText');
        this.productListEl = document.getElementById('productList');
    }
    
    initializeSpeechRecognition() {
        if ('webkitSpeechRecognition' in window || 'SpeechRecognition' in window) {
            const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
            this.recognition = new SpeechRecognition();
            this.recognition.continuous = false;
            this.recognition.interimResults = false;
            this.recognition.lang = 'pt-BR';
            
            this.recognition.onresult = (event) => {
                const transcript = event.results[0][0].transcript;
                this.handleVoiceInput(transcript);
            };
            
            this.recognition.onerror = (event) => {
                console.error('Speech recognition error:', event.error);
                this.stopRecording();
                this.showError('Erro ao reconhecer voz. Tente novamente.');
            };
            
            this.recognition.onend = () => {
                this.stopRecording();
            };
        } else {
            console.warn('Speech recognition not supported');
            // Hide voice buttons if not supported
            if (this.initialVoiceBtn) this.initialVoiceBtn.style.display = 'none';
            if (this.voiceBtn) this.voiceBtn.style.display = 'none';
        }
    }
    
    bindEvents() {
        // Option buttons
        document.querySelectorAll('.option-card').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const type = e.currentTarget.dataset.type;
                const input = e.currentTarget.dataset.input;
                this.selectMode(type, input);
            });
        });
        
        // Initial screen events
        if (this.projectInput) {
            this.projectInput.addEventListener('keypress', (e) => {
                if (e.key === 'Enter') {
                    e.preventDefault();
                    this.handleInitialInput();
                }
            });
        }
        
        if (this.initialVoiceBtn) {
            this.initialVoiceBtn.addEventListener('click', () => {
                this.startRecording('initial');
            });
        }
        
        // Chat screen events
        if (this.sendBtn) {
            this.sendBtn.addEventListener('click', () => this.sendMessage());
        }
        
        if (this.messageInput) {
            this.messageInput.addEventListener('keypress', (e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    this.sendMessage();
                }
            });
        }
        
        if (this.voiceBtn) {
            this.voiceBtn.addEventListener('click', () => this.startRecording('chat'));
        }
        
        if (this.backBtn) {
            this.backBtn.addEventListener('click', () => this.goToInitialScreen());
        }
        
        if (this.stopVoiceBtn) {
            this.stopVoiceBtn.addEventListener('click', () => this.stopRecording());
        }
        
        // Product list events
        if (this.generateQuoteBtn) {
            this.generateQuoteBtn.addEventListener('click', () => this.generateMultipleQuote());
        }
        
        if (this.clearListBtn) {
            this.clearListBtn.addEventListener('click', () => this.clearProductList());
        }
        
        // PDF download
        if (this.downloadBtn) {
            this.downloadBtn.addEventListener('click', () => this.downloadPDF());
        }
        
        // Voice modal close
        if (this.voiceModal) {
            this.voiceModal.addEventListener('click', (e) => {
                if (e.target === this.voiceModal) {
                    this.stopRecording();
                }
            });
        }
    }
    
    handleInitialInput() {
        const message = this.projectInput.value.trim();
        if (!message) return;
        
        // Auto-detect mode based on content
        const hasMultiple = /\b(e|,|e\s+|mais|\d+\s+.+\s+(e|,))\b/i.test(message);
        this.mode = hasMultiple ? 'multiple' : 'single';
        this.inputType = 'text';
        
        this.selectMode(this.mode, this.inputType, message);
    }
    
    selectMode(type, input, initialMessage = null) {
        this.mode = type;
        this.inputType = input;
        
        // Hide initial screen and show chat screen
        this.initialScreen.style.display = 'none';
        this.chatScreen.style.display = 'block';
        
        // Update welcome message
        if (type === 'single') {
            this.welcomeText.textContent = 'Olá! Sou o assistente de orçamentos. Descreva o produto que deseja orçar (ex: "corrediça HAFELE", "5 divisores Von Ort").';
        } else {
            this.welcomeText.textContent = 'Olá! Adicione os produtos que deseja orçar. Você pode adicionar um por vez ou vários de uma vez. Quando terminar, clique em "Gerar Orçamento".';
            this.productListEl.style.display = 'block';
        }
        
        // If there's an initial message, process it
        if (initialMessage) {
            setTimeout(() => {
                this.messageInput.value = initialMessage;
                this.sendMessage();
            }, 500);
        } else if (input === 'voice') {
            setTimeout(() => this.startRecording('chat'), 500);
        }
    }
    
    goToInitialScreen() {
        this.chatScreen.style.display = 'none';
        this.initialScreen.style.display = 'flex';
        this.productListEl.style.display = 'none';
        this.pdfArea.style.display = 'none';
        this.projectInput.value = '';
        this.messageInput.value = '';
        this.clearProductList();
    }
    
    handleVoiceInput(transcript) {
        this.stopRecording();
        
        if (this.mode === 'single') {
            this.messageInput.value = transcript;
            this.sendMessage();
        } else {
            this.messageInput.value = transcript;
            this.addMultipleProducts(transcript);
        }
    }
    
    startRecording(context = 'chat') {
        if (!this.recognition) {
            this.showError('Seu navegador não suporta reconhecimento de voz');
            return;
        }
        
        this.isRecording = true;
        this.voiceModal.style.display = 'flex';
        
        if (context === 'initial') {
            this.initialVoiceBtn.classList.add('recording');
            this.voiceText.textContent = 'Fale sobre o projeto que deseja orçar...';
        } else {
            this.voiceBtn.classList.add('recording');
            this.voiceText.textContent = this.mode === 'multiple' ? 
                'Fale os produtos que deseja adicionar...' : 'Ouvindo...';
        }
        
        try {
            this.recognition.start();
        } catch (error) {
            console.error('Error starting recognition:', error);
            this.stopRecording();
        }
    }
    
    stopRecording() {
        this.isRecording = false;
        this.voiceModal.style.display = 'none';
        
        if (this.initialVoiceBtn) {
            this.initialVoiceBtn.classList.remove('recording');
        }
        if (this.voiceBtn) {
            this.voiceBtn.classList.remove('recording');
        }
        
        if (this.recognition) {
            try {
                this.recognition.stop();
            } catch (error) {
                console.error('Error stopping recognition:', error);
            }
        }
    }
    
    async sendMessage() {
        const message = this.messageInput.value.trim();
        if (!message) return;
        
        if (this.mode === 'multiple') {
            this.addMultipleProducts(message);
        } else {
            this.addMessage(message, 'user');
            this.messageInput.value = '';
            
            this.sendBtn.disabled = true;
            this.showTypingIndicator();
            
            try {
                const response = await fetch('/chat', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        message: message,
                        session_id: this.sessionId,
                        mode: this.mode
                    })
                });
                
                const data = await response.json();
                
                if (response.ok) {
                    this.addMessage(data.response, 'bot');
                    
                    if (data.pdf_url) {
                        this.pdfUrl = data.pdf_url;
                        this.showPDFDownload();
                    }
                } else {
                    this.showError(data.error || 'Ocorreu um erro ao processar sua mensagem');
                }
            } catch (error) {
                console.error('Error sending message:', error);
                this.showError('Erro de conexão. Verifique sua internet e tente novamente.');
            } finally {
                this.sendBtn.disabled = false;
                this.hideTypingIndicator();
            }
        }
    }
    
    async addMultipleProducts(message) {
        this.messageInput.value = '';
        this.sendBtn.disabled = true;
        this.showTypingIndicator();
        
        try {
            const response = await fetch('/extract-products', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    message: message,
                    session_id: this.sessionId
                })
            });
            
            const data = await response.json();
            
            if (response.ok && data.products) {
                data.products.forEach(product => {
                    this.addProductToList(product);
                });
            } else {
                this.showError('Não consegui identificar os produtos. Tente novamente.');
            }
        } catch (error) {
            console.error('Error extracting products:', error);
            this.showError('Erro ao processar produtos. Tente novamente.');
        } finally {
            this.sendBtn.disabled = false;
            this.hideTypingIndicator();
        }
    }
    
    addProductToList(product) {
        const existingIndex = this.productList.findIndex(p => p.name === product.name);
        
        if (existingIndex !== -1) {
            this.productList[existingIndex].quantity += product.quantity;
        } else {
            this.productList.push(product);
        }
        
        this.updateProductListUI();
    }
    
    updateProductListUI() {
        if (this.productList.length === 0) {
            this.listContent.innerHTML = '<p class="empty-list">Nenhum item adicionado ainda</p>';
            this.generateQuoteBtn.disabled = true;
        } else {
            let html = '';
            let total = 0;
            
            this.productList.forEach((product, index) => {
                const itemTotal = product.price * product.quantity;
                total += itemTotal;
                
                html += `
                    <div class="product-item">
                        <div class="product-info">
                            <div class="product-name">${product.name}</div>
                            <div class="product-quantity">Quantidade: ${product.quantity}</div>
                        </div>
                        <div class="product-price">R$ ${itemTotal.toFixed(2)}</div>
                        <button class="remove-product" onclick="app.removeProduct(${index})">
                            <i class="fas fa-times"></i>
                        </button>
                    </div>
                `;
            });
            
            html += `
                <div class="product-item" style="border-top: 2px solid var(--primary-color); margin-top: 8px; padding-top: 12px;">
                    <div class="product-info">
                        <div class="product-name" style="font-weight: 600;">TOTAL</div>
                    </div>
                    <div class="product-price" style="font-size: 18px; color: var(--primary-color);">R$ ${total.toFixed(2)}</div>
                </div>
            `;
            
            this.listContent.innerHTML = html;
            this.generateQuoteBtn.disabled = false;
        }
    }
    
    removeProduct(index) {
        this.productList.splice(index, 1);
        this.updateProductListUI();
    }
    
    clearProductList() {
        this.productList = [];
        this.updateProductListUI();
    }
    
    async generateMultipleQuote() {
        if (this.productList.length === 0) return;
        
        this.sendBtn.disabled = true;
        this.generateQuoteBtn.disabled = true;
        this.showTypingIndicator();
        
        try {
            const response = await fetch('/chat', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    message: 'generate_multiple_quote',
                    session_id: this.sessionId,
                    mode: this.mode,
                    products: this.productList
                })
            });
            
            const data = await response.json();
            
            if (response.ok) {
                this.addMessage(data.response, 'bot');
                
                if (data.pdf_url) {
                    this.pdfUrl = data.pdf_url;
                    this.showPDFDownload();
                }
            } else {
                this.showError(data.error || 'Ocorreu um erro ao gerar o orçamento');
            }
        } catch (error) {
            console.error('Error generating quote:', error);
            this.showError('Erro de conexão. Verifique sua internet e tente novamente.');
        } finally {
            this.sendBtn.disabled = false;
            this.generateQuoteBtn.disabled = false;
            this.hideTypingIndicator();
        }
    }
    
    addMessage(text, sender) {
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${sender}`;
        
        const avatar = document.createElement('div');
        avatar.className = sender === 'bot' ? 'bot-avatar' : 'user-avatar';
        avatar.innerHTML = sender === 'bot' ? '<i class="fas fa-robot"></i>' : '<i class="fas fa-user"></i>';
        
        const content = document.createElement('div');
        content.className = 'message-content';
        
        const formattedText = this.formatMessage(text);
        content.innerHTML = formattedText;
        
        messageDiv.appendChild(avatar);
        messageDiv.appendChild(content);
        
        this.chatMessages.appendChild(messageDiv);
        this.scrollToBottom();
    }
    
    formatMessage(text) {
        text = text.replace(/\*(.*?)\*/g, '<strong>$1</strong>');
        text = text.replace(/\n/g, '<br>');
        
        // Convert markdown tables to HTML tables
        const tableRegex = /\|(.+)\|\n\|(.+)\|\n((?:\|.+\|\n?)*)/g;
        text = text.replace(tableRegex, (match, header, separator, rows) => {
            const headers = header.split('|').map(h => h.trim()).filter(h => h);
            const rowsArray = rows.trim().split('\n').map(row => 
                row.split('|').map(cell => cell.trim()).filter(cell => cell)
            );
            
            let tableHTML = '<table class="message-table"><thead><tr>';
            headers.forEach(h => {
                tableHTML += `<th>${h}</th>`;
            });
            tableHTML += '</tr></thead><tbody>';
            
            rowsArray.forEach((row, index) => {
                const isTotalRow = row.some(cell => cell.toLowerCase().includes('total'));
                tableHTML += `<tr class="${isTotalRow ? 'total-row' : ''}">`;
                row.forEach(cell => {
                    tableHTML += `<td>${cell}</td>`;
                });
                tableHTML += '</tr>';
            });
            
            tableHTML += '</tbody></table>';
            
            return tableHTML;
        });
        
        return text;
    }
    
    showTypingIndicator() {
        this.typingIndicator.style.display = 'flex';
        this.scrollToBottom();
    }
    
    hideTypingIndicator() {
        this.typingIndicator.style.display = 'none';
    }
    
    showError(message) {
        this.addMessage(`❌ ${message}`, 'bot');
    }
    
    showPDFDownload() {
        this.pdfArea.style.display = 'block';
        this.scrollToBottom();
    }
    
    downloadPDF() {
        if (this.pdfUrl) {
            const link = document.createElement('a');
            link.href = this.pdfUrl;
            link.download = `orcamento_${Date.now()}.pdf`;
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
        }
    }
    
    scrollToBottom() {
        this.chatMessages.scrollTop = this.chatMessages.scrollHeight;
    }
}

// Initialize app
let app;
document.addEventListener('DOMContentLoaded', () => {
    app = new ChatApp();
});