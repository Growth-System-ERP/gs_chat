
import frappe
from langchain.memory import ConversationTokenBufferMemory
from .ai_provider import AIProviderConfig
from langchain_openai import ChatOpenAI

def get_or_create_memory(conversation_id, conversation_memories, api_key, provider="OpenAI", base_url=None):
    if conversation_id not in conversation_memories:
        # Create LLM instance for memory using configuration factory
        memory_llm_kwargs = AIProviderConfig.get_llm_config(provider, api_key,
                                                           AIProviderConfig.get_default_model(provider),
                                                           base_url)
        memory_llm_kwargs["temperature"] = 0  # Override temperature for memory

        # Use a token-aware memory implementation
        memory = ConversationTokenBufferMemory(
            llm=ChatOpenAI(**memory_llm_kwargs),
            max_token_limit=3000,
            return_messages=True
        )

        # Load recent messages from database (limit to last 10)
        messages = frappe.get_all(
            "Chatbot Message",
            fields=["message_type", "content"],
            filters={
                "conversation": conversation_id,
                "is_error": 0
            },
            order_by="creation desc",
            limit=10
        )

        # Add messages in reverse order (oldest first)
        for msg in reversed(messages):
            if msg.message_type == "user":
                memory.chat_memory.add_user_message(msg.content)
            elif msg.message_type == "bot":
                memory.chat_memory.add_ai_message(msg.content)

        conversation_memories[conversation_id] = memory

    return conversation_memories[conversation_id]
