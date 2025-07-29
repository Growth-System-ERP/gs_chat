(() => {
  // ../gs_chat/gs_chat/public/js/slash_commands.js
  var SlashCommandManager = class {
    constructor(chatInput) {
      this.chatInput = chatInput;
      this.isActive = false;
      this.dropdown = null;
      this.currentDoctype = null;
      this.setupEvents();
    }
    setupEvents() {
      const me = this;
      this.chatInput.on("input", function(e) {
        const target = window.getSelection().focusNode;
        const doctypeSelector = $(target).closest(".doctype-selector");
        const documentSelector = $(target).closest(".document-selector");
        if (doctypeSelector.length && me.dropdown) {
          const filterText = doctypeSelector.text().trim().toLowerCase();
          me.filterDropdown(filterText);
        } else if (documentSelector.length && me.dropdown) {
          const filterText = documentSelector.text().trim().toLowerCase();
          me.filterDropdown(filterText);
        }
      });
      this.chatInput.on("keydown", function(e) {
        if (!me.isActive) {
          if (e.key === "/" && !e.shiftKey && !e.ctrlKey) {
            e.preventDefault();
            me.createEntitySelector();
            me.showDoctypeDropdown();
          }
          return;
        }
        switch (e.key) {
          case "Escape":
            e.preventDefault();
            me.hideDropdown();
            me.removeEntitySelector();
            break;
          case "Backspace":
            me.handleBackspace(e);
            break;
          case "ArrowUp":
          case "ArrowDown":
            if (me.dropdown) {
              e.preventDefault();
              me.navigateDropdown(e.key === "ArrowDown" ? "next" : "prev");
            }
            break;
          case "Enter":
            if (me.dropdown) {
              e.preventDefault();
              me.selectActiveItem();
            }
            break;
        }
      });
      $(document).on("click", function(e) {
        if (me.isActive && me.dropdown && !$(e.target).closest(".slash-command-dropdown, .entity-selector").length) {
          me.hideDropdown();
          me.removeEntitySelector();
        }
      });
      $(window).on("resize scroll", () => {
        if (this.isActive && this.dropdown) {
          this.positionDropdown();
        }
      });
    }
    handleBackspace(e) {
      const selection = window.getSelection();
      const node = selection.focusNode;
      const offset = selection.anchorOffset;
      if (node.nodeType === Node.TEXT_NODE && offset === 0) {
        const prevNode = node.previousSibling;
        if (prevNode && $(prevNode).hasClass("entity-selector") && $(prevNode).hasClass("complete-entity")) {
          e.preventDefault();
          const entitySelector = $(prevNode);
          entitySelector.removeClass("complete-entity");
          const documentSelector = entitySelector.find('[contenteditable="false"]').last();
          if (documentSelector.length) {
            documentSelector.attr("contenteditable", "true");
            documentSelector.addClass("document-selector");
            this.focusEntityPart(documentSelector[0]);
            this.currentDoctype = entitySelector.attr("data-doctype");
            this.currentDoctypeSelected = true;
            this.isActive = true;
            this.showDocumentDropdown(this.currentDoctype);
          }
          return;
        }
      }
      const docSelector = $(node).closest(".document-selector");
      if (docSelector.length && docSelector.text().trim() === "") {
        e.preventDefault();
        this.revertToDocTypeSelection(docSelector);
        return;
      }
      const dtSelector = $(node).closest(".doctype-selector");
      if (dtSelector.length && dtSelector.text().trim() === "") {
        e.preventDefault();
        this.removeEntitySelector();
        return;
      }
    }
    revertToDocTypeSelection(docSelector) {
      const entitySelector = docSelector.closest(".entity-selector");
      entitySelector.find(".document-selector").remove();
      entitySelector.find(".entity-separator").remove();
      const doctypeSelector = entitySelector.find(".selected-doctype");
      doctypeSelector.attr("contenteditable", "true");
      this.focusEntityPart(doctypeSelector[0]);
      this.hideDropdown();
      this.showDoctypeDropdown();
      this.currentDoctypeSelected = false;
    }
    selectActiveItem() {
      const selectedItem = this.dropdown.find(".dropdown-item.active");
      if (selectedItem.length) {
        const value = selectedItem.data("value");
        const label = selectedItem.text();
        this.selectItem(
          { value, label },
          this.currentDoctypeSelected ? "document" : "doctype"
        );
      }
    }
    createEntitySelector() {
      const selection = window.getSelection();
      if (!selection.rangeCount)
        return;
      const range = selection.getRangeAt(0);
      const entitySelector = $('<span class="entity-selector"></span>');
      const doctypeSelector = $('<span class="entity-part doctype-selector" contenteditable="true" data-placeholder="type..."></span>');
      entitySelector.append(doctypeSelector);
      range.insertNode(entitySelector[0]);
      this.focusEntityPart(doctypeSelector[0]);
      this.isActive = true;
      this.currentDoctypeSelected = false;
    }
    focusEntityPart(element) {
      const range = document.createRange();
      const selection = window.getSelection();
      range.selectNodeContents(element);
      range.collapse(false);
      selection.removeAllRanges();
      selection.addRange(range);
      element.focus();
    }
    removeEntitySelector() {
      this.chatInput.find(".entity-selector").remove();
      this.isActive = false;
    }
    showDoctypeDropdown() {
      const me = this;
      frappe.call({
        method: "gs_chat.controllers.entity_creator.get_doctype_suggestions",
        callback: function(r) {
          if (r.message && r.message.length) {
            me.createDropdown(r.message, "doctype");
          } else {
            me.isActive = false;
            me.removeEntitySelector();
            frappe.show_alert({
              message: __("No accessible doctypes found"),
              indicator: "red"
            });
          }
        }
      });
    }
    createDropdown(items, type) {
      this.hideDropdown();
      this.dropdownItems = items;
      this.dropdown = $('<div class="slash-command-dropdown"></div>');
      const itemsContainer = $('<div class="dropdown-items"></div>');
      items.forEach((item, index) => {
        const itemElement = $(`<div class="dropdown-item" data-value="${item.value}">${item.label}</div>`);
        if (index === 0) {
          itemElement.addClass("active");
        }
        itemElement.on("click", () => {
          this.selectItem(item, type);
        });
        itemsContainer.append(itemElement);
      });
      this.dropdown.append(itemsContainer);
      $("body").append(this.dropdown);
      this.positionDropdown();
    }
    filterDropdown(filterText) {
      if (!this.dropdown || !this.dropdownItems)
        return;
      const itemsContainer = this.dropdown.find(".dropdown-items");
      itemsContainer.empty();
      const filteredItems = this.dropdownItems.filter(
        (item) => item.label.toLowerCase().includes(filterText)
      );
      if (filteredItems.length === 0) {
        itemsContainer.append('<div class="dropdown-item no-results">No matches found</div>');
        return;
      }
      filteredItems.forEach((item, index) => {
        const itemElement = $(`<div class="dropdown-item" data-value="${item.value}">${item.label}</div>`);
        if (index === 0) {
          itemElement.addClass("active");
        }
        itemElement.on("click", () => {
          this.selectItem(item, this.currentDoctypeSelected ? "document" : "doctype");
        });
        itemsContainer.append(itemElement);
      });
    }
    navigateDropdown(direction) {
      if (!this.dropdown)
        return;
      const items = this.dropdown.find(".dropdown-item:not(.no-results)");
      const activeItem = this.dropdown.find(".dropdown-item.active");
      const currentIndex = items.index(activeItem);
      let newIndex;
      if (direction === "next") {
        newIndex = (currentIndex + 1) % items.length;
      } else {
        newIndex = (currentIndex - 1 + items.length) % items.length;
      }
      activeItem.removeClass("active");
      items.eq(newIndex).addClass("active");
      this.scrollToItem(items.eq(newIndex));
    }
    positionDropdown() {
      if (!this.dropdown)
        return;
      const entitySelector = this.chatInput.find(".entity-selector");
      if (!entitySelector.length) {
        this.hideDropdown();
        return;
      }
      const position = entitySelector.offset();
      const entityHeight = entitySelector.outerHeight();
      const dropdownHeight = this.dropdown.outerHeight();
      const windowHeight = $(window).height();
      const spaceBelow = windowHeight - (position.top - window.scrollY + entityHeight);
      const spaceAbove = position.top - window.scrollY;
      const showAbove = dropdownHeight > spaceBelow && spaceAbove > spaceBelow;
      if (showAbove) {
        this.dropdown.css({
          position: "fixed",
          bottom: windowHeight - position.top + 5,
          left: position.left,
          top: "auto",
          zIndex: 9999
        });
      } else {
        this.dropdown.css({
          position: "fixed",
          top: position.top + entityHeight + 5,
          left: position.left,
          bottom: "auto",
          zIndex: 9999
        });
      }
    }
    scrollToItem(item) {
      const container = item.parent();
      const containerHeight = container.height();
      const itemTop = item.position().top;
      const itemHeight = item.outerHeight();
      if (itemTop < 0) {
        container.scrollTop(container.scrollTop() + itemTop);
      } else if (itemTop + itemHeight > containerHeight) {
        container.scrollTop(container.scrollTop() + itemTop + itemHeight - containerHeight);
      }
    }
    selectItem(item, type) {
      if (type === "doctype") {
        this.currentDoctype = item.value;
        this.currentDoctypeSelected = true;
        const entitySelector = this.chatInput.find(".entity-selector");
        const doctypeSelector = entitySelector.find(".doctype-selector");
        doctypeSelector.text(item.label);
        doctypeSelector.attr("contenteditable", "false");
        entitySelector.append('<span class="entity-separator">/</span>');
        const documentSelector = $('<span class="entity-part document-selector" contenteditable="true" data-placeholder="type..."></span>');
        entitySelector.append(documentSelector);
        this.focusEntityPart(documentSelector[0]);
        documentSelector.on("input", () => {
          if (this.dropdown) {
            const filterText = documentSelector.text().trim().toLowerCase();
            this.filterDropdown(filterText);
          }
        });
        this.hideDropdown();
        this.showDocumentDropdown(item.value);
      } else {
        const entitySelector = this.chatInput.find(".entity-selector");
        const documentSelector = entitySelector.find(".document-selector");
        documentSelector.text(item.label);
        documentSelector.attr("contenteditable", "false");
        entitySelector.attr("data-doctype", this.currentDoctype);
        entitySelector.attr("data-document", item.value);
        entitySelector.addClass("complete-entity");
        this.hideDropdown();
        this.isActive = false;
        const spaceNode = document.createTextNode("\xA0");
        entitySelector.after(spaceNode);
        const selection = window.getSelection();
        const range = document.createRange();
        range.setStartAfter(spaceNode);
        range.setEndAfter(spaceNode);
        selection.removeAllRanges();
        selection.addRange(range);
        this.chatInput.focus();
      }
    }
    showDocumentDropdown(doctype) {
      const me = this;
      frappe.call({
        method: "gs_chat.controllers.entity_creator.get_document_suggestions",
        args: {
          doctype,
          partial_input: ""
        },
        callback: function(r) {
          if (r.message && r.message.length) {
            me.createDropdown(r.message, "document");
          } else {
            me.isActive = false;
            frappe.show_alert({
              message: __("No documents found for {0}", [doctype]),
              indicator: "orange"
            });
          }
        }
      });
    }
    hideDropdown() {
      if (this.dropdown) {
        this.dropdown.remove();
        this.dropdown = null;
      }
    }
    getEntityReferences() {
      const references = [];
      this.chatInput.find(".entity-selector").each(function() {
        const doctype = $(this).attr("data-doctype");
        const document2 = $(this).attr("data-document");
        if (doctype && document2) {
          references.push({
            doctype,
            document: document2
          });
        }
      });
      return references;
    }
  };

  // ../gs_chat/gs_chat/public/js/voice_input.js
  var VoiceInputManager = class {
    constructor(chatInput, onResult) {
      this.chatInput = chatInput;
      this.onResult = onResult;
      this.recognition = null;
      this.isListening = false;
      this.supportedLanguages = {
        "en-US": "English (US)",
        "en-GB": "English (UK)",
        "es-ES": "Spanish",
        "fr-FR": "French",
        "de-DE": "German",
        "it-IT": "Italian",
        "pt-BR": "Portuguese (Brazil)",
        "zh-CN": "Chinese (Mandarin)",
        "ja-JP": "Japanese",
        "ko-KR": "Korean",
        "hi-IN": "Hindi",
        "ar-SA": "Arabic",
        "ru-RU": "Russian"
      };
      this.currentLanguage = "en-US";
      this.initializeSpeechRecognition();
    }
    initializeSpeechRecognition() {
      const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
      if (!SpeechRecognition) {
        console.warn("Speech recognition not supported");
        return false;
      }
      this.recognition = new SpeechRecognition();
      this.recognition.continuous = false;
      this.recognition.interimResults = true;
      this.recognition.maxAlternatives = 1;
      this.recognition.lang = this.currentLanguage;
      this.recognition.onstart = () => {
        this.isListening = true;
        this.updateUI(true);
      };
      this.recognition.onend = () => {
        this.isListening = false;
        this.updateUI(false);
      };
      this.recognition.onresult = (event) => {
        let finalTranscript = "";
        let interimTranscript = "";
        for (let i = event.resultIndex; i < event.results.length; i++) {
          const transcript = event.results[i][0].transcript;
          if (event.results[i].isFinal) {
            finalTranscript += transcript + " ";
          } else {
            interimTranscript += transcript;
          }
        }
        if (interimTranscript) {
          this.showInterimResult(interimTranscript);
        }
        if (finalTranscript) {
          this.processFinalResult(finalTranscript.trim());
        }
      };
      this.recognition.onerror = (event) => {
        console.log(event);
        console.error("Speech recognition error:", event.error);
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
          message: __("Speech recognition not supported in your browser"),
          indicator: "red"
        });
        return;
      }
      navigator.mediaDevices.getUserMedia({ audio: true }).then(() => {
        this.recognition.lang = this.currentLanguage;
        this.recognition.start();
      }).catch((err) => {
        frappe.show_alert({
          message: __("Microphone access denied"),
          indicator: "red"
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
        localStorage.setItem("chatbot-voice-language", langCode);
      }
    }
    showInterimResult(text) {
      const existingInterim = this.chatInput.find(".voice-interim");
      if (existingInterim.length) {
        existingInterim.text(text);
      } else {
        this.chatInput.append(`<span class="voice-interim">${text}</span>`);
      }
    }
    processFinalResult(text) {
      this.chatInput.find(".voice-interim").remove();
      const currentText = this.chatInput.text().trim();
      const newText = currentText ? currentText + " " + text : text;
      this.chatInput.text(newText);
      this.moveCursorToEnd();
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
        "no-speech": __("No speech detected. Please try again."),
        "audio-capture": __("No microphone found."),
        "not-allowed": __("Microphone permission denied."),
        "network": __("Network error. Please check your connection.")
      };
      frappe.show_alert({
        message: errorMessages[error] || __("Speech recognition error: ") + error,
        indicator: "red"
      });
    }
    updateUI(isListening) {
      const voiceButton = $(".voice-input-button");
      if (isListening) {
        voiceButton.addClass("listening");
        voiceButton.find("i").removeClass("fa-microphone").addClass("fa-microphone-slash");
      } else {
        voiceButton.removeClass("listening");
        voiceButton.find("i").removeClass("fa-microphone-slash").addClass("fa-microphone");
      }
    }
    createUI() {
      const voiceButton = $(`
            <button class="btn btn-sm voice-input-button" title="${__("Voice Input")}">
                <i class="fa fa-microphone"></i>
            </button>
        `);
      const langSelector = $(`
            <select class="voice-language-selector" title="${__("Select Language")}">
                ${Object.entries(this.supportedLanguages).map(
        ([code, name]) => `<option value="${code}" ${code === this.currentLanguage ? "selected" : ""}>${name}</option>`
      ).join("")}
            </select>
        `);
      voiceButton.on("click", () => this.toggle());
      langSelector.on("change", (e) => this.setLanguage(e.target.value));
      const savedLang = localStorage.getItem("chatbot-voice-language");
      if (savedLang && this.supportedLanguages[savedLang]) {
        this.currentLanguage = savedLang;
        langSelector.val(savedLang);
      }
      return { voiceButton, langSelector };
    }
  };

  // ../gs_chat/gs_chat/public/js/gs_chat.bundle.js
  frappe.provide("gs_chat");
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
      this.autoSendAfterVoice = localStorage.getItem("chatbot-auto-send-voice") === "true";
      this.voiceShortcutEnabled = localStorage.getItem("chatbot-voice-shortcut") !== "false";
    }
    setupIcon() {
      const $chatbotIcon = $(`
            <li class="nav-item dropdown dropdown-notifications dropdown-mobile chatbot-icon-open">
                <a class="nav-link" data-toggle="dropdown" aria-expanded="false" 
                   title="Growth Assistant" href="#" onclick="return false;">
                    ${frappe.utils.icon("chatbot")}
                </a>
            </li>
        `);
      $(".dropdown-help").before($chatbotIcon);
      $chatbotIcon.on("click", () => {
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
      if (!this.chatDialog) {
        this.createDialog();
        this.setupResizeHandle();
        this.loadSavedDimensions();
        this.setupEvents();
        this.renderConversationList();
        this.slashCommands = new SlashCommandManager(this.chatInput);
      }
      this.chatDialog.addClass("open");
      this.chatDialog.removeClass("minimized");
      this.isOpen = true;
      this.chatInput.focus();
      if (this.messages.length === 0 && !this.currentConversationId) {
        this.startNewConversation();
      }
      $(document).trigger("growth_chatbot_loaded");
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
                        <div class="voice-controls">
                            <select class="voice-language-selector" title="${__("Select Language")}">
                                <option value="en-US">English (US)</option>
                                <option value="es-ES">Spanish</option>
                                <option value="fr-FR">French</option>
                                <option value="de-DE">German</option>
                                <option value="zh-CN">Chinese</option>
                                <option value="hi-IN">Hindi</option>
                                <option value="ar-SA">Arabic</option>
                                <option value="ja-JP">Japanese</option>
                                <option value="ko-KR">Korean</option>
                            </select>
                        </div>
                        <div class="chat-input-container">
                            <span class="chat-input" data-placeholder="Ask anything..." contenteditable="true" enterkeyhint="enter" tabindex="0"></span>
                            <button class="btn btn-sm voice-input-button" title="${__("Voice Input")}">
                                <i class="fa fa-microphone"></i>
                            </button>
                            <button class="btn btn-primary btn-sm send-button">
                                <i class="fa fa-paper-plane"></i>
                            </button>
                        </div>
                    </div>
                </div>
                <div class="resize-handle"></div>
            </div>
            `);
      $("body").append(this.chatDialog);
    }
    setupEvents() {
      const me = this;
      this.chatBody = this.chatDialog.find(".chat-body");
      this.messagesContainer = this.chatDialog.find(".chatbot-messages");
      this.chatInput = this.chatDialog.find(".chat-input");
      this.typingIndicator = this.chatDialog.find(".typing-indicator");
      this.sendButton = this.chatDialog.find(".send-button");
      this.conversationList = this.chatDialog.find(".conversation-list");
      this.newChatItem = this.chatDialog.find(".new-chat-item");
      this.toggleSidebarButton = this.chatDialog.find(".toggle-sidebar-button");
      this.chatInput.on("keydown", function(e) {
        if (e.key === "Enter" && !e.shiftKey && !e.ctrlKey && !e.metaKey && !me.slashCommands.isActive) {
          e.preventDefault();
          me.sendMessage();
          return false;
        }
      });
      this.sendButton.on("click", function() {
        me.sendMessage();
      });
      this.chatDialog.find(".action-button").on("click", function(e) {
        const action = $(e.currentTarget).data("action");
        if (action === "refresh") {
          me.resetConversation();
        } else if (action === "minimize") {
          me.minimizeChat();
        } else if (action === "close") {
          me.closeChat();
        }
      });
      this.newChatItem.on("click", function() {
        me.startNewConversation();
      });
      this.toggleSidebarButton.on("click", function() {
        me.toggleSidebar();
      });
      this.fixPlaceholder();
      this.setupVoiceInput();
      this.setupKeyboardShortcuts();
    }
    toggleSidebar() {
      this.chatDialog.toggleClass("sidebar-hidden");
      this.sidebarOpen = !this.chatDialog.hasClass("sidebar-hidden");
      if (localStorage) {
        localStorage.setItem("chatbot-sidebar-open", this.sidebarOpen ? "1" : "0");
      }
    }
    fetchConversations() {
      const me = this;
      frappe.call({
        method: "gs_chat.controllers.chat.get_conversations",
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
      this.conversationList.find(".conversation-item:not(.new-chat-item)").remove();
      if (!this.conversationList.find(".new-chat-item").length) {
        const $newChatItem = $(`
                <div class="conversation-item new-chat-item">
                    <div class="conversation-title"><i class="fa fa-plus"></i> New Chat</div>
                </div>
            `);
        $newChatItem.on("click", function() {
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
      this.conversations.sort((a, b) => {
        return new Date(b.last_updated) - new Date(a.last_updated);
      });
      this.conversations.forEach((conv) => {
        const formattedDate = frappe.datetime.prettyDate(conv.last_updated);
        const title = conv.title || "Conversation " + frappe.datetime.str_to_user(conv.creation).slice(0, 10);
        const $item = $(`
                <div class="conversation-item" data-conversation-id="${conv.name}">
                    <div class="conversation-title">${frappe.utils.escape_html(title)}</div>
                    <div class="conversation-date">${formattedDate}</div>
                </div>
            `);
        if (conv.name === me.currentConversationId) {
          $item.addClass("active");
        }
        $item.on("click", function() {
          const convId = $(this).data("conversation-id");
          me.loadConversation(convId);
          me.conversationList.find(".conversation-item").removeClass("active");
          $(this).addClass("active");
        });
        this.newChatItem.after($item);
      });
    }
    startNewConversation() {
      this.messagesContainer.empty();
      this.messages = [];
      this.currentConversationId = null;
      this.conversationList.find(".conversation-item").removeClass("active");
      this.newChatItem.addClass("active");
      this.addBotMessage("Hello! I'm your Growth Assistant. You can ask me questions about ERP features or your data. Try typing `/` to access specific documents.", false, false);
      this.chatInput.focus();
    }
    loadConversation(conversationId) {
      const me = this;
      me.chatDialog.addClass("loading-conversation");
      me.messagesContainer.html('<div class="text-center p-4">Loading conversation...</div>');
      frappe.call({
        method: "gs_chat.controllers.chat.get_conversation_messages",
        args: {
          conversation_id: conversationId
        },
        callback: (r) => {
          if (r.message && r.message.success) {
            me.messagesContainer.empty();
            me.messages = [];
            me.currentConversationId = conversationId;
            const messages = r.message.messages || [];
            if (messages.length === 0) {
              me.addBotMessage("This conversation is empty. You can start by asking a question.");
            } else {
              messages.forEach((msg) => {
                if (msg.message_type === "user") {
                  me.addUserMessage(msg.content, false);
                } else if (msg.message_type === "bot") {
                  me.addBotMessage(msg.content, msg.is_error, false);
                }
              });
            }
            me.scrollToBottom();
            setTimeout(() => {
              me.chatDialog.removeClass("loading-conversation");
            }, 50);
          } else {
            console.error("Failed to load conversation:", r.message);
            me.messagesContainer.html(
              '<div class="text-center p-4 text-danger">Failed to load conversation</div>'
            );
            me.chatDialog.removeClass("loading-conversation");
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
      const textParts = [];
      const collectTextFromNode = (node) => {
        if (node.nodeType === Node.TEXT_NODE) {
          textParts.push(node.textContent);
        } else if (node.nodeType === Node.ELEMENT_NODE) {
          if (node.classList.contains("entity-selector")) {
            const doctype = node.getAttribute("data-doctype");
            const document2 = node.getAttribute("data-document");
            if (doctype && document2) {
              textParts.push(`/${doctype}/${document2}`);
            }
          } else if (node.tagName === "BR") {
            textParts.push("\n");
          } else if (node.tagName === "P" || node.tagName === "DIV") {
            Array.from(node.childNodes).forEach((child) => {
              collectTextFromNode(child);
            });
            if (node.nextSibling) {
              textParts.push("\n");
            }
          } else {
            Array.from(node.childNodes).forEach((child) => {
              collectTextFromNode(child);
            });
          }
        }
      };
      Array.from(this.chatInput[0].childNodes).forEach((node) => {
        collectTextFromNode(node);
      });
      return textParts.join("");
    }
    sendMessage() {
      const query = this.getQueryText().trim();
      if (!query) {
        return;
      }
      const references = this.slashCommands.getEntityReferences();
      this.addUserMessage(query, false);
      this.chatInput.html("");
      this.showTypingIndicator();
      let $pendingItem = null;
      if (!this.currentConversationId) {
        $pendingItem = $(`
                <div class="conversation-item active" data-conversation-id="pending">
                    <div class="conversation-title"><i class="fa fa-circle-o-notch fa-spin"></i> ${query.substring(0, 20)}${query.length > 20 ? "..." : ""}</div>
                </div>
            `);
        this.newChatItem.removeClass("active").after($pendingItem);
      }
      frappe.call({
        method: "gs_chat.controllers.chat.process_message",
        args: {
          query,
          references,
          conversation_id: this.currentConversationId || null
        },
        callback: (r) => {
          this.hideTypingIndicator();
          if (r.message && r.message.success) {
            if (r.message.conversation_id != this.currentConversationId) {
              this.currentConversationId = r.message.conversation_id;
              if ($pendingItem) {
                $pendingItem.remove();
              }
              this.fetchConversations();
            }
            const messageEl = this.addBotMessage(r.message.response, false, false);
            this.addFeedbackButtons(messageEl, r.message.response);
            this.scrollToBottom();
          } else {
            this.addBotMessage(
              r.message && r.message.error ? r.message.error : "Sorry, I encountered an error. Please try again.",
              true,
              false
            );
            if (!this.currentConversationId && $pendingItem) {
              $pendingItem.remove();
              this.newChatItem.addClass("active");
            }
          }
        },
        error: () => {
          this.hideTypingIndicator();
          this.addBotMessage(
            "Sorry, I couldn't connect to the server. Please check your connection and try again.",
            true,
            false
          );
          if (!this.currentConversationId && $pendingItem) {
            $pendingItem.remove();
            this.newChatItem.addClass("active");
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
      this.messages.push({
        type: "user",
        content
      });
      if (saveToServer && this.currentConversationId) {
        frappe.call({
          method: "gs_chat.controllers.chat.save_message",
          args: {
            conversation_id: this.currentConversationId,
            message_type: "user",
            content
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
      const errorClass = isError ? "error" : "";
      const messageEl = $(`
            <div class="chat-message bot-message">
                <div class="chat-bubble ${errorClass}">
                    ${frappe.markdown(content)}
                </div>
            </div>
        `);
      this.messagesContainer.append(messageEl);
      this.messages.push({
        type: "bot",
        content,
        isError
      });
      if (saveToServer && this.currentConversationId) {
        frappe.call({
          method: "gs_chat.controllers.chat.save_message",
          args: {
            conversation_id: this.currentConversationId,
            message_type: "bot",
            content,
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
                <span>${__("Was this helpful?")}</span>
                <button class="btn btn-xs btn-default feedback-button" data-feedback="positive">
                    <i class="fa fa-thumbs-up"></i>
                </button>
                <button class="btn btn-xs btn-default feedback-button" data-feedback="negative">
                    <i class="fa fa-thumbs-down"></i>
                </button>
            </div>
        `);
      messageEl.append(feedbackEl);
      feedbackEl.find(".feedback-button").on("click", (e) => {
        const feedback = $(e.currentTarget).data("feedback");
        if (feedback === "positive") {
          this.submitFeedback(response, "Positive");
          feedbackEl.html(`<span class="text-success">${__("Thanks for your feedback!")}</span>`);
        } else {
          this.showFeedbackForm(feedbackEl, response);
        }
      });
    }
    showFeedbackForm(feedbackEl, response) {
      const dialog = new frappe.ui.Dialog({
        title: __("Provide Feedback"),
        fields: [
          {
            fieldname: "feedback_comment",
            fieldtype: "Small Text",
            label: __("What was wrong with this response?"),
            reqd: true
          }
        ],
        primary_action_label: __("Submit"),
        primary_action: (values) => {
          this.submitFeedback(response, "Negative", values.feedback_comment);
          feedbackEl.html(`<span class="text-success">${__("Thanks for your feedback!")}</span>`);
          dialog.hide();
        }
      });
      dialog.show();
    }
    submitFeedback(response, feedback, comment = null) {
      const interactionId = frappe.utils.get_random(10);
      frappe.call({
        method: "erpnext_chatbot.api.llm_interface.provide_feedback",
        args: {
          interaction_id: interactionId,
          feedback,
          comment
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
        __("This will clear your conversation history. Continue?"),
        () => {
          if (this.currentConversationId) {
            this.messagesContainer.empty();
            this.messages = [];
            this.addBotMessage("Hello! I'm your Growth Assistant. You can ask me questions about ERP features or your data. Try typing `/` to access specific documents.");
            frappe.call({
              method: "gs_chat.controllers.chat.reset_conversation",
              args: {
                conversation_id: this.currentConversationId
              },
              callback: (r) => {
                if (r.message && r.message.success) {
                  this.fetchConversations();
                } else {
                  console.error("Failed to reset conversation:", r.message);
                }
              }
            });
          } else {
            this.startNewConversation();
          }
        }
      );
    }
    fixPlaceholder() {
      const input = this.chatInput;
      function isEffectivelyEmpty(element) {
        const clone = element.clone();
        clone.find("br").remove();
        return clone.html().trim() === "";
      }
      input.on("input focus blur", function() {
        const isEmpty = isEffectivelyEmpty($(this));
        $(this).toggleClass("effectively-empty", isEmpty);
      });
      input.trigger("blur");
    }
    showTypingIndicator() {
      this.typingIndicator.removeClass("d-none");
    }
    hideTypingIndicator() {
      this.typingIndicator.addClass("d-none");
    }
    scrollToBottom() {
      const messagesContainer = this.chatDialog.find(".chatbot-messages")[0];
      if (messagesContainer) {
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
      }
    }
    setupResizeHandle() {
      const me = this;
      let startX, startY, startWidth, startHeight;
      const handle = this.chatDialog.find(".resize-handle");
      handle.on("mousedown", function(e) {
        e.preventDefault();
        startX = e.clientX;
        startY = e.clientY;
        startWidth = me.chatDialog.outerWidth();
        startHeight = me.chatDialog.outerHeight();
        $(document).on("mousemove.chatbot-resize", onMouseMove);
        $(document).on("mouseup.chatbot-resize", onMouseUp);
      });
      function onMouseMove(e) {
        const newWidth = startWidth + (startX - e.clientX);
        const newHeight = startHeight + (startY - e.clientY);
        const width = Math.max(550, newWidth);
        const height = Math.max(350, newHeight);
        me.chatDialog.css({
          width: width + "px",
          height: height + "px"
        });
        if (localStorage) {
          localStorage.setItem("chatbot-width", width);
          localStorage.setItem("chatbot-height", height);
        }
      }
      function onMouseUp() {
        $(document).off("mousemove.chatbot-resize");
        $(document).off("mouseup.chatbot-resize");
        me.scrollToBottom();
      }
    }
    loadSavedDimensions() {
      if (localStorage) {
        const width = localStorage.getItem("chatbot-width");
        const height = localStorage.getItem("chatbot-height");
        if (width && height) {
          this.chatDialog.css({
            width: width + "px",
            height: height + "px"
          });
        } else {
          this.chatDialog.css({
            width: "750px",
            height: "500px"
          });
        }
        const sidebarOpen = localStorage.getItem("chatbot-sidebar-open");
        if (sidebarOpen === "0") {
          this.chatDialog.addClass("sidebar-hidden");
          this.sidebarOpen = false;
        } else {
          this.sidebarOpen = true;
        }
      }
    }
    setupVoiceInput() {
      const me = this;
      this.voiceManager = new VoiceInputManager(
        this.chatInput,
        (text) => {
          if (me.autoSendAfterVoice) {
            setTimeout(() => me.sendMessage(), 500);
          }
        }
      );
      const voiceButton = this.chatDialog.find(".voice-input-button");
      const langSelector = this.chatDialog.find(".voice-language-selector");
      voiceButton.on("click", () => {
        me.voiceManager.toggle();
      });
      langSelector.on("change", (e) => {
        me.voiceManager.setLanguage(e.target.value);
      });
      const savedLang = localStorage.getItem("chatbot-voice-language");
      if (savedLang) {
        langSelector.val(savedLang);
        me.voiceManager.setLanguage(savedLang);
      }
      this.voiceManager.updateUI = (isListening) => {
        if (isListening) {
          voiceButton.addClass("listening");
          voiceButton.find("i").removeClass("fa-microphone").addClass("fa-microphone-slash");
          me.chatInput.addClass("voice-active");
        } else {
          voiceButton.removeClass("listening");
          voiceButton.find("i").removeClass("fa-microphone-slash").addClass("fa-microphone");
          me.chatInput.removeClass("voice-active");
        }
      };
      this.voiceManager.showInterimResult = (text) => {
        const existingInterim = me.chatInput.find(".voice-interim");
        if (existingInterim.length) {
          existingInterim.text(text);
        } else {
          me.chatInput.append(`<span class="voice-interim">${text}</span>`);
        }
      };
      this.voiceManager.processFinalResult = (text) => {
        me.chatInput.find(".voice-interim").remove();
        const currentText = me.getQueryText().trim();
        if (currentText) {
          me.chatInput.append(document.createTextNode(" " + text));
        } else {
          me.chatInput.text(text);
        }
        me.voiceManager.moveCursorToEnd();
        me.chatInput.trigger("input");
      };
    }
    toggleAutoSendVoice() {
      this.autoSendAfterVoice = !this.autoSendAfterVoice;
      localStorage.setItem("chatbot-auto-send-voice", this.autoSendAfterVoice);
      frappe.show_alert({
        message: this.autoSendAfterVoice ? __("Auto-send after voice input enabled") : __("Auto-send after voice input disabled"),
        indicator: "blue"
      });
    }
    setupKeyboardShortcuts() {
      const me = this;
      $(document).on("keydown", function(e) {
        if (me.isOpen && me.voiceShortcutEnabled) {
          if (e.ctrlKey && e.shiftKey && e.key === "V") {
            e.preventDefault();
            if (me.voiceManager) {
              me.voiceManager.toggle();
            }
          }
        }
      });
      this.chatInput.on("keydown", function(e) {
        if (e.key === "Escape" && me.voiceManager && me.voiceManager.isListening) {
          e.preventDefault();
          me.voiceManager.stop();
        }
      });
    }
    createVoiceSettingsMenu() {
      const settingsButton = $(`
        <button class="btn btn-xs voice-settings-btn" title="${__("Voice Settings")}">
        <i class="fa fa-cog"></i>
        </button>
        `);
      settingsButton.on("click", () => {
        this.showVoiceSettings();
      });
      return settingsButton;
    }
    showVoiceSettings() {
      const dialog = new frappe.ui.Dialog({
        title: __("Voice Input Settings"),
        fields: [
          {
            fieldname: "auto_send",
            fieldtype: "Check",
            label: __("Auto-send after voice input"),
            default: this.autoSendAfterVoice ? 1 : 0
          },
          {
            fieldname: "keyboard_shortcut",
            fieldtype: "Check",
            label: __("Enable keyboard shortcut (Ctrl+Shift+V)"),
            default: this.voiceShortcutEnabled ? 1 : 0
          },
          {
            fieldname: "continuous_mode",
            fieldtype: "Check",
            label: __("Continuous listening mode"),
            default: 0,
            description: __("Keep listening after each phrase")
          }
        ],
        primary_action_label: __("Save"),
        primary_action: (values) => {
          this.autoSendAfterVoice = values.auto_send;
          this.voiceShortcutEnabled = values.keyboard_shortcut;
          localStorage.setItem("chatbot-auto-send-voice", values.auto_send);
          localStorage.setItem("chatbot-voice-shortcut", values.keyboard_shortcut);
          if (this.voiceManager) {
            this.voiceManager.recognition.continuous = values.continuous_mode;
          }
          dialog.hide();
          frappe.show_alert({
            message: __("Voice settings saved"),
            indicator: "green"
          });
        }
      });
      dialog.show();
    }
  };
  $(document).ready(function() {
    frappe.after_ajax(() => {
      if (frappe.session.user == "Administrator")
        gs_chat.instance = new gs_chat.ChatbotWidget();
    });
  });
})();
//# sourceMappingURL=gs_chat.bundle.2XM5KP6T.js.map
