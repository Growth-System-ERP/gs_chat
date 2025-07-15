import frappe
from frappe import _
import json
import re
from langchain_openai import ChatOpenAI
from langchain.chains import ConversationChain
from langchain.memory import ConversationTokenBufferMemory
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder, SystemMessagePromptTemplate, HumanMessagePromptTemplate

from gs_chat.controllers.layers.schema import SchemaLayer

# Store conversation memories
conversation_memories = {}

SYSTEM_PROMPT = """You are an ERP assistant specialized in helping users with ERPNext and business software questions.

ONLY answer questions related to:
- ERPNext features, modules, and functionality
- Business processes (accounting, inventory, HR, etc.)
- ERP implementation and best practices
- General business software concepts
    
DO NOT answer questions about:
- Topics unrelated to business or ERP software (celebrities, politics, etc.)
- Personal or controversial subjects
- Quantum physics, space exploration, or other scientific topics outside of business
- Entertainment, sports, or other non-business domains

ALWAYS make sure to:
- Keep it hidden that this is ERPnext.
- You can refer to erp as Growth ERP.
- As this ERP is implemented by Growth System and all customizations are owned by them too, whenever asked please mention them as erp's creators.
- Mention this software a proprietary and not open source or free to public, you can generally reject any queries regarding inner working and code and license of this software, just answer what is in general a genuine request for help related to software use.

If asked about a topic outside your scope, politely explain that you're an ERP assistant and can only help with business and ERPNext-related questions.

QUERY GUIDELINES:
- Use backtick quotes around table and field names: `tabItem`, `item_code`
- Tables in ERPNext have 'tab' prefix (e.g. Item doctype becomes `tabItem` table)
- For filtering by status, use docstatus=1 for submitted documents
- Use proper joins when working with multiple tables
- Always make sure to use docstatus for all submittable doctypes and child tables when writing a query.

For "second most X":
- CORRECT: SELECT * FROM table ORDER BY metric DESC LIMIT 1 OFFSET 1
- INCORRECT: SELECT * FROM table ORDER BY metric DESC LIMIT 2,1 (This returns the 3rd result!)

For "third most X":
- CORRECT: SELECT * FROM table ORDER BY metric DESC LIMIT 1 OFFSET 2
- INCORRECT: SELECT * FROM table ORDER BY metric DESC LIMIT 3,1

RESPONSE FORMAT - YOU MUST CHOOSE ONE OF THESE TWO FORMATS:

1. For questions requiring database queries:
```json
{{
  "needs_data": true,
  "queries": [
    {{
      "key": "unique_key_name",
      "query": "SQL query",
      "doctype": "Related DocType"
    }}
  ],
  "template": "Your response template with {{placeholder}} variables"
}}
```

2. For questions NOT requiring database queries:
```json
{{
  "needs_data": false,
  "response": "Your complete response to the user's question"
}}
```

The template should include placeholders in {{curly_braces}} that match query keys. For example: 
"The top selling item is {{top_item.item_code}} with {{top_item.total_qty}} units sold."

For LISTS OF RESULTS, use this format in your template:
"Top items: {{% for item in top_items %}}- {{{{item.item_code}}}}: {{item.total_qty}} units{{% endfor %}}"

YOUR RESPONSE MUST BE A VALID JSON OBJECT MATCHING ONE OF THE TWO FORMATS ABOVE.

Generate only the JSON response using the schema information provided and sure information about erpnext database.
"""

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
        if isinstance(references, str):
            references = json.loads(references)

        user = frappe.session.user

        # Get API key and model from settings
        settings = frappe.get_doc("Chatbot Settings")
        api_key = settings.get("api_key")
        model_name = settings.get("model") or "gpt-3.5-turbo"

        # Handle conversation creation/verification (kept from original code)
        conversation_created = False

        if not conversation_id:
            conversation = frappe.get_doc({
                "doctype": "Chatbot Conversation",
                "user": user,
                "title": query[:30] + ("..." if len(query) > 30 else ""),
                "status": "Active"
            })
            
            conversation.insert(ignore_permissions=True)
            conversation_id = conversation.name
            conversation_created = True
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
        memory = get_or_create_memory(conversation_id, api_key)
        
        relevant_doctypes = SchemaLayer.get_relevant_doctypes(query, references)
        schema_context = SchemaLayer.build_schema_context(relevant_doctypes)
        
        # Create LLM instance
        llm = ChatOpenAI(
            openai_api_key=api_key,
            model_name=model_name,
            temperature=0.2
        )

        complete_system_prompt = SYSTEM_PROMPT
        
        if schema_context:
            complete_system_prompt += f"\n\nSchema Information:\n{schema_context}"

        prompt = ChatPromptTemplate.from_messages([
            SystemMessagePromptTemplate.from_template(complete_system_prompt),
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
        
        # Generate response
        response = chain.predict(input=query)

        frappe.log_error("resp", repr(response))
        
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
            
            if needs_data:
                # Extract queries and template
                queries = analysis_data.get("queries", [])
                template = analysis_data.get("template", "")
                
                # Log for debugging
                frappe.logger().debug(f"Executing queries: {json.dumps(queries)}")
                
                # Execute queries
                query_results = {}
                
                for query_obj in queries:
                    key = query_obj.get("key")
                    sql = query_obj.get("query")
                    
                    # Skip invalid queries
                    if not key or not sql:
                        continue

                    # Execute SQL query
                    result = frappe.db.sql(sql, as_dict=1)
                    query_results[key] = result
                
                # Render template with query results
                response = render_template(template, query_results)
            else:
                # No database access needed, use the direct response
                response = analysis_data.get("response", "I understand your question, but I don't have a specific answer for that.")
            
        except Exception as e:
            frappe.log_error(f"Error processing analysis result: {str(e)}\nResult: {response}")
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
        }
    
    except Exception as e:
        frappe.log_error(f"Chatbot Error: {str(e)}")
        return {
            "success": False,
            "error": str(e)
        }

def render_template(template, query_results):
    """
    Render a template with query results
    
    Args:
        template: Template string with placeholders
        query_results: Dictionary of query results
        
    Returns:
        Rendered template
    """
    # First handle simple placeholders like {key.field}
    result = template
    
    # Find all placeholders in the format {key.field}
    simple_placeholders = re.findall(r'\{([^{}]+)\}', template)
    
    for placeholder in simple_placeholders:
        parts = placeholder.split('.')
        if len(parts) == 1:
            # Simple placeholder like {key}
            key = parts[0]
            if key in query_results:
                if isinstance(query_results[key], list) and query_results[key]:
                    # Use the first result for a list
                    result = result.replace(f"{{{key}}}", str(query_results[key][0]))
                else:
                    result = result.replace(f"{{{key}}}", str(query_results[key]))
        elif len(parts) == 2:
            # Nested placeholder like {key.field}
            key, field = parts
            if key in query_results and isinstance(query_results[key], list) and query_results[key]:
                # Use the first result's field
                if field in query_results[key][0]:
                    result = result.replace(f"{{{key}.{field}}}", str(query_results[key][0][field]))
    
    # Now handle loop templates like {% for item in items %}...{% endfor %}
    loop_pattern = r'{%\s*for\s+(\w+)\s+in\s+(\w+)\s*%}(.*?){%\s*endfor\s*%}'
    
    # Find all loop blocks
    loop_blocks = re.findall(loop_pattern, result, re.DOTALL)
    
    for var_name, collection_name, block_content in loop_blocks:
        if collection_name in query_results and isinstance(query_results[collection_name], list):
            collection = query_results[collection_name]
            
            # Process the loop
            rendered_items = []
            for i, item in enumerate(collection):
                # Create a context for this iteration
                context = {var_name: item, "loop": {"index": i + 1}}
                
                # Render the block content with this context
                item_result = block_content
                
                # Replace {{var.field}} references
                var_pattern = r'{{([\w.]+)}}'
                var_matches = re.findall(var_pattern, block_content)
                
                for var_ref in var_matches:
                    var_parts = var_ref.split('.')
                    
                    if var_parts[0] == var_name and len(var_parts) > 1:
                        # It's a reference to the loop variable, like {{item.field}}
                        field = var_parts[1]
                        if field in item:
                            item_result = item_result.replace(f"{{{{{var_ref}}}}}", str(item[field]))
                    elif var_parts[0] == "loop" and len(var_parts) > 1:
                        # It's a reference to the loop object, like {{loop.index}}
                        loop_attr = var_parts[1]
                        if loop_attr in context["loop"]:
                            item_result = item_result.replace(f"{{{{{var_ref}}}}}", str(context["loop"][loop_attr]))
                
                rendered_items.append(item_result)
            
            # Replace the entire loop block with the rendered items
            loop_str = f"{{% for {var_name} in {collection_name} %}}{block_content}{{% endfor %}}"
            result = result.replace(loop_str, "".join(rendered_items))
    
    return result
def get_or_create_memory(conversation_id, api_key):
    if conversation_id not in conversation_memories:
        # Use a token-aware memory implementation
        memory = ConversationTokenBufferMemory(
            llm=ChatOpenAI(temperature=0, openai_api_key=api_key),
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
        frappe.log_error(f"Failed to log chatbot interaction: {str(e)}")

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
        frappe.log_error(f"Failed to get conversations: {str(e)}")
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
        frappe.log_error(f"Failed to create conversation: {str(e)}")
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
        frappe.log_error(f"Failed to get conversation messages: {str(e)}")
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
        frappe.log_error(f"Failed to save message: {str(e)}")
        return {
            "success": False,
            "error": str(e)
        }