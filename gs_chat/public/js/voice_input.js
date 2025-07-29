// public/js/voice_input.js
export class VoiceInputManager {
    constructor(chatInput, onResult) {
        this.chatInput = chatInput;
        this.onResult = onResult;
        this.recognition = null;
        this.isListening = false;
        this.supportedLanguages = {
            'en-US': 'English (US)',
            'en-GB': 'English (UK)',
            'es-ES': 'Spanish',
            'fr-FR': 'French',
            'de-DE': 'German',
            'it-IT': 'Italian',
            'pt-BR': 'Portuguese (Brazil)',
            'zh-CN': 'Chinese (Mandarin)',
            'ja-JP': 'Japanese',
            'ko-KR': 'Korean',
            'hi-IN': 'Hindi',
            'ar-SA': 'Arabic',
            'ru-RU': 'Russian'
        };
        this.currentLanguage = 'en-US';
        this.initializeSpeechRecognition();
    }

    initializeSpeechRecognition() {
        // Check browser support
        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        
        if (!SpeechRecognition) {
            console.warn('Speech recognition not supported');
            return false;
        }

        this.recognition = new SpeechRecognition();
        this.recognition.continuous = false;
        this.recognition.interimResults = true;
        this.recognition.maxAlternatives = 1;
        this.recognition.lang = this.currentLanguage;

        // Event handlers
        this.recognition.onstart = () => {
            this.isListening = true;
            this.updateUI(true);
        };

        this.recognition.onend = () => {
            this.isListening = false;
            this.updateUI(false);
        };

        this.recognition.onresult = (event) => {
            let finalTranscript = '';
            let interimTranscript = '';

            for (let i = event.resultIndex; i < event.results.length; i++) {
                const transcript = event.results[i][0].transcript;
                if (event.results[i].isFinal) {
                    finalTranscript += transcript + ' ';
                } else {
                    interimTranscript += transcript;
                }
            }

            // Update chat input with interim results
            if (interimTranscript) {
                this.showInterimResult(interimTranscript);
            }

            // Process final results
            if (finalTranscript) {
                this.processFinalResult(finalTranscript.trim());
            }
        };

        this.recognition.onerror = (event) => {
            console.log(event)
            console.error('Speech recognition error:', event.error);
            this.handleError(event.error);
            this.isListening = false;
            this.updateUI(false);
        };

        return true;
    }

    toggle() {
        if (this.isListening) {
            this.stop();
        } else {
            this.start();
        }
    }

    start() {
        if (!this.recognition) {
            frappe.show_alert({
                message: __('Speech recognition not supported in your browser'),
                indicator: 'red'
            });
            return;
        }

        // Request microphone permission
        navigator.mediaDevices.getUserMedia({ audio: true })
            .then(() => {
                this.recognition.lang = this.currentLanguage;
                this.recognition.start();
            })
            .catch((err) => {
                frappe.show_alert({
                    message: __('Microphone access denied'),
                    indicator: 'red'
                });
            });
    }

    stop() {
        if (this.recognition && this.isListening) {
            this.recognition.stop();
        }
    }

    setLanguage(langCode) {
        if (this.supportedLanguages[langCode]) {
            this.currentLanguage = langCode;
            // Save preference
            localStorage.setItem('chatbot-voice-language', langCode);
        }
    }

    showInterimResult(text) {
        // Show interim results in a special way
        const existingInterim = this.chatInput.find('.voice-interim');
        if (existingInterim.length) {
            existingInterim.text(text);
        } else {
            this.chatInput.append(`<span class="voice-interim">${text}</span>`);
        }
    }

    processFinalResult(text) {
        // Remove interim display
        this.chatInput.find('.voice-interim').remove();
        
        // Get current content
        const currentText = this.chatInput.text().trim();
        
        // Append to existing text or replace
        const newText = currentText ? currentText + ' ' + text : text;
        
        // Update chat input
        this.chatInput.text(newText);
        
        // Move cursor to end
        this.moveCursorToEnd();
        
        // Callback
        if (this.onResult) {
            this.onResult(text);
        }
    }

    moveCursorToEnd() {
        const range = document.createRange();
        const selection = window.getSelection();
        
        range.selectNodeContents(this.chatInput[0]);
        range.collapse(false);
        
        selection.removeAllRanges();
        selection.addRange(range);
        
        this.chatInput[0].focus();
    }

    handleError(error) {
        const errorMessages = {
            'no-speech': __('No speech detected. Please try again.'),
            'audio-capture': __('No microphone found.'),
            'not-allowed': __('Microphone permission denied.'),
            'network': __('Network error. Please check your connection.')
        };

        frappe.show_alert({
            message: errorMessages[error] || __('Speech recognition error: ') + error,
            indicator: 'red'
        });
    }

    updateUI(isListening) {
        const voiceButton = $('.voice-input-button');
        if (isListening) {
            voiceButton.addClass('listening');
            voiceButton.find('i').removeClass('fa-microphone').addClass('fa-microphone-slash');
        } else {
            voiceButton.removeClass('listening');
            voiceButton.find('i').removeClass('fa-microphone-slash').addClass('fa-microphone');
        }
    }

    createUI() {
        // Create voice input button
        const voiceButton = $(`
            <button class="btn btn-sm voice-input-button" title="${__('Voice Input')}">
                <i class="fa fa-microphone"></i>
            </button>
        `);

        // Create language selector
        const langSelector = $(`
            <select class="voice-language-selector" title="${__('Select Language')}">
                ${Object.entries(this.supportedLanguages).map(([code, name]) => 
                    `<option value="${code}" ${code === this.currentLanguage ? 'selected' : ''}>${name}</option>`
                ).join('')}
            </select>
        `);

        // Event handlers
        voiceButton.on('click', () => this.toggle());
        langSelector.on('change', (e) => this.setLanguage(e.target.value));

        // Load saved language preference
        const savedLang = localStorage.getItem('chatbot-voice-language');
        if (savedLang && this.supportedLanguages[savedLang]) {
            this.currentLanguage = savedLang;
            langSelector.val(savedLang);
        }

        return { voiceButton, langSelector };
    }
}

// Integration with chat widget - Add to gs_chat.bundle.js setupEvents()
function setupVoiceInput() {
    const voiceManager = new VoiceInputManager(
        this.chatInput,
        (text) => {
            // Optional: Auto-send after voice input
            if (this.autoSendVoice && text.length > 0) {
                setTimeout(() => this.sendMessage(), 500);
            }
        }
    );

    const { voiceButton, langSelector } = voiceManager.createUI();
    
    // Add to chat footer
    this.chatDialog.find('.chat-footer').prepend(langSelector);
    this.chatDialog.find('.send-button').before(voiceButton);
    
    // Store reference
    this.voiceManager = voiceManager;
}
