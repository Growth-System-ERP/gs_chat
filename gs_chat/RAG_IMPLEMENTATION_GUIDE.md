# RAG (Retrieval-Augmented Generation) Implementation Guide

## 🎯 What is RAG?

RAG combines:
- **Retrieval**: Finding relevant documents from knowledge base
- **Augmentation**: Adding retrieved content to AI prompt
- **Generation**: AI generates response using both query and retrieved context

## 🏗️ Architecture Overview

```
User Query → RAG Retriever → Vector Search → Relevant Docs → Enhanced Prompt → AI Response
```

## 📊 Implementation Details

### 1. **RAG Components Added**

#### **RAGRetriever Class**
- Handles document retrieval and vector search
- Supports multiple AI providers (OpenAI, DeepSeek)
- Caches vector store for performance

#### **Knowledge Base Sources**
1. **Help Articles** - From database if Help Article doctype exists
2. **System Documentation** - Static documentation about ERP processes
3. **Conversation History** - Successful past conversations for learning
4. **Process Documentation** - Business process workflows

#### **Vector Store**
- Uses FAISS for fast similarity search
- Embeddings via OpenAI (fallback for DeepSeek)
- Auto-refreshes every hour
- Manual refresh available

### 2. **Integration Points**

#### **In process_message() function**
```python
# RAG: Retrieve relevant documents
rag_retriever = RAGRetriever(api_key, provider, base_url)
relevant_docs = rag_retriever.get_relevant_documents(query, top_k=3)

# Add RAG context to prompt
if relevant_docs:
    rag_context = "\n\n📚 RELEVANT KNOWLEDGE BASE:\n"
    for i, doc in enumerate(relevant_docs, 1):
        rag_context += f"\n{i}. Source: {doc['source']}\n"
        rag_context += f"Content: {doc['content'][:500]}...\n"
    complete_system_prompt += rag_context
```

#### **Response Metadata**
```python
return {
    "success": True,
    "response": response,
    "rag_sources": len(relevant_docs),
    "rag_used": len(relevant_docs) > 0
}
```

## 🚀 How to Use RAG

### 1. **Automatic Usage**
RAG works automatically when you ask questions:

```python
# User asks: "How to create sales invoice?"
# RAG retrieves relevant documentation about sales invoice creation
# AI generates response using both system knowledge and retrieved docs
```

### 2. **Manual Knowledge Base Refresh**
```python
# API call to refresh knowledge base
frappe.call({
    method: "gs_chat.controllers.chat.refresh_rag_knowledge_base",
    callback: function(r) {
        console.log("Knowledge base refreshed:", r.message);
    }
});
```

### 3. **Check RAG Status**
```python
# API call to check RAG system status
frappe.call({
    method: "gs_chat.controllers.chat.get_rag_status",
    callback: function(r) {
        console.log("RAG Status:", r.message.status);
    }
});
```

## 📈 Benefits of RAG Implementation

### 1. **Improved Accuracy**
- AI has access to specific documentation
- Reduces hallucination by providing factual context
- Better answers for complex business processes

### 2. **Contextual Responses**
- Retrieves relevant past conversations
- Learns from successful interactions
- Provides consistent answers

### 3. **Knowledge Management**
- Centralizes business process documentation
- Makes institutional knowledge searchable
- Improves over time with more data

### 4. **Performance Optimization**
- Caches vector store for fast retrieval
- Only retrieves top-k most relevant documents
- Efficient similarity search with FAISS

## 🔧 Configuration Options

### 1. **Retrieval Parameters**
```python
# Number of documents to retrieve
top_k = 3  # Default: 3 documents

# Cache refresh interval
cache_timeout = 3600  # 1 hour in seconds
```

### 2. **Document Sources**
You can customize which sources to include:
- Help Articles (from database)
- System Documentation (static)
- Conversation History (learning)
- Process Documentation (workflows)

### 3. **Embedding Models**
- OpenAI: Uses OpenAI embeddings
- DeepSeek: Falls back to OpenAI embeddings
- Can be extended for other providers

## 📊 Monitoring RAG Performance

### 1. **Response Metadata**
Every response includes:
```json
{
    "rag_sources": 2,
    "rag_used": true,
    "response_time": 1.45
}
```

### 2. **System Status**
Check RAG system health:
```json
{
    "vector_store_loaded": true,
    "last_updated": 1640995200,
    "cache_age_hours": 0.5
}
```

## 🛠️ Troubleshooting

### 1. **No RAG Results**
- Check if knowledge base is populated
- Verify API key configuration
- Refresh knowledge base manually

### 2. **Slow Performance**
- Vector store might need rebuilding
- Check cache status
- Consider reducing top_k parameter

### 3. **Poor Relevance**
- Add more specific documentation
- Improve document chunking
- Use better embedding models

## 🔮 Future Enhancements

### 1. **Custom Document Types**
- Add support for custom doctypes as knowledge sources
- File attachments indexing
- Web page content crawling

### 2. **Advanced Retrieval**
- Hybrid search (keyword + semantic)
- Re-ranking algorithms
- Query expansion techniques

### 3. **Analytics**
- RAG usage statistics
- Document relevance scoring
- User feedback integration

## 📝 Best Practices

### 1. **Document Quality**
- Keep documents well-structured
- Use clear headings and sections
- Regular content updates

### 2. **Performance**
- Monitor cache hit rates
- Regular knowledge base refresh
- Optimize document chunking

### 3. **Maintenance**
- Regular system health checks
- Monitor embedding costs
- Update documentation regularly

This RAG implementation significantly enhances your chatbot's ability to provide accurate, contextual, and helpful responses by leveraging your organization's knowledge base.
