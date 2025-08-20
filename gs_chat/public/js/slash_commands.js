// slash_commands.js - Entity selector approach

export class SlashCommandManager {
    constructor(chatInput) {
        this.chatInput = chatInput;
        this.isActive = false;
        this.dropdown = null;
        this.currentDoctype = null;
        this.setupEvents();
    }

    setupEvents() {
        const me = this;
        
        // Listen for '/' key to activate entity selection
        this.chatInput.on('input', function(e) {
            const target = window.getSelection().focusNode;
            const doctypeSelector = $(target).closest('.doctype-selector');
            const documentSelector = $(target).closest('.document-selector');

            if (doctypeSelector.length && me.dropdown) {
                const filterText = doctypeSelector.text().trim().toLowerCase();
                me.filterDropdown(filterText);
            } else if (documentSelector.length && me.dropdown) {
                const filterText = documentSelector.text().trim().toLowerCase();
                me.filterDropdown(filterText);
            }
        });

        this.chatInput.on('keydown', function(e) {
            if (!me.isActive) {
                // Only handle slash to activate when not active
                if (e.key === '/' && !e.shiftKey && !e.ctrlKey) {
                    e.preventDefault();
                    me.createEntitySelector();
                    me.showDoctypeDropdown();
                }
                return;
            }
            
            // Handle keys when entity selector is active

            switch (e.key) {
                case 'Escape':
                    e.preventDefault();
                    me.hideDropdown();
                    me.removeEntitySelector();
                    break;
                    
                case 'Backspace':
                    me.handleBackspace(e);
                    break;
                    
                case 'ArrowUp':
                case 'ArrowDown':
                    if (me.dropdown) {
                        e.preventDefault();
                        me.navigateDropdown(e.key === 'ArrowDown' ? 'next' : 'prev');
                    }
                    break;
                    
                case 'Enter':
                    if (me.dropdown) {
                        e.preventDefault();
                        me.selectActiveItem();
                    }
                    break;
            }
        });
        
        // Handle clicks outside the dropdown to close it
        $(document).on('click', function(e) {
            if (me.isActive && me.dropdown && !$(e.target).closest('.slash-command-dropdown, .entity-selector').length) {
                me.hideDropdown();
                me.removeEntitySelector();
            }
        });
        
        // Handle window resize or scroll
        $(window).on('resize scroll', () => {
            if (this.isActive && this.dropdown) {
                this.positionDropdown();
            }
        });
    }

    handleBackspace(e) {
        const selection = window.getSelection();
        const node = selection.focusNode;
        const offset = selection.anchorOffset;
        
        // Check if we're right after a completed entity (cursor at start of text node)
        if (node.nodeType === Node.TEXT_NODE && offset === 0) {
            const prevNode = node.previousSibling;
            
            // If previous node is a completed entity
            if (prevNode && $(prevNode).hasClass('entity-selector') && $(prevNode).hasClass('complete-entity')) {
                e.preventDefault();
                
                // Get the entity selector
                const entitySelector = $(prevNode);
                
                // Remove complete-entity class
                entitySelector.removeClass('complete-entity');
                
                // Find document selector (last editable part that was made non-editable)
                const documentSelector = entitySelector.find('[contenteditable="false"]').last();
                
                if (documentSelector.length) {
                    // Make it editable again
                    documentSelector.attr('contenteditable', 'true');
                    documentSelector.addClass('document-selector');
                    
                    // Focus on it
                    this.focusEntityPart(documentSelector[0]);
                    
                    // Set state for dropdown
                    this.currentDoctype = entitySelector.attr('data-doctype');
                    this.currentDoctypeSelected = true;
                    this.isActive = true;
                    
                    // Show dropdown
                    this.showDocumentDropdown(this.currentDoctype);
                }
                
                return;
            }
        }
        
        // Case: we're inside a document selector and it's empty
        const docSelector = $(node).closest('.document-selector');
        if (docSelector.length && docSelector.text().trim() === '') {
            e.preventDefault();
            this.revertToDocTypeSelection(docSelector);
            return;
        }
        
        // Case: we're inside a doctype selector and it's empty
        const dtSelector = $(node).closest('.doctype-selector');
        if (dtSelector.length && dtSelector.text().trim() === '') {
            e.preventDefault();
            this.removeEntitySelector();
            return;
        }
    }

    revertToDocTypeSelection(docSelector) {
        const entitySelector = docSelector.closest('.entity-selector');
        
        // Remove document part
        entitySelector.find('.document-selector').remove();
        entitySelector.find('.entity-separator').remove();
        
        // Make doctype editable again
        const doctypeSelector = entitySelector.find('.selected-doctype');
        doctypeSelector.attr('contenteditable', 'true');

        // Focus and show dropdown
        this.focusEntityPart(doctypeSelector[0]);
        this.hideDropdown();
        this.showDoctypeDropdown();
        
        // Reset state
        this.currentDoctypeSelected = false;
    }

    selectActiveItem() {
        const selectedItem = this.dropdown.find('.dropdown-item.active');
        if (selectedItem.length) {
            const value = selectedItem.data('value');
            const label = selectedItem.text();
            this.selectItem(
                {value, label}, 
                this.currentDoctypeSelected ? 'document' : 'doctype'
            );
        }
    }
    
    createEntitySelector() {
        // Get cursor position
        const selection = window.getSelection();
        if (!selection.rangeCount) return;

        const range = selection.getRangeAt(0);
        
        // Create entity selector container
        const entitySelector = $('<span class="entity-selector"></span>');
        
        // Create doctype selector
        const doctypeSelector = $('<span class="entity-part doctype-selector" contenteditable="true" data-placeholder="type..."></span>');
        entitySelector.append(doctypeSelector);
        
        // Insert at cursor position
        range.insertNode(entitySelector[0]);
        
        // Focus the doctype selector
        this.focusEntityPart(doctypeSelector[0]);
        
        // Set active state
        this.isActive = true;
        this.currentDoctypeSelected = false;
    }
    
    focusEntityPart(element) {
        // Focus and set cursor at the end of the element
        const range = document.createRange();
        const selection = window.getSelection();
        
        range.selectNodeContents(element);
        range.collapse(false); // collapse to end
        
        selection.removeAllRanges();
        selection.addRange(range);
        
        element.focus();
    }
    
    removeEntitySelector() {
        // Remove the entity selector if present
        this.chatInput.find('.entity-selector').remove();
        this.isActive = false;
    }

    showDoctypeDropdown() {
        const me = this;
        
        // Fetch available doctypes
        frappe.call({
            method: 'gs_chat.controllers.entity_creator.get_doctype_suggestions',
            callback: function(r) {
                if (r.message && r.message.length) {
                    me.createDropdown(r.message, 'doctype');
                } else {
                    me.isActive = false;
                    me.removeEntitySelector();
                    frappe.show_alert({
                        message: __('No accessible doctypes found'),
                        indicator: 'red'
                    });
                }
            }
        });
    }

    createDropdown(items, type) {
        // Remove existing dropdown if any
        this.hideDropdown();
        
        // Store items for filtering
        this.dropdownItems = items;
        
        // Create dropdown container
        this.dropdown = $('<div class="slash-command-dropdown"></div>');
        
        // Add items container
        const itemsContainer = $('<div class="dropdown-items"></div>');
        
        // Add items
        items.forEach((item, index) => {
            const itemElement = $(`<div class="dropdown-item" data-value="${item.value}">${item.label}</div>`);
            
            // Highlight first item
            if (index === 0) {
                itemElement.addClass('active');
            }
            
            // Handle item click
            itemElement.on('click', () => {
                this.selectItem(item, type);
            });
            
            itemsContainer.append(itemElement);
        });
        
        this.dropdown.append(itemsContainer);
        
        // Append to body with fixed positioning
        $('body').append(this.dropdown);
        
        // Position dropdown
        this.positionDropdown();
    }
    
    filterDropdown(filterText) {
        if (!this.dropdown || !this.dropdownItems) return;
        
        const itemsContainer = this.dropdown.find('.dropdown-items');
        itemsContainer.empty();
        
        // Filter items and rebuild list
        const filteredItems = this.dropdownItems.filter(item => 
            item.label.toLowerCase().includes(filterText)
        );
        
        if (filteredItems.length === 0) {
            itemsContainer.append('<div class="dropdown-item no-results">No matches found</div>');
            return;
        }
        
        filteredItems.forEach((item, index) => {
            const itemElement = $(`<div class="dropdown-item" data-value="${item.value}">${item.label}</div>`);
            
            // Highlight first item
            if (index === 0) {
                itemElement.addClass('active');
            }
            
            // Handle item click
            itemElement.on('click', () => {
                this.selectItem(item, this.currentDoctypeSelected ? 'document' : 'doctype');
            });
            
            itemsContainer.append(itemElement);
        });
    }
    
    navigateDropdown(direction) {
        if (!this.dropdown) return;
        
        const items = this.dropdown.find('.dropdown-item:not(.no-results)');
        const activeItem = this.dropdown.find('.dropdown-item.active');
        const currentIndex = items.index(activeItem);
        
        let newIndex;
        if (direction === 'next') {
            newIndex = (currentIndex + 1) % items.length;
        } else {
            newIndex = (currentIndex - 1 + items.length) % items.length;
        }
        
        activeItem.removeClass('active');
        items.eq(newIndex).addClass('active');
        this.scrollToItem(items.eq(newIndex));
    }

    positionDropdown() {
        if (!this.dropdown) return;
        
        // Get position from the current entity selector
        const entitySelector = this.chatInput.find('.entity-selector');
        if (!entitySelector.length) {
            this.hideDropdown();
            return;
        }
        
        const position = entitySelector.offset();
        const entityHeight = entitySelector.outerHeight();
        const dropdownHeight = this.dropdown.outerHeight();
        const windowHeight = $(window).height();
        
        // Calculate available space below and above
        const spaceBelow = windowHeight - (position.top - window.scrollY + entityHeight);
        const spaceAbove = position.top - window.scrollY;
        
        // Decide whether to show above or below
        const showAbove = (dropdownHeight > spaceBelow) && (spaceAbove > spaceBelow);
        
        // Position dropdown
        if (showAbove) {
            this.dropdown.css({
                position: 'fixed',
                bottom: windowHeight - position.top + 5,
                left: position.left,
                top: 'auto',
                zIndex: 9999
            });
        } else {
            this.dropdown.css({
                position: 'fixed',
                top: position.top + entityHeight + 5,
                left: position.left,
                bottom: 'auto',
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
        if (type === 'doctype') {
            // Store current doctype for later
            this.currentDoctype = item.value;
            this.currentDoctypeSelected = true;
            
            // Update the current entity selector with the selected doctype
            const entitySelector = this.chatInput.find('.entity-selector');
            const doctypeSelector = entitySelector.find('.doctype-selector');
            
            // Set doctype text and make it non-editable
            doctypeSelector.text(item.label);
            doctypeSelector.attr('contenteditable', 'false');
            
            // Add slash separator
            entitySelector.append('<span class="entity-separator">/</span>');
            
            // Add document selector
            const documentSelector = $('<span class="entity-part document-selector" contenteditable="true" data-placeholder="type..."></span>');
            entitySelector.append(documentSelector);
            
            // Focus the document selector
            this.focusEntityPart(documentSelector[0]);
            
            // Set up input handling in the document selector
            documentSelector.on('input', () => {
                // Filter the dropdown based on input
                if (this.dropdown) {
                    const filterText = documentSelector.text().trim().toLowerCase();
                    this.filterDropdown(filterText);
                }
            });
            
            // Show document dropdown
            this.hideDropdown();
            this.showDocumentDropdown(item.value);
        } else {
            // Update the current entity selector with the selected document
            const entitySelector = this.chatInput.find('.entity-selector');
            const documentSelector = entitySelector.find('.document-selector');
            
            // Set document text and make it non-editable
            documentSelector.text(item.label);
            documentSelector.attr('contenteditable', 'false');
            
            // Add the doctype and document information as data attributes for later retrieval
            entitySelector.attr('data-doctype', this.currentDoctype);
            entitySelector.attr('data-document', item.value);
            entitySelector.addClass('complete-entity');

            // Hide dropdown and reset state
            this.hideDropdown();
            this.isActive = false;

            const spaceNode = document.createTextNode('\u00A0'); // Non-breaking space
            entitySelector.after(spaceNode);
            
            // Set cursor after entity selector
            const selection = window.getSelection();
            const range = document.createRange();
            range.setStartAfter(spaceNode);
            range.setEndAfter(spaceNode);
            selection.removeAllRanges();
            selection.addRange(range);
            
            // Focus back on main input
            this.chatInput.focus();
        }
    }

    showDocumentDropdown(doctype) {
        const me = this;
        
        // Fetch documents for the selected doctype
        frappe.call({
            method: 'gs_chat.controllers.entity_creator.get_document_suggestions',
            args: {
                doctype: doctype,
                partial_input: ''
            },
            callback: function(r) {
                if (r.message && r.message.length) {
                    me.createDropdown(r.message, 'document');
                } else {
                    me.isActive = false;
                    frappe.show_alert({
                        message: __('No documents found for {0}', [doctype]),
                        indicator: 'orange'
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

    // Method to get all entity references from the input for context creation
    getEntityReferences() {
        const references = [];
        
        this.chatInput.find('.entity-selector').each(function() {
            const doctype = $(this).attr('data-doctype');
            const document = $(this).attr('data-document');
            
            if (doctype && document) {
                references.push({
                    doctype: doctype,
                    document: document
                });
            }
        });
        
        return references;
    }
}