import frappe
import json
from frappe import _
from collections import defaultdict
from typing import Dict, List, Any, Optional, Tuple

class EntitySelector:
    """
    Creates context for the chatbot by parsing user queries for doctype references
    and fetching relevant data from ERPNext.
    
    Uses the /doctype/docname pattern to identify and fetch data.
    """
    
    def __init__(self):
        self.cache = {}
        # Load allowed doctypes from settings
        self.allowed_doctypes = self._get_allowed_doctypes()

    def _get_allowed_doctypes(self) -> Dict[str, List[str]]:
        """Get doctypes and fields allowed for chatbot access"""
        not_allowed_modules = [
            "Core",
            "Website",
            "Workflow",
            "Email",
            "Custom",
            "Desk",
            "Integrations",
            "Printing",
            "Social",
            "Contacts",
            "Automation",
            "GS Chat",
            "GSAI Sales",
            "Audit Trail",
            "GST India",
            "VAT India",
            "GS Settings",
            "Whitelabel",
        ]

        return frappe.db.get_list(
            "DocType",
            filters={
                "istable": 0,
                "issingle": 0,
                "module": ("not in", not_allowed_modules)
            },
            fields=["name"],
            pluck="name"
        )

    def get_doctype_suggestions(self, partial_input: str = "") -> List[Dict[str, str]]:
        """
        Get suggestions for doctypes based on partial input.
        
        Args:
            partial_input: Partial doctype name
            
        Returns:
            List of matching doctypes with labels and values
        """
        suggestions = []
        
        for doctype in self.allowed_doctypes:
            if not partial_input or partial_input.lower() in doctype.lower():
                suggestions.append({
                    "label": doctype,
                    "value": doctype
                })
        
        return sorted(suggestions, key=lambda x: x["label"])
    
    def get_document_suggestions(self, doctype: str, partial_input: str = "", limit: int = 200) -> List[Dict[str, str]]:
        """
        Get suggestions for documents of a specific doctype based on partial input.
        
        Args:
            doctype: Doctype to search in
            partial_input: Partial document name or search term
            limit: Maximum number of suggestions to return
            
        Returns:
            List of matching documents with labels and values
        """
        if doctype not in self.allowed_doctypes:
            return []
        
        try:
            # Search for matching documents
            filters = []
            
            # Try name field first
            if partial_input:
                filters.append(["name", "like", f"%{partial_input}%"])
            
            # Get documents matching the filter
            docs = frappe.get_list(
                doctype,
                filters=filters,
                fields=["name", "owner"],
                limit=limit,
                order_by="modified desc"
            )
            
            # Include additional searchable field if available (e.g., customer_name)
            if not docs and partial_input and doctype == "Customer":
                # Try customer_name
                filters = [["customer_name", "like", f"%{partial_input}%"]]
                docs = frappe.get_list(
                    doctype,
                    filters=filters,
                    fields=["name", "customer_name", "owner"],
                    limit=limit,
                    order_by="modified desc"
                )
            
            suggestions = []
            for doc in docs:
                # Only show documents the user has permission to read
                if frappe.has_permission(doctype, "read", doc=doc.name, user=frappe.session.user):
                    # Format the label based on doctype
                    if doctype == "Customer" and hasattr(doc, "customer_name"):
                        label = f"{doc.name} - {doc.customer_name}"
                    else:
                        label = doc.name
                    
                    suggestions.append({
                        "label": label,
                        "value": doc.name
                    })
            
            return suggestions
            
        except Exception as e:
            frappe.log_error(f"Error getting document suggestions for {doctype}: {str(e)}")
            return []

# API endpoints for slash command system
@frappe.whitelist()
def get_doctype_suggestions(partial_input=""):
    """
    Get suggestions for doctypes based on partial input.
    
    Args:
        partial_input: Partial doctype name
        
    Returns:
        List of matching doctypes with labels and values
    """
    entity = EntitySelector()
    return entity.get_doctype_suggestions(partial_input)

@frappe.whitelist()
def get_document_suggestions(doctype, partial_input=""):
    """
    Get suggestions for documents of a specific doctype based on partial input.
    
    Args:
        doctype: Doctype to search in
        partial_input: Partial document name or search term
        
    Returns:
        List of matching documents with labels and values
    """
    entity = EntitySelector()
    return entity.get_document_suggestions(doctype, partial_input)