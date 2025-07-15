"""
GS Chat Memory DocType module
"""

import frappe
from frappe.model.document import Document

class GSChatMemory(Document):
    """
    GS Chat Memory document class
    
    Stores conversation history and summaries for the chatbot
    """
    
    def validate(self):
        """
        Validate the document before saving
        """
        # Ensure either query/response or content is provided
        if self.is_summary and not self.content:
            frappe.throw("Content is required for summary records")
            
        if not self.is_summary and not (self.query or self.response):
            frappe.throw("Query or response is required for interaction records")
    
    def before_save(self):
        """
        Set defaults before saving
        """
        if not self.timestamp:
            self.timestamp = frappe.utils.now()
