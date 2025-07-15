import unittest
import frappe
import json
from gs_chat.controllers.suggestion_engine import SuggestionEngine, get_suggestion_engine

class TestSuggestionEngine(unittest.TestCase):
    def setUp(self):
        self.suggestion_engine = SuggestionEngine("Administrator")
    
    def test_get_suggestions(self):
        """Test getting suggestions"""
        # Get suggestions without context
        suggestions = self.suggestion_engine.get_suggestions()
        
        # Check that we got some suggestions
        self.assertIsInstance(suggestions, list)
        self.assertGreater(len(suggestions), 0)
        
        # Check suggestion structure
        for suggestion in suggestions:
            self.assertIn("text", suggestion)
            self.assertIn("action", suggestion)
            self.assertIn("params", suggestion)
            self.assertIn("source", suggestion)
    
    def test_context_based_suggestions(self):
        """Test context-based suggestions"""
        # Test with document context
        doc_context = {
            "doctype": "Sales Order",
            "docname": "SO-00001"
        }
        
        doc_suggestions = self.suggestion_engine.get_suggestions(doc_context)
        
        # Check that we got some suggestions
        self.assertIsInstance(doc_suggestions, list)
        
        # Check for context-specific suggestions
        context_suggestions = [s for s in doc_suggestions if s.get("source") == "context"]
        if context_suggestions:
            self.assertEqual(context_suggestions[0].get("context_type"), "document")
        
        # Test with query context
        query_context = {
            "query": "How do I create an invoice?"
        }
        
        query_suggestions = self.suggestion_engine.get_suggestions(query_context)
        
        # Check that we got some suggestions
        self.assertIsInstance(query_suggestions, list)
    
    def test_role_based_suggestions(self):
        """Test role-based suggestions"""
        # Skip if not in Frappe environment
        if not hasattr(frappe, 'get_roles'):
            self.skipTest("Frappe environment not available")
        
        # Get user roles
        user_roles = self.suggestion_engine._get_user_roles()
        
        # Get suggestions
        suggestions = self.suggestion_engine.get_suggestions()
        
        # Check for role-specific suggestions
        role_suggestions = [s for s in suggestions if s.get("source") == "role"]
        
        # If user has roles with defined suggestions, we should get role-based suggestions
        if any(role in self.suggestion_engine.user_roles for role in ["Accounts Manager", "Sales Manager", "Purchase Manager", "HR Manager", "Stock Manager"]):
            self.assertGreater(len(role_suggestions), 0)
    
    def test_suggestion_history(self):
        """Test suggestion history tracking"""
        # Record a suggestion use
        self.suggestion_engine.record_suggestion_use("Test suggestion")
        
        # Check that it was recorded
        self.assertIn("Test suggestion", self.suggestion_engine.suggestion_history)
        self.assertEqual(self.suggestion_engine.suggestion_history["Test suggestion"]["count"], 1)
        
        # Record it again
        self.suggestion_engine.record_suggestion_use("Test suggestion")
        
        # Check that count increased
        self.assertEqual(self.suggestion_engine.suggestion_history["Test suggestion"]["count"], 2)
    
    def test_suggestion_engine_factory(self):
        """Test suggestion engine factory function"""
        # Get suggestion engine
        engine = get_suggestion_engine("Administrator")
        
        # Check type
        self.assertIsInstance(engine, SuggestionEngine)
        self.assertEqual(engine.user, "Administrator")

if __name__ == "__main__":
    unittest.main()
