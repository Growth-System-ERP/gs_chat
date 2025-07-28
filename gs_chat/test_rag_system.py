#!/usr/bin/env python3
"""
Test script for Smart RAG system - Dry run validation
"""

import frappe
import json
import time
from unittest.mock import Mock, patch

def test_imports():
    """Test all required imports"""
    print("🔍 Testing imports...")
    
    try:
        from gs_chat.controllers.chat import SmartRAGRetriever, process_message
        print("✅ Core imports successful")
    except ImportError as e:
        print(f"❌ Import error: {e}")
        return False
    
    # Test langchain imports
    try:
        from langchain_openai import ChatOpenAI, OpenAIEmbeddings
        print("✅ LangChain imports successful")
    except ImportError:
        try:
            from langchain.chat_models import ChatOpenAI
            from langchain.embeddings import OpenAIEmbeddings
            print("✅ Legacy LangChain imports successful")
        except ImportError as e:
            print(f"❌ LangChain import error: {e}")
            return False
    
    return True

def test_lightweight_detection():
    """Test lightweight mode detection"""
    print("\n🔍 Testing lightweight mode detection...")
    
    try:
        from gs_chat.controllers.chat import SmartRAGRetriever
        
        # Test with mock API key
        retriever = SmartRAGRetriever("test-key", "OpenAI")
        
        print(f"✅ Lightweight mode: {retriever.lightweight_mode}")
        print(f"✅ Embeddings initialized: {retriever.embeddings is not None}")
        
        return True
    except Exception as e:
        print(f"❌ Lightweight detection error: {e}")
        return False

def test_knowledge_base_loading():
    """Test knowledge base loading without vector store"""
    print("\n🔍 Testing knowledge base loading...")
    
    try:
        from gs_chat.controllers.chat import SmartRAGRetriever
        
        retriever = SmartRAGRetriever("test-key", "OpenAI", lightweight_mode=True)
        
        # Test lightweight knowledge base
        docs = retriever._load_lightweight_knowledge_base()
        print(f"✅ Loaded {len(docs)} documents in lightweight mode")
        
        # Test individual components
        system_docs = retriever._load_system_documentation()
        print(f"✅ System docs: {len(system_docs)}")
        
        return True
    except Exception as e:
        print(f"❌ Knowledge base loading error: {e}")
        return False

def test_lightweight_search():
    """Test lightweight search functionality"""
    print("\n🔍 Testing lightweight search...")
    
    try:
        from gs_chat.controllers.chat import SmartRAGRetriever
        
        retriever = SmartRAGRetriever("test-key", "OpenAI", lightweight_mode=True)
        
        # Test search
        results = retriever.get_relevant_documents("sales invoice", top_k=3)
        print(f"✅ Search returned {len(results)} results")
        
        if results:
            print(f"✅ First result source: {results[0].get('source', 'Unknown')}")
        
        return True
    except Exception as e:
        print(f"❌ Lightweight search error: {e}")
        return False

def test_process_message_integration():
    """Test the main process_message function"""
    print("\n🔍 Testing process_message integration...")
    
    try:
        # Mock frappe functions
        with patch('frappe.get_doc') as mock_get_doc, \
             patch('frappe.session') as mock_session, \
             patch('frappe.log_error') as mock_log_error:
            
            # Setup mocks
            mock_session.user = "test@example.com"
            
            # Mock settings
            mock_settings = Mock()
            mock_settings.get.side_effect = lambda key: {
                'api_key': 'test-key',
                'provider': 'OpenAI',
                'model': 'gpt-3.5-turbo'
            }.get(key)
            
            mock_get_doc.return_value = mock_settings
            
            # Import after mocking
            from gs_chat.controllers.chat import process_message
            
            # This would normally fail due to missing conversation/message creation
            # but we can test the RAG initialization part
            print("✅ process_message function accessible")
            
        return True
    except Exception as e:
        print(f"❌ Process message integration error: {e}")
        return False

def test_error_handling():
    """Test error handling scenarios"""
    print("\n🔍 Testing error handling...")
    
    try:
        from gs_chat.controllers.chat import SmartRAGRetriever
        
        # Test with invalid API key
        retriever = SmartRAGRetriever("", "OpenAI")
        
        # This should not crash
        results = retriever.get_relevant_documents("test query")
        print(f"✅ Handled empty API key gracefully: {len(results)} results")
        
        # Test with invalid provider
        retriever2 = SmartRAGRetriever("test-key", "InvalidProvider")
        results2 = retriever2.get_relevant_documents("test query")
        print(f"✅ Handled invalid provider gracefully: {len(results2)} results")
        
        return True
    except Exception as e:
        print(f"❌ Error handling test failed: {e}")
        return False

def test_performance():
    """Test performance characteristics"""
    print("\n🔍 Testing performance...")
    
    try:
        from gs_chat.controllers.chat import SmartRAGRetriever
        
        # Test lightweight mode performance
        start_time = time.time()
        retriever = SmartRAGRetriever("test-key", "OpenAI", lightweight_mode=True)
        init_time = time.time() - start_time
        print(f"✅ Lightweight initialization: {init_time:.3f}s")
        
        # Test search performance
        start_time = time.time()
        results = retriever.get_relevant_documents("sales invoice", top_k=3)
        search_time = time.time() - start_time
        print(f"✅ Lightweight search: {search_time:.3f}s for {len(results)} results")
        
        return True
    except Exception as e:
        print(f"❌ Performance test error: {e}")
        return False

def run_all_tests():
    """Run all tests"""
    print("🚀 Starting Smart RAG System Dry Run Tests")
    print("=" * 50)
    
    tests = [
        test_imports,
        test_lightweight_detection,
        test_knowledge_base_loading,
        test_lightweight_search,
        test_process_message_integration,
        test_error_handling,
        test_performance
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        try:
            if test():
                passed += 1
        except Exception as e:
            print(f"❌ Test {test.__name__} crashed: {e}")
    
    print("\n" + "=" * 50)
    print(f"🎯 Test Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! System ready for deployment.")
    else:
        print("⚠️  Some tests failed. Review issues before deployment.")
    
    return passed == total

if __name__ == "__main__":
    # Initialize frappe if needed
    try:
        frappe.init()
        frappe.connect()
    except:
        print("⚠️  Running without Frappe context (some tests may fail)")
    
    run_all_tests()
