import frappe
from frappe import _
import json
import re
import time

from .layers.rag_retriever import SmartRAGRetriever
from .layers.ai_provider import AIProviderConfig
from .layers.template_renderer import render_template
from .layers.conversation_manager import get_or_create_memory
from .layers.sql_validator import validate_and_execute_query
from .layers.system_prompt import SYSTEM_PROMPT

from pathlib import Path
from langchain_openai import ChatOpenAI
from langchain.chains import ConversationChain

from langchain_core.messages import SystemMessage
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder, SystemMessagePromptTemplate, HumanMessagePromptTemplate

# Store conversation memories and settings cache
conversation_memories = {}
settings_cache = {"last_updated": None, "settings": None}


def get_cached_settings():
    """Get cached chatbot settings to avoid repeated database calls"""
    global settings_cache

    # Check if we need to refresh cache (cache for 5 minutes)
    current_time = time.time()
    if (settings_cache["last_updated"] is None or
        current_time - settings_cache["last_updated"] > 300):

        settings_cache["settings"] = frappe.get_doc("Chatbot Settings")
        settings_cache["last_updated"] = current_time

    return settings_cache["settings"]

@frappe.whitelist()
def process_message(query, references=None, conversation_id=None):
    """
    Process a message using a simple Langchain API call

    Args:
        query: User's query text
        references: Optional JSON string or list of document references
        conversation_id: Optional ID of an existing conversation

    Returns:
        Dict with response from LLM and success status
    """
    try:
        # Input validation
        if not query or not query.strip():
            return {
                "success": False,
                "error": "Query cannot be empty"
            }

        if isinstance(references, str):
            references = json.loads(references)

        user = frappe.session.user

        # Get API key, model, and provider from cached settings
        settings = get_cached_settings()
        api_key = settings.get("api_key")
        provider = settings.get("provider") or "OpenAI"

        # Set default model and get base_url
        default_model = AIProviderConfig.get_default_model(provider)
        model_name = settings.get("model") or default_model
        base_url = settings.get("base_url") if provider == "DeepSeek" else None

        # Validate model for provider
        if not AIProviderConfig.is_valid_model(provider, model_name):
            frappe.logger().warning(f"Invalid model '{model_name}' for provider '{provider}', using default")
            model_name = default_model

        # Validate provider configuration
        is_valid, error_msg = AIProviderConfig.validate_provider_config(provider, api_key, base_url)
        if not is_valid:
            return {
                "success": False,
                "error": error_msg
            }

        # Handle conversation creation/verification
        if not conversation_id:
            conversation = frappe.get_doc({
                "doctype": "Chatbot Conversation",
                "user": user,
                "title": query[:30] + ("..." if len(query) > 30 else ""),
                "status": "Active"
            })

            conversation.insert(ignore_permissions=True)
            conversation_id = conversation.name
        else:
            conversation = frappe.get_doc("Chatbot Conversation", conversation_id)
            if conversation.user != user:
                frappe.throw(_("You don't have permission to access this conversation"))

        # Save user message
        user_message = frappe.get_doc({
            "doctype": "Chatbot Message",
            "conversation": conversation_id,
            "message_type": "user",
            "content": query,
            "is_error": 0
        })
        user_message.insert(ignore_permissions=True)

        # Get or create memory for this conversation
        memory = get_or_create_memory(conversation_id, conversation_memories, api_key, provider, base_url)

        # RAG: Retrieve relevant documents (replaces SchemaLayer)
        relevant_docs = []
        try:
            rag_retriever = SmartRAGRetriever(api_key, provider, base_url)
            relevant_docs = rag_retriever.get_relevant_documents(query, top_k=5)
            frappe.logger().info(f"RAG retrieved {len(relevant_docs)} documents")
        except Exception as e:
            frappe.log_error(f"RAG initialization/retrieval failed", str(e))
            # Continue without RAG - system will work with basic prompt only
            frappe.logger().warning("Continuing without RAG context due to error")

        # Create LLM instance using configuration factory
        llm_kwargs = AIProviderConfig.get_llm_config(provider, api_key, model_name, base_url)
        llm = ChatOpenAI(**llm_kwargs)

        complete_system_prompt = SYSTEM_PROMPT

        # Add RAG context
        if relevant_docs:
            rag_context = "\n\n📚 RELEVANT KNOWLEDGE BASE:\n"
            for i, doc in enumerate(relevant_docs, 1):
                rag_context += f"\n{i}. Source: {doc['source']}\n"
                content = doc['content']
                escaped_content = content.replace('{{', '{').replace('}}', '}')
                escaped_content = content.replace('{', '{{').replace('}', '}}')
                rag_context += f"Content: {escaped_content}...\n"
            print(rag_context)
            complete_system_prompt += rag_context

        prompt = ChatPromptTemplate.from_messages([
            SystemMessage(content=complete_system_prompt),
            MessagesPlaceholder(variable_name="history"),
            HumanMessagePromptTemplate.from_template("Generate a response for: {input}")
        ])

        # Create the chain with memory
        chain = ConversationChain(
            llm=llm,
            prompt=prompt,
            memory=memory,
            verbose=True
        )

        # Generate response with timing
        start_time = time.time()
        response = chain.predict(input=query)
        response_time = time.time() - start_time

        # Log response details for debugging
        frappe.logger().info(f"AI Response - Provider: {provider}, Model: {model_name}, Time: {response_time:.2f}s")
        frappe.logger().debug(f"AI Response Content: {repr(response)}")

        try:
            # Look for JSON block in backticks or plain JSON
            json_match = re.search(r'```(?:json)?\s*(.*?)\s*```|^\s*(\{.*\})\s*$', response, re.DOTALL)

            if json_match:
                if json_match.group(1):
                    json_str = json_match.group(1)
                else:
                    json_str = json_match.group(2)
            else:
                # Try to find any JSON-like structure
                json_match = re.search(r'\{[\s\S]*\}', response)
                if json_match:
                    json_str = json_match.group(0)
                else:
                    json_str = "{}"

            # Parse the JSON
            analysis_data = json.loads(json_str)

            # Check if this needs database access
            needs_data = analysis_data.get("needs_data", False)
            queries = analysis_data.get("queries", [])

            if needs_data or queries:
                template = analysis_data.get("template", "")

                # Log for debugging
                frappe.logger().debug(f"Executing queries: {json.dumps(queries)}")

                # Execute queries
                query_results = {}

                for query_obj in queries:
                    key = query_obj.get("key")
                    sql = query_obj.get("query")
                    doctype = query_obj.get("doctype")

                    # Skip invalid queries
                    if not key or not sql:
                        continue

                    # Execute SQL query
                    result = validate_and_execute_query(sql, doctype)
                    if not result["success"]:
                        return error_response

                    query_results[key] = result["data"]

                # Render template with query results
                response = render_template(template, query_results)
            else:
                # No database access needed, use the direct response
                response = analysis_data.get("response", "I understand your question, but I don't have a specific answer for that.")

        except Exception as e:
            frappe.log_error(f"Error processing analysis result", f"{str(e)}\nResult: {response}")
            # Fallback to sending the raw analysis result
            response = f"I analyzed your question but encountered an error. Here's what I found:\n\n{response}"


        # Save bot message
        bot_message = frappe.get_doc({
            "doctype": "Chatbot Message",
            "conversation": conversation_id,
            "message_type": "bot",
            "content": response,
            "is_error": 0
        })
        bot_message.insert(ignore_permissions=True)

        return {
            "success": True,
            "response": response,
            "conversation_id": conversation_id,
            "response_time": round(response_time, 2),
            "provider": provider,
            "model": model_name,
            "rag_sources": len(relevant_docs),
            "rag_used": len(relevant_docs) > 0
        }

    except Exception as e:
        frappe.log_error("Chatbot Error", str(e))
        return {
            "success": False,
            "error": str(e)
        }


@frappe.whitelist()
def reset_conversation(conversation_id):
    """Reset the conversation memory"""
    if conversation_id in conversation_memories:
        del conversation_memories[conversation_id]

    return {
        "success": True,
        "message": "Conversation reset successfully"
    }


def log_interaction(query, response, has_context):
    """Log chat interaction for analytics"""
    try:
        doc = frappe.get_doc({
            "doctype": "Chatbot Interaction",
            "user": frappe.session.user,
            "query": query,
            "response": response,
            "context_used": 1 if has_context else 0,
            "timestamp": frappe.utils.now()
        })
        doc.insert(ignore_permissions=True)
    except Exception as e:
        frappe.log_error(f"Failed to log chatbot interaction", str(e))

@frappe.whitelist()
def get_conversations():
    """Get all conversations for the current user"""
    try:
        user = frappe.session.user

        conversations = frappe.get_all(
            "Chatbot Conversation",
            fields=["name", "title", "creation", "modified as last_updated"],
            filters={
                "user": user,
                "status": "Active"
            },
            order_by="modified asc"
        )

        return {
            "success": True,
            "conversations": conversations
        }
    except Exception as e:
        frappe.log_error(f"Failed to get conversations", str(e))
        return {
            "success": False,
            "error": str(e)
        }

@frappe.whitelist()
def create_conversation():
    """Create a new conversation"""
    try:
        user = frappe.session.user

        # Create conversation document
        conversation = frappe.get_doc({
            "doctype": "Chatbot Conversation",
            "user": user,
            "title": "New Conversation",  # Default title, will be updated later
            "status": "Active"
        })

        conversation.insert(ignore_permissions=True)

        return {
            "success": True,
            "conversation_id": conversation.name
        }
    except Exception as e:
        frappe.log_error(f"Failed to create conversation", str(e))
        return {
            "success": False,
            "error": str(e)
        }

@frappe.whitelist()
def get_conversation_messages(conversation_id):
    """Get all messages for a specific conversation"""
    try:
        user = frappe.session.user

        # Check if the user has access to this conversation
        conversation = frappe.get_doc("Chatbot Conversation", conversation_id)
        if conversation.user != user:
            frappe.throw(_("You don't have permission to access this conversation"))

        # Get all messages
        messages = frappe.get_all(
            "Chatbot Message",
            fields=["name", "message_type", "content", "is_error", "creation"],
            filters={
                "conversation": conversation_id
            },
            order_by="creation asc"
        )

        return {
            "success": True,
            "messages": messages
        }
    except Exception as e:
        frappe.log_error(f"Failed to get conversation messages", str(e))
        return {
            "success": False,
            "error": str(e)
        }

@frappe.whitelist()
def get_available_models(provider=None):
    """Get available models for a provider or all providers"""
    try:
        if provider:
            # Get models for specific provider
            models = AIProviderConfig.get_available_models(provider)
            default_model = AIProviderConfig.get_default_model(provider)

            return {
                "success": True,
                "provider": provider,
                "models": models,
                "default_model": default_model
            }
        else:
            # Get models for all providers
            all_models = {}
            providers = ["OpenAI", "DeepSeek"]

            for prov in providers:
                all_models[prov] = {
                    "models": AIProviderConfig.get_available_models(prov),
                    "default_model": AIProviderConfig.get_default_model(prov)
                }

            return {
                "success": True,
                "providers": all_models
            }

    except Exception as e:
        frappe.log_error(f"Failed to get available models", str(e))
        return {
            "success": False,
            "error": str(e)
        }

@frappe.whitelist()
def save_message(conversation_id, message_type, content, is_error=0):
    """Save a message to a conversation"""
    try:
        user = frappe.session.user

        # Check if the user has access to this conversation
        conversation = frappe.get_doc("Chatbot Conversation", conversation_id)
        if conversation.user != user:
            frappe.throw(_("You don't have permission to access this conversation"))

        # Create message
        message = frappe.get_doc({
            "doctype": "Chatbot Message",
            "conversation": conversation_id,
            "message_type": message_type,
            "content": content,
            "is_error": is_error
        })

        message.insert(ignore_permissions=True)

        # Update conversation title if this is the first user message
        if message_type == 'user':
            message_count = frappe.db.count(
                "Chatbot Message",
                filters={
                    "conversation": conversation_id,
                    "message_type": "user"
                }
            )

            if message_count <= 1:
                # Use the first 30 characters as the title
                title = content[:30] + ("..." if len(content) > 30 else "")
                conversation.title = title
                conversation.save(ignore_permissions=True)

        return {
            "success": True,
            "message_id": message.name
        }
    except Exception as e:
        frappe.log_error(f"Failed to save message", str(e))
        return {
            "success": False,
            "error": str(e)
        }
