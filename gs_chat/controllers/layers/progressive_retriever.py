# gs_chat/controllers/layers/progressive_retriever.py

import json
import frappe
from frappe import _
from .rag_retriever import SmartRAGRetriever
from .sql_validator import validate_and_execute_query
from .ai_provider import AIProviderConfig
from .system_prompt import HOW_TO, DB_QUERY, RESPONSE_FORMAT, FEATURES, SQL_SAFETY_RULES
from langchain_openai import ChatOpenAI

class ProgressiveRetriever:
    """Progressive data fetching with LLM-driven decisions"""
    
    def __init__(self, api_key, provider="OpenAI", base_url=None):
        self.api_key = api_key
        self.provider = provider
        self.base_url = base_url
        self.rag_retriever = SmartRAGRetriever(api_key, provider, base_url)
        
    def create_first_pass_prompt(self):
        """Create the first pass prompt with essential system context"""
        
        # Include essential parts of system prompt for context awareness
        first_pass_context = f"""
{HOW_TO}

{DB_QUERY}

{SQL_SAFETY_RULES}

IMPORTANT: You are analyzing a user query to determine if you can answer it directly or need additional data.

For this analysis, respond with JSON in the following format:
{{
    "can_answer_directly": boolean,  // true if you can answer without any data
    "confidence_level": "high|medium|low",
    "direct_answer": "your complete answer if can_answer_directly is true, otherwise null",
    "reasoning": "brief explanation of your decision",
    "needs_data": {{
        "database_queries": [
            {{
                "query": "SQL query string (following all safety rules)",
                "purpose": "what this query retrieves",
                "expected_fields": ["field1", "field2"]
            }}
        ],
        "doctypes_schema": ["DocType1", "DocType2"],  // for schema information
        "code_analysis": {{
            "needed": boolean,
            "specific_files": ["file1.py", "file2.py"],
            "search_patterns": ["function_name", "class_name"]
        }},
        "rag_search": {{
            "needed": boolean,
            "queries": ["search query 1", "search query 2"],
            "focus_areas": ["help_articles", "conversations", "code", "schema", "process_docs"]
        }},
        "specific_records": {{
            "doctype": "DocType name",
            "names": ["record1", "record2"]
        }}
    }}
}}

Remember:
- Set can_answer_directly to true for general ERP questions, business process explanations, or anything within your knowledge
- Request database queries ONLY when specific data is needed
- Follow all SQL safety rules when generating queries
- Consider the user's business context and previous conversation
"""
        return first_pass_context
    
    def analyze_query_needs(self, query, conversation_context=None):
        """First pass: Analyze what data is needed"""
        
        llm_kwargs = AIProviderConfig.get_llm_config(
            self.provider, 
            self.api_key, 
            AIProviderConfig.get_default_model(self.provider), 
            self.base_url
        )
        llm = ChatOpenAI(**llm_kwargs)
        
        first_pass_prompt = self.create_first_pass_prompt()
        
        # Add conversation context if available
        context_str = ""
        if conversation_context:
            context_str = "\nRecent conversation:\n"
            for msg in conversation_context[-5:]:  # Last 5 messages
                context_str += f"{msg.role}: {msg.content[:200]}...\n"
        
        full_prompt = f"""{first_pass_prompt}

{context_str}

User Query: {query}

Analyze this query and respond with the JSON format specified above."""
        
        try:
            response = llm.invoke(full_prompt)
            analysis = json.loads(response.content)
            
            # Validate and sanitize SQL queries if present
            if analysis.get("needs_data", {}).get("database_queries"):
                for query_spec in analysis["needs_data"]["database_queries"]:
                    # Basic validation
                    sql = query_spec.get("query", "")
                    if sql and not self._is_safe_sql(sql):
                        query_spec["query"] = ""  # Remove unsafe query
                        
            return analysis
            
        except Exception as e:
            frappe.log_error(f"Error in query analysis: {str(e)}")
            # Fallback to needing RAG search
            return {
                "can_answer_directly": False,
                "confidence_level": "low",
                "needs_data": {"rag_search": {"needed": True, "queries": [query]}}
            }
    
    def _is_safe_sql(self, sql):
        """Quick safety check for SQL queries"""
        unsafe_keywords = ['DELETE', 'DROP', 'TRUNCATE', 'ALTER', 'UPDATE', 'GRANT', 'REVOKE']
        sql_upper = sql.upper()
        return not any(keyword in sql_upper for keyword in unsafe_keywords)
    
    def fetch_progressive_data(self, needs_analysis):
        """Fetch data based on analysis"""
        fetched_data = {}
        errors = []
        
        needs = needs_analysis.get("needs_data", {})
        
        # 1. Execute SQL queries if needed
        if needs.get("database_queries"):
            fetched_data["query_results"] = {}
            for query_spec in needs["database_queries"]:
                try:
                    sql = query_spec.get("query")
                    if sql:
                        result = validate_and_execute_query(sql)
                        if result["success"]:
                            fetched_data["query_results"][query_spec["purpose"]] = {
                                "data": result["data"],
                                "fields": query_spec.get("expected_fields", [])
                            }
                        else:
                            errors.append(f"Query failed: {result.get('error')}")
                except Exception as e:
                    errors.append(f"Query execution error: {str(e)}")
        
        # 2. Get doctype schemas if needed
        if needs.get("doctypes_schema"):
            fetched_data["schemas"] = {}
            for doctype in needs["doctypes_schema"]:
                try:
                    # Get doctype metadata
                    if frappe.db.exists("DocType", doctype):
                        meta = frappe.get_meta(doctype)
                        schema_info = {
                            "doctype": doctype,
                            "module": meta.module,
                            "is_submittable": meta.is_submittable,
                            "fields": []
                        }
                        
                        for field in meta.fields:
                            schema_info["fields"].append({
                                "fieldname": field.fieldname,
                                "fieldtype": field.fieldtype,
                                "label": field.label,
                                "options": field.options,
                                "reqd": field.reqd,
                                "hidden": field.hidden
                            })
                        
                        fetched_data["schemas"][doctype] = schema_info
                except Exception as e:
                    errors.append(f"Schema fetch error for {doctype}: {str(e)}")
        
        # 3. RAG search if needed
        if needs.get("rag_search", {}).get("needed"):
            fetched_data["rag_results"] = []
            queries = needs["rag_search"].get("queries", [])
            
            for search_query in queries:
                try:
                    results = self.rag_retriever.get_relevant_documents(search_query, top_k=3)
                    fetched_data["rag_results"].extend(results)
                except Exception as e:
                    errors.append(f"RAG search error: {str(e)}")
        
        # 4. Get specific records if needed
        if needs.get("specific_records"):
            doctype = needs["specific_records"].get("doctype")
            names = needs["specific_records"].get("names", [])
            
            if doctype and names:
                fetched_data["records"] = {}
                for name in names:
                    try:
                        if frappe.db.exists(doctype, name):
                            doc = frappe.get_doc(doctype, name)
                            fetched_data["records"][name] = doc.as_dict()
                    except Exception as e:
                        errors.append(f"Error fetching {doctype} {name}: {str(e)}")
        
        # 5. Code analysis if needed
        if needs.get("code_analysis", {}).get("needed"):
            # This would use the existing RAG code loading functionality
            # but with specific file targeting
            fetched_data["code_analysis"] = []
            # Implementation would go here
        
        if errors:
            fetched_data["errors"] = errors
            
        return fetched_data
    
    def format_data_for_context(self, fetched_data):
        """Format fetched data for LLM context"""
        context_parts = []
        
        # Format query results
        if fetched_data.get("query_results"):
            context_parts.append("📊 DATABASE QUERY RESULTS:")
            for purpose, result in fetched_data["query_results"].items():
                context_parts.append(f"\n{purpose}:")
                if result["data"]:
                    # Format as table-like structure
                    if result["fields"]:
                        context_parts.append(f"Fields: {', '.join(result['fields'])}")
                    for row in result["data"][:10]:  # Limit to 10 rows
                        context_parts.append(f"  {json.dumps(row, default=str)}")
                    if len(result["data"]) > 10:
                        context_parts.append(f"  ... and {len(result['data']) - 10} more rows")
                else:
                    context_parts.append("  No data found")
        
        # Format schemas
        if fetched_data.get("schemas"):
            context_parts.append("\n📋 DATABASE SCHEMAS:")
            for doctype, schema in fetched_data["schemas"].items():
                context_parts.append(f"\n{doctype}:")
                context_parts.append(f"  Module: {schema['module']}")
                context_parts.append(f"  Submittable: {'Yes' if schema['is_submittable'] else 'No'}")
                context_parts.append("  Key Fields:")
                for field in schema["fields"][:15]:  # Show top 15 fields
                    if not field["hidden"]:
                        req = " (required)" if field["reqd"] else ""
                        context_parts.append(f"    - {field['fieldname']}: {field['label']} ({field['fieldtype']}){req}")
        
        # Format RAG results
        if fetched_data.get("rag_results"):
            context_parts.append("\n📚 RELEVANT KNOWLEDGE:")
            for i, doc in enumerate(fetched_data["rag_results"][:5], 1):
                context_parts.append(f"\n{i}. Source: {doc.get('source', 'Unknown')}")
                content = doc.get('content', '')[:300]
                context_parts.append(f"   {content}...")
        
        # Format specific records
        if fetched_data.get("records"):
            context_parts.append("\n📄 SPECIFIC RECORDS:")
            for name, record in fetched_data["records"].items():
                context_parts.append(f"\n{name}:")
                # Show key fields only
                key_fields = ["customer", "supplier", "total", "grand_total", "status", "workflow_state"]
                for field in key_fields:
                    if field in record:
                        context_parts.append(f"  {field}: {record[field]}")
        
        # Add errors if any
        if fetched_data.get("errors"):
            context_parts.append("\n⚠️ ERRORS ENCOUNTERED:")
            for error in fetched_data["errors"]:
                context_parts.append(f"  - {error}")
        
        return "\n".join(context_parts)