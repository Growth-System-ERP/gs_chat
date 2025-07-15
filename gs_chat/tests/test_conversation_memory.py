import unittest
import frappe
import json
from gs_chat.controllers.conversation_memory import ConversationMemory, get_memory_manager

class TestConversationMemory(unittest.TestCase):
    def setUp(self):
        self.memory = ConversationMemory("Administrator")
        
        # Clean up any existing test data
        frappe.db.delete("GS Chat Memory", {"user": "Administrator"})
    
    def test_add_interaction(self):
        """Test adding an interaction to memory"""
        # Skip if not in Frappe environment
        if not hasattr(frappe, 'get_doc'):
            self.skipTest("Frappe environment not available")
        
        # Add a test interaction
        result = self.memory.add_interaction(
            "Test query",
            "Test response",
            {"test_metadata": True}
        )
        
        # Check result
        self.assertTrue(result.get("success"))
        self.assertIn("memory_id", result)
        
        # Verify it was saved
        memory_id = result.get("memory_id")
        memory_doc = frappe.get_doc("GS Chat Memory", memory_id)
        
        self.assertEqual(memory_doc.user, "Administrator")
        self.assertEqual(memory_doc.query, "Test query")
        self.assertEqual(memory_doc.response, "Test response")
        
        # Check metadata
        metadata = json.loads(memory_doc.metadata)
        self.assertTrue(metadata.get("test_metadata"))
    
    def test_get_recent_interactions(self):
        """Test retrieving recent interactions"""
        # Skip if not in Frappe environment
        if not hasattr(frappe, 'get_doc'):
            self.skipTest("Frappe environment not available")
        
        # Add some test interactions
        for i in range(5):
            self.memory.add_interaction(
                f"Test query {i}",
                f"Test response {i}"
            )
        
        # Get recent interactions
        interactions = self.memory.get_recent_interactions(limit=3)
        
        # Check result
        self.assertEqual(len(interactions), 3)
        self.assertEqual(interactions[0]["query"], "Test query 4")  # Most recent first
    
    def test_get_context_for_query(self):
        """Test getting context for a query"""
        # Skip if not in Frappe environment
        if not hasattr(frappe, 'get_doc'):
            self.skipTest("Frappe environment not available")
        
        # Add some test interactions
        for i in range(3):
            self.memory.add_interaction(
                f"Test query {i}",
                f"Test response {i}"
            )
        
        # Get context
        context = self.memory.get_context_for_query("New query")
        
        # Check result
        self.assertIn("Recent conversation:", context)
        self.assertIn("Test query", context)
        self.assertIn("Test response", context)
    
    def test_clear_memory(self):
        """Test clearing memory"""
        # Skip if not in Frappe environment
        if not hasattr(frappe, 'get_doc'):
            self.skipTest("Frappe environment not available")
        
        # Add some test interactions
        for i in range(3):
            self.memory.add_interaction(
                f"Test query {i}",
                f"Test response {i}"
            )
        
        # Clear memory
        result = self.memory.clear_memory()
        
        # Check result
        self.assertTrue(result.get("success"))
        
        # Verify memory was cleared
        interactions = self.memory.get_recent_interactions()
        self.assertEqual(len(interactions), 0)
    
    def test_memory_manager_factory(self):
        """Test memory manager factory function"""
        # Get memory manager
        memory_manager = get_memory_manager("Administrator")
        
        # Check type
        self.assertIsInstance(memory_manager, ConversationMemory)
        self.assertEqual(memory_manager.user, "Administrator")

if __name__ == "__main__":
    unittest.main()
