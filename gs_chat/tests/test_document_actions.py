import unittest
import frappe
import json
from gs_chat.controllers.document_actions import (
    DocumentActionHandler, 
    CreateDocumentHandler,
    ViewDocumentHandler,
    ApproveDocumentHandler,
    RejectDocumentHandler,
    ListDocumentsHandler,
    SUPPORTED_DOCUMENT_TYPES
)

class TestDocumentActions(unittest.TestCase):
    def setUp(self):
        self.base_handler = DocumentActionHandler()
    
    def test_document_types(self):
        """Test that document types are properly defined"""
        self.assertTrue(len(SUPPORTED_DOCUMENT_TYPES) > 0)
        self.assertIn("Purchase Order", SUPPORTED_DOCUMENT_TYPES.values())
        self.assertIn("Sales Invoice", SUPPORTED_DOCUMENT_TYPES.values())
    
    def test_normalize_doc_type(self):
        """Test document type normalization"""
        test_cases = [
            ("purchase order", "Purchase Order"),
            ("SALES INVOICE", "Sales Invoice"),
            ("po", "Purchase Order"),
            ("invoice", "Sales Invoice"),
            ("unknown type", "unknown type")  # Should return as-is if not recognized
        ]
        
        for input_type, expected in test_cases:
            normalized = self.base_handler._normalize_doc_type(input_type)
            self.assertEqual(normalized, expected)
    
    def test_create_document_handler(self):
        """Test document creation handler"""
        # Skip if not in Frappe environment
        if not hasattr(frappe, 'new_doc'):
            self.skipTest("Frappe environment not available")
            
        # Test with valid document type
        handler = CreateDocumentHandler("Purchase Order")
        result = handler.handle()
        
        # Should return success=False in test environment due to permissions
        # but we can check that the action_type is correct
        self.assertEqual(result["action_type"], "create")
    
    def test_view_document_handler(self):
        """Test document viewing handler"""
        # Skip if not in Frappe environment
        if not hasattr(frappe, 'get_list'):
            self.skipTest("Frappe environment not available")
            
        # Test with invalid document ID
        handler = ViewDocumentHandler("Purchase Order", "INVALID-ID")
        result = handler.handle()
        
        # Should return success=False for invalid document
        self.assertEqual(result["action_type"], "view")
        self.assertFalse(result["success"])
    
    def test_approve_document_handler(self):
        """Test document approval handler"""
        # Skip if not in Frappe environment
        if not hasattr(frappe, 'get_list'):
            self.skipTest("Frappe environment not available")
            
        # Test with invalid document ID
        handler = ApproveDocumentHandler("Purchase Order", "INVALID-ID")
        result = handler.handle()
        
        # Should return success=False for invalid document
        self.assertEqual(result["action_type"], "approve")
        self.assertFalse(result["success"])
    
    def test_reject_document_handler(self):
        """Test document rejection handler"""
        # Skip if not in Frappe environment
        if not hasattr(frappe, 'get_list'):
            self.skipTest("Frappe environment not available")
            
        # Test with invalid document ID
        handler = RejectDocumentHandler("Purchase Order", "INVALID-ID")
        result = handler.handle()
        
        # Should return success=False for invalid document
        self.assertEqual(result["action_type"], "reject")
        self.assertFalse(result["success"])
    
    def test_list_documents_handler(self):
        """Test document listing handler"""
        # Skip if not in Frappe environment
        if not hasattr(frappe, 'get_list'):
            self.skipTest("Frappe environment not available")
            
        # Test with valid document type
        handler = ListDocumentsHandler("Purchase Order")
        result = handler.handle()
        
        # Should return success=False in test environment due to permissions
        # but we can check that the action_type is correct
        self.assertEqual(result["action_type"], "list")

if __name__ == "__main__":
    unittest.main()
