frappe.provide("gs_chat");

import { SlashCommandManager } from "./slash_commands.js"

gs_chat.ChatbotWidget = class {
    constructor() {
        this.messages = [];
        this.isOpen = false;
        this.slashCommands = null;
        this.conversations = [];
        this.currentConversationId = null;
        this.sidebarOpen = false;
        this.setupIcon();
        this.fetchConversations();
    }

    setupIcon() {
        const $chatbotIcon = $(`
            <li class="nav-item dropdown dropdown-notifications dropdown-mobile chatbot-icon-open">
                <a class="nav-link" data-toggle="dropdown" aria-expanded="false" 
                   title="Growth Assistant" href="#" onclick="return false;">
                    ${frappe.utils.icon("chatbot")}
                </a>
            </li>
        `)
        $('.dropdown-help').before($chatbotIcon);

        $chatbotIcon.on('click', () => {
            this.toggleChatbot();
            return false;
        });
    }

    toggleChatbot() {
        if (this.isOpen) {
            this.closeChat();
        } else {
            this.openChat();
        }
    }
    
    openChat() {
        // Create the dialog if it doesn't exist
        if (!this.chatDialog) {
            this.createDialog();
            this.setupResizeHandle();
            this.loadSavedDimensions();
            this.setupEvents();
            this.renderConversationList();

            // Initialize slash commands
            this.slashCommands = new SlashCommandManager(this.chatInput);
        }

        // Show the dialog
        this.chatDialog.addClass("open");
        this.chatDialog.removeClass("minimized");

        this.isOpen = true;

        // Focus on input
        this.chatInput.focus();

        // Add welcome message if this is the first time and no conversation is loaded
        if (this.messages.length === 0 && !this.currentConversationId) {
            this.startNewConversation();
        }

        // Dispatch event that chatbot is loaded (for slash commands)
        $(document).trigger('growth_chatbot_loaded');
    }

    createDialog() {
        this.chatDialog = $(`
            <div class="modal-content gs-chatbot-widget sidebar-hidden">
                <div class="chat-sidebar">
                    <div class="conversation-list">
                        <div class="conversation-item new-chat-item">
                            <div class="conversation-title"><i class="fa fa-plus"></i> New Chat</div>
                        </div>
                    </div>
                </div>
                <div class="chat-main">
                    <div class="modal-header">
                        <div class="fill-width flex title-section">
                            <button class="btn btn-sm toggle-sidebar-button">
                                ${frappe.utils.icon("list")}
                            </button>
                            <span class="indicator hidden"></span>
                            <h4 class="modal-title">G'Bot</h4>
                        </div>
                        <div class="modal-actions">
                            <button class="btn btn-sm action-button" data-action="refresh" title="Reset Conversation">
                                ${frappe.utils.icon("refresh")}
                            </button>
                            <button class="btn btn-modal-minimize action-button btn-link" data-action="minimize" title="Minimize">
                                ${frappe.utils.icon("collapse")}
                            </button>
                            <button class="btn btn-modal-close btn-link action-button" data-action="close" title="Close">
                                ${frappe.utils.icon("close-alt")}
                            </button>
                        </div>
                    </div>
                    <div class="modal-body chat-body ui-front">
                        <div class="chatbot-messages"></div>
                        <div class="typing-indicator d-none">
                            <span></span><span></span><span></span>
                        </div>
                    </div>
                    <div class="chat-footer">
                        <div class="chat-input-container">
                            <span class="chat-input" data-placeholder="Ask anything..." contenteditable="true" enterkeyhint="enter" tabindex="0"></span>
                            <button class="btn btn-primary btn-sm send-button">
                                <i class="fa fa-paper-plane"></i>
                            </button>
                        </div>
                    </div>
                </div>
                <div class="resize-handle"></div>
            </div>
            `)

        $('body').append(this.chatDialog);
    }

    setupEvents() {
        const me = this;

        // Cache elements
        this.chatBody = this.chatDialog.find('.chat-body');
        this.messagesContainer = this.chatDialog.find('.chatbot-messages');
        this.chatInput = this.chatDialog.find('.chat-input');
        this.typingIndicator = this.chatDialog.find('.typing-indicator');
        this.sendButton = this.chatDialog.find('.send-button');
        this.conversationList = this.chatDialog.find('.conversation-list');
        this.newChatItem = this.chatDialog.find('.new-chat-item');
        this.toggleSidebarButton = this.chatDialog.find('.toggle-sidebar-button');

        // Setup keyboard shortcut (Ctrl+Enter to send)
        this.chatInput.on('keydown', function(e) {
            if (e.key === 'Enter' && !e.shiftKey && !e.ctrlKey && !e.metaKey && !me.slashCommands.isActive) {
                e.preventDefault();
                me.sendMessage();
                return false;
            }
        });

        this.sendButton.on('click', function() {
            me.sendMessage();
        });

        this.chatDialog.find('.action-button').on('click', function(e) {
            const action = $(e.currentTarget).data('action');
            
            if (action === 'refresh') {
                me.resetConversation();
            } else if (action === 'minimize') {
                me.minimizeChat();
            } else if (action === 'close') {
                me.closeChat();
            }
        });
        
        // New chat item
        this.newChatItem.on('click', function() {
            me.startNewConversation();
        });
        
        // Toggle sidebar button
        this.toggleSidebarButton.on('click', function() {
            me.toggleSidebar();
        });

        this.fixPlaceholder();
    }
    
    toggleSidebar() {
        this.chatDialog.toggleClass('sidebar-hidden');
        this.sidebarOpen = !this.chatDialog.hasClass('sidebar-hidden');
        
        // Save sidebar state
        if (localStorage) {
            localStorage.setItem('chatbot-sidebar-open', this.sidebarOpen ? '1' : '0');
        }
    }
    
    fetchConversations() {
        const me = this;
        
        // Call API to get conversations
        frappe.call({
            method: 'gs_chat.controllers.chat.get_conversations',
            callback: (r) => {
                if (r.message && r.message.success) {
                    me.conversations = r.message.conversations || [];
                } else {
                    console.error("Failed to fetch conversations:", r.message);
                }
            }
        });
    }
    
    renderConversationList() {
        const me = this;
        
        // Clear all except the new chat item
        this.conversationList.find('.conversation-item:not(.new-chat-item)').remove();
        
        // Always keep the New Chat item at the top
        if (!this.conversationList.find('.new-chat-item').length) {
            const $newChatItem = $(`
                <div class="conversation-item new-chat-item">
                    <div class="conversation-title"><i class="fa fa-plus"></i> New Chat</div>
                </div>
            `);
            
            $newChatItem.on('click', function() {
                me.startNewConversation();
            });
            
            this.conversationList.prepend($newChatItem);
            this.newChatItem = $newChatItem;
        }
        
        if (this.conversations.length === 0) {
            this.conversationList.append(
                `<div class="empty-conversation-placeholder">No previous conversations</div>`
            );
            return;
        }
        
        // Sort conversations by date (newest first)
        this.conversations.sort((a, b) => {
            return new Date(b.last_updated) - new Date(a.last_updated);
        });
        
        // Create element for each conversation
        this.conversations.forEach(conv => {
            const formattedDate = frappe.datetime.prettyDate(conv.last_updated);
            const title = conv.title || 'Conversation ' + frappe.datetime.str_to_user(conv.creation).slice(0, 10);
            
            const $item = $(`
                <div class="conversation-item" data-conversation-id="${conv.name}">
                    <div class="conversation-title">${frappe.utils.escape_html(title)}</div>
                    <div class="conversation-date">${formattedDate}</div>
                </div>
            `);
            
            // Mark current conversation as active
            if (conv.name === me.currentConversationId) {
                $item.addClass('active');
            }
            
            // Click handler
            $item.on('click', function() {
                const convId = $(this).data('conversation-id');
                me.loadConversation(convId);
                
                // Update active state
                me.conversationList.find('.conversation-item').removeClass('active');
                $(this).addClass('active');
            });
            
            // Insert after the new chat item
            this.newChatItem.after($item);
        });
    }
    
    startNewConversation() {
        // Clear chat UI
        this.messagesContainer.empty();
        this.messages = [];
        
        // Reset the conversation ID - a new one will be created when sending the first message
        this.currentConversationId = null;
        
        // Mark all conversation items as inactive
        this.conversationList.find('.conversation-item').removeClass('active');
        
        // Mark the new chat item as active to indicate we're in a new conversation
        this.newChatItem.addClass('active');
        
        // Add welcome message
        this.addBotMessage("Hello! I'm your Growth Assistant. You can ask me questions about ERP features or your data. Try typing `/` to access specific documents.", false, false);
        
        // Focus on the input
        this.chatInput.focus();
    }

    loadConversation(conversationId) {
        const me = this;
        
        // Show loading indicator
        me.chatDialog.addClass('loading-conversation');
        
        me.messagesContainer.html('<div class="text-center p-4">Loading conversation...</div>');

        // Call API to get conversation messages
        frappe.call({
            method: 'gs_chat.controllers.chat.get_conversation_messages',
            args: {
                conversation_id: conversationId
            },
            callback: (r) => {
                if (r.message && r.message.success) {
                    // Clear current messages
                    me.messagesContainer.empty();
                    me.messages = [];
                    
                    // Set current conversation ID
                    me.currentConversationId = conversationId;
                    
                    // Load messages
                    const messages = r.message.messages || [];
                    
                    if (messages.length === 0) {
                        me.addBotMessage("This conversation is empty. You can start by asking a question.");
                    } else {
                        // Add each message to UI
                        messages.forEach(msg => {
                            if (msg.message_type === 'user') {
                                me.addUserMessage(msg.content, false);
                            } else if (msg.message_type === 'bot') {
                                me.addBotMessage(msg.content, msg.is_error, false);
                            }
                        });
                    }
                    
                    // Scroll to bottom
                    me.scrollToBottom();

                    setTimeout(() => {
                        me.chatDialog.removeClass('loading-conversation');
                    }, 50);
                } else {
                    console.error("Failed to load conversation:", r.message);
                    me.messagesContainer.html(
                        '<div class="text-center p-4 text-danger">Failed to load conversation</div>'
                    );

                    me.chatDialog.removeClass('loading-conversation');
                }
            }
        });
    }

    closeChat() {
        if (this.chatDialog) {
            this.chatDialog.removeClass("open");
        }
        this.isOpen = false;
    }

    minimizeChat() {
        this.chatDialog.toggleClass("minimized");
    }

    getQueryText() {
        // Get all text nodes and combine them with proper line breaks
        const textParts = [];
        const collectTextFromNode = (node) => {
            if (node.nodeType === Node.TEXT_NODE) {
                textParts.push(node.textContent);
            } else if (node.nodeType === Node.ELEMENT_NODE) {
                // For entity selector spans, use their text content
                if (node.classList.contains('entity-selector')) {
                    const doctype = node.getAttribute('data-doctype');
                    const document = node.getAttribute('data-document');
                    if (doctype && document) {
                        textParts.push(`/${doctype}/${document}`);
                    }
                } 
                // For line breaks, add a newline character
                else if (node.tagName === 'BR') {
                    textParts.push('\n');
                } 
                // For paragraphs or divs, add a newline after their content
                else if (node.tagName === 'P' || node.tagName === 'DIV') {
                    // Recursively process children
                    Array.from(node.childNodes).forEach(child => {
                        collectTextFromNode(child);
                    });
                    // Add a newline unless this is the last paragraph
                    if (node.nextSibling) {
                        textParts.push('\n');
                    }
                } 
                // Process other elements recursively
                else {
                    Array.from(node.childNodes).forEach(child => {
                        collectTextFromNode(child);
                    });
                }
            }
        };

        // Start collecting from all direct children of the chat input
        Array.from(this.chatInput[0].childNodes).forEach(node => {
            collectTextFromNode(node);
        });

        // Join all text parts into a single string
        return textParts.join('');
    }

    sendMessage() {
        // Get all text from the contenteditable div
        const query = this.getQueryText().trim();

        if (!query) {
            return;
        }

        const references = this.slashCommands.getEntityReferences();

        // Add user message to chat
        this.addUserMessage(query, false); // Don't save to server yet
        
        // Clear input - for contenteditable
        this.chatInput.html('');

        // Show typing indicator
        this.showTypingIndicator();
        
        // If this is potentially a new conversation, update the UI accordingly
        let $pendingItem = null;
        if (!this.currentConversationId) {
            // We need to visually indicate a new conversation is being created
            // Create a temporary pending conversation UI element
            $pendingItem = $(`
                <div class="conversation-item active" data-conversation-id="pending">
                    <div class="conversation-title"><i class="fa fa-circle-o-notch fa-spin"></i> ${query.substring(0, 20)}${query.length > 20 ? '...' : ''}</div>
                </div>
            `);
            
            // Insert after the new chat button and mark new chat item as inactive
            this.newChatItem.removeClass('active').after($pendingItem);
        }
        
        // Send to server with a single endpoint that handles both new and existing conversations
        frappe.call({
            method: 'gs_chat.controllers.chat.process_message',
            args: {
                query: query,
                references: references,
                conversation_id: this.currentConversationId || null
            },
            callback: (r) => {
                // Hide typing indicator
                this.hideTypingIndicator();
                
                if (r.message && r.message.success) {
                    // If a new conversation was created, update the ID
                    if (r.message.conversation_id != this.currentConversationId) {
                        this.currentConversationId = r.message.conversation_id;

                        // Remove the pending item (will be replaced during refresh)
                        if ($pendingItem) {
                            $pendingItem.remove();
                        }
                        
                        // Refresh conversation list to show the new one
                        this.fetchConversations();
                    }
                    
                    // Add bot response
                    const messageEl = this.addBotMessage(r.message.response, false, false); // Already saved on server
                    
                    // Add feedback buttons
                    this.addFeedbackButtons(messageEl, r.message.response);
                    
                    // Scroll to bottom
                    this.scrollToBottom();
                } else {
                    // Show error message
                    this.addBotMessage(
                        r.message && r.message.error 
                            ? r.message.error 
                            : "Sorry, I encountered an error. Please try again.",
                        true,
                        false
                    );
                    
                    // If this was a new conversation attempt, clean up
                    if (!this.currentConversationId && $pendingItem) {
                        $pendingItem.remove();
                        this.newChatItem.addClass('active');
                    }
                }
            },
            error: () => {
                // Hide typing indicator
                this.hideTypingIndicator();
                
                // Show error message
                this.addBotMessage(
                    "Sorry, I couldn't connect to the server. Please check your connection and try again.",
                    true,
                    false
                );
                
                // If this was a new conversation attempt, clean up
                if (!this.currentConversationId && $pendingItem) {
                    $pendingItem.remove();
                    this.newChatItem.addClass('active');
                }
            }
        });
    }

    addUserMessage(content, saveToServer = true) {
        const messageEl = $(`
            <div class="chat-message user-message">
                <div class="chat-bubble">
                    ${frappe.markdown(content)}
                </div>
            </div>
        `);
        
        this.messagesContainer.append(messageEl);
        this.scrollToBottom();
        
        // Add to messages array
        this.messages.push({
            type: 'user',
            content: content
        });
        
        // Save to server if needed and we have a conversation ID
        if (saveToServer && this.currentConversationId) {
            frappe.call({
                method: 'gs_chat.controllers.chat.save_message',
                args: {
                    conversation_id: this.currentConversationId,
                    message_type: 'user',
                    content: content
                },
                callback: (r) => {
                    if (!r.message || !r.message.success) {
                        console.error("Failed to save user message:", r.message);
                    }
                }
            });
        }
    }

    addBotMessage(content, isError = false, saveToServer = true) {
        const errorClass = isError ? 'error' : '';
        
        const messageEl = $(`
            <div class="chat-message bot-message">
                <div class="chat-bubble ${errorClass}">
                    ${frappe.markdown(content)}
                </div>
            </div>
        `);
        
        this.messagesContainer.append(messageEl);
        
        // Add to messages array
        this.messages.push({
            type: 'bot',
            content: content,
            isError: isError
        });
        
        // Save to server if needed and we have a conversation ID
        if (saveToServer && this.currentConversationId) {
            frappe.call({
                method: 'gs_chat.controllers.chat.save_message',
                args: {
                    conversation_id: this.currentConversationId,
                    message_type: 'bot',
                    content: content,
                    is_error: isError ? 1 : 0
                },
                callback: (r) => {
                    if (!r.message || !r.message.success) {
                        console.error("Failed to save bot message:", r.message);
                    }
                }
            });
        }
        
        return messageEl;
    }

    addFeedbackButtons(messageEl, response) {
        const feedbackEl = $(`
            <div class="message-feedback">
                <span>${__('Was this helpful?')}</span>
                <button class="btn btn-xs btn-default feedback-button" data-feedback="positive">
                    <i class="fa fa-thumbs-up"></i>
                </button>
                <button class="btn btn-xs btn-default feedback-button" data-feedback="negative">
                    <i class="fa fa-thumbs-down"></i>
                </button>
            </div>
        `);
        
        messageEl.append(feedbackEl);
        
        // Handle feedback clicks
        feedbackEl.find('.feedback-button').on('click', (e) => {
            const feedback = $(e.currentTarget).data('feedback');
            
            if (feedback === 'positive') {
                this.submitFeedback(response, 'Positive');
                feedbackEl.html(`<span class="text-success">${__('Thanks for your feedback!')}</span>`);
            } else {
                this.showFeedbackForm(feedbackEl, response);
            }
        });
    }

    showFeedbackForm(feedbackEl, response) {
        // Use Frappe's dialog
        const dialog = new frappe.ui.Dialog({
            title: __('Provide Feedback'),
            fields: [
                {
                    fieldname: 'feedback_comment',
                    fieldtype: 'Small Text',
                    label: __('What was wrong with this response?'),
                    reqd: true
                }
            ],
            primary_action_label: __('Submit'),
            primary_action: (values) => {
                this.submitFeedback(response, 'Negative', values.feedback_comment);
                feedbackEl.html(`<span class="text-success">${__('Thanks for your feedback!')}</span>`);
                dialog.hide();
            }
        });
        
        dialog.show();
    }

    submitFeedback(response, feedback, comment = null) {
        // Find the interaction ID if available
        // For simplicity, we'll create a unique ID here
        const interactionId = frappe.utils.get_random(10);
        
        frappe.call({
            method: 'erpnext_chatbot.api.llm_interface.provide_feedback',
            args: {
                interaction_id: interactionId,
                feedback: feedback,
                comment: comment
            },
            callback: (r) => {
                if (!r.message || !r.message.success) {
                    console.error("Failed to submit feedback:", r.message);
                }
            }
        });
    }

    resetConversation() {
        frappe.confirm(
            __('This will clear your conversation history. Continue?'),
            () => {
                if (this.currentConversationId) {
                    // Clear chat UI
                    this.messagesContainer.empty();
                    this.messages = [];
                    
                    // Add welcome message
                    this.addBotMessage("Hello! I'm your Growth Assistant. You can ask me questions about ERP features or your data. Try typing `/` to access specific documents.");
    
                    // Reset conversation on server
                    frappe.call({
                        method: 'gs_chat.controllers.chat.reset_conversation',
                        args: {
                            conversation_id: this.currentConversationId
                        },
                        callback: (r) => {
                            if (r.message && r.message.success) {
                                // Refresh conversation list
                                this.fetchConversations();
                            } else {
                                console.error("Failed to reset conversation:", r.message);
                            }
                        }
                    });
                } else {
                    // If no conversation, just start a new one
                    this.startNewConversation();
                }
            }
        );
    }

    fixPlaceholder() {
        const input = this.chatInput;
        
        // Function to check if content is effectively empty
        function isEffectivelyEmpty(element) {
            // Check if there's only whitespace or only <br> elements
            const clone = element.clone();
            clone.find('br').remove();
            return clone.html().trim() === '';
        }

        // Handle input events
        input.on('input focus blur', function() {
            const isEmpty = isEffectivelyEmpty($(this));

            $(this).toggleClass('effectively-empty', isEmpty);
        });
        
        // Initial state
        input.trigger('blur');
    }

    showTypingIndicator() {
        this.typingIndicator.removeClass('d-none');
    }

    hideTypingIndicator() {
        this.typingIndicator.addClass('d-none');
    }

    scrollToBottom() {
        const messagesContainer = this.chatDialog.find('.chatbot-messages')[0];
        if (messagesContainer) {
            messagesContainer.scrollTop = messagesContainer.scrollHeight;
        }
    }

    setupResizeHandle() {
        const me = this;
        let startX, startY, startWidth, startHeight;
        const handle = this.chatDialog.find('.resize-handle');

        handle.on('mousedown', function(e) {
            e.preventDefault();
            
            // Get initial positions
            startX = e.clientX;
            startY = e.clientY;
            startWidth = me.chatDialog.outerWidth();
            startHeight = me.chatDialog.outerHeight();
            
            // Add event listeners for mouse movement and release
            $(document).on('mousemove.chatbot-resize', onMouseMove);
            $(document).on('mouseup.chatbot-resize', onMouseUp);
        });
        
        function onMouseMove(e) {
            // Calculate new dimensions
            const newWidth = startWidth + (startX - e.clientX);
            const newHeight = startHeight + (startY - e.clientY);

            // Apply minimum size constraints
            const width = Math.max(550, newWidth); // Minimum width 550px (increased to accommodate sidebar)
            const height = Math.max(350, newHeight); // Minimum height 350px
            
            // Apply new dimensions
            me.chatDialog.css({
                width: width + 'px',
                height: height + 'px'
            });

            // Store dimensions for persistence (optional)
            if (localStorage) {
                localStorage.setItem('chatbot-width', width);
                localStorage.setItem('chatbot-height', height);
            }
            
        }
        
        function onMouseUp() {
            // Remove event listeners when done resizing
            $(document).off('mousemove.chatbot-resize');
            $(document).off('mouseup.chatbot-resize');

            // Scroll to bottom to keep the view on new messages
            me.scrollToBottom();
        }
    }

    // Add method to load saved dimensions
    loadSavedDimensions() {
        if (localStorage) {
            const width = localStorage.getItem('chatbot-width');
            const height = localStorage.getItem('chatbot-height');
            
            if (width && height) {
                this.chatDialog.css({
                    width: width + 'px',
                    height: height + 'px'
                });
            } else {
                // Set default size if not saved previously (larger to accommodate sidebar)
                this.chatDialog.css({
                    width: '750px',
                    height: '500px'
                });
            }
            
            // Load sidebar state
            const sidebarOpen = localStorage.getItem('chatbot-sidebar-open');
            if (sidebarOpen === '0') {
                this.chatDialog.addClass('sidebar-hidden');
                this.sidebarOpen = false;
            } else {
                this.sidebarOpen = true;
            }
        }
    }
};

$(document).ready(function() {
    frappe.after_ajax(() => {
        if (frappe.session.user == "Administrator")
        gs_chat.instance = new gs_chat.ChatbotWidget();
    });
});