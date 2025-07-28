import unittest
import frappe
import json
from gs_chat.controllers.intent_recognition import IntentRecognizer, recognize_intent
from gs_chat.controllers.intent_data import INTENT_CATEGORIES

class TestIntentRecognition(unittest.TestCase):
    def setUp(self):
        self.recognizer = IntentRecognizer()
    
    def test_intent_categories(self):
        """Test that intent categories are properly defined"""
        self.assertTrue(len(INTENT_CATEGORIES) > 0)
        self.assertIn("get_customer_info", INTENT_CATEGORIES)
        self.assertIn("check_invoice", INTENT_CATEGORIES)
        self.assertIn("help", INTENT_CATEGORIES)
    
    def test_normalize_query(self):
        """Test query normalization"""
        test_cases = [
            ("Show me CUSTOMER ABC", "show me customer abc"),
            ("What's the status of invoice #123?", "whats the status of invoice #123"),
            ("Help  me  with   this", "help me with this")
        ]
        
        for original, expected in test_cases:
            normalized = self.recognizer._normalize_query(original)
            self.assertEqual(normalized, expected)
    
    def test_customer_info_intent(self):
        """Test recognition of customer info intent"""
        test_queries = [
            "Show me information about customer ABC Corp",
            "Get details for client XYZ Inc",
            "Who is customer John Smith",
            "Display customer information for Global Traders"
        ]
        
        for query in test_queries:
            result = self.recognizer.recognize_intent(query)
            self.assertEqual(result["intent"], "get_customer_info")
            self.assertGreater(result["confidence"], 0.5)
    
    def test_invoice_intent(self):
        """Test recognition of invoice intent"""
        test_queries = [
            "Show me invoice INV-001",
            "Check the status of invoice INV-2023-05",
            "What's the status of bill #B12345",
            "Find invoice number INV-2023-001"
        ]
        
        for query in test_queries:
            result = self.recognizer.recognize_intent(query)
            self.assertEqual(result["intent"], "check_invoice")
            self.assertGreater(result["confidence"], 0.5)
    
    def test_help_intent(self):
        """Test recognition of help intent"""
        test_queries = [
            "Help me with creating an invoice",
            "I need assistance with inventory management",
            "Guide me on how to update customer information",
            "Help with sales order process"
        ]
        
        for query in test_queries:
            result = self.recognizer.recognize_intent(query)
            self.assertEqual(result["intent"], "help")
            self.assertGreater(result["confidence"], 0.5)
    
    def test_entity_extraction(self):
        """Test entity extraction from queries"""
        test_cases = [
            (
                "Show me information about customer ABC Corp",
                "get_customer_info",
                {"customer_name": "ABC Corp"}
            ),
            (
                "Check the status of invoice INV-2023-05",
                "check_invoice",
                {"invoice_number": "INV-2023-05"}
            ),
            (
                "Help me with creating an invoice",
                "help",
                {"help_topic": "creating an invoice"}
            )
        ]
        
        for query, intent, expected_entities in test_cases:
            # First get the intent
            result = self.recognizer.recognize_intent(query)
            self.assertEqual(result["intent"], intent)
            
            # Then extract entities
            entities = self.recognizer.extract_entities(query, intent)
            
            # Check that expected entities are present
            for key, value in expected_entities.items():
                self.assertIn(key, entities)
                self.assertEqual(entities[key], value)
    
    def test_api_endpoint(self):
        """Test the API endpoint for intent recognition"""
        # This test requires a Frappe environment
        if not frappe.local:
            self.skipTest("Frappe environment not available")
        
        test_query = "Show me customer ABC Corp"
        result = recognize_intent(test_query)
        
        self.assertTrue(result["success"])
        self.assertEqual(result["intent"], "get_customer_info")
        self.assertGreater(result["confidence"], 0.5)
        self.assertIn("entities", result)

if __name__ == "__main__":
    unittest.main()
