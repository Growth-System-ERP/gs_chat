import frappe
from frappe import _
import json
import re
import time
import os
import ast
from pathlib import Path
from langchain_openai import ChatOpenAI
from langchain.chains import ConversationChain
from langchain.memory import ConversationTokenBufferMemory
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder, SystemMessagePromptTemplate, HumanMessagePromptTemplate
try:
    from langchain_openai import OpenAIEmbeddings
except ImportError:
    from langchain.embeddings import OpenAIEmbeddings

try:
    from langchain_community.vectorstores import FAISS
except ImportError:
    from langchain.vectorstores import FAISS

try:
    from langchain_text_splitters import RecursiveCharacterTextSplitter
except ImportError:
    from langchain.text_splitter import RecursiveCharacterTextSplitter

try:
    from langchain_core.documents import Document
except ImportError:
    from langchain.schema import Document

# SchemaLayer removed - now using Smart RAG for schema information

# Store conversation memories and settings cache
conversation_memories = {}
settings_cache = {"last_updated": None, "settings": None}

# RAG components cache
rag_cache = {
    "vector_store": None,
    "embeddings": None,
    "last_updated": None
}

class SmartRAGRetriever:
    """Enhanced RAG implementation with resource optimization for smaller instances"""

    def __init__(self, api_key, provider="OpenAI", base_url=None, lightweight_mode=None):
        self.api_key = api_key
        self.provider = provider
        self.base_url = base_url
        self.app_path = frappe.get_app_path("gs_chat")
        self.site_path = frappe.get_site_path()

        # Auto-detect lightweight mode based on system resources
        if lightweight_mode is None:
            self.lightweight_mode = self._detect_lightweight_mode()
        else:
            self.lightweight_mode = lightweight_mode

        # Adjust settings based on mode
        if self.lightweight_mode:
            self.embeddings = None  # Skip embeddings for lightweight mode
            self.text_splitter = RecursiveCharacterTextSplitter(
                chunk_size=500,    # Smaller chunks
                chunk_overlap=50,  # Less overlap
                separators=["\n\n", "\n"]
            )
        else:
            self.embeddings = self._get_embeddings()
            self.text_splitter = RecursiveCharacterTextSplitter(
                chunk_size=1000,
                chunk_overlap=200,
                separators=["\n\n", "\n", " ", ""]
            )

    def _get_embeddings(self):
        """Get embeddings model based on provider"""
        if self.provider == "OpenAI":
            return OpenAIEmbeddings(openai_api_key=self.api_key)
        elif self.provider == "DeepSeek":
            # DeepSeek doesn't have embeddings API, fallback to OpenAI
            # You might want to use a different embedding service
            return OpenAIEmbeddings(openai_api_key=self.api_key)
        else:
            return OpenAIEmbeddings(openai_api_key=self.api_key)

    def _detect_lightweight_mode(self):
        """Auto-detect if we should use lightweight mode based on system resources"""
        try:
            import psutil

            # Get system memory
            memory = psutil.virtual_memory()
            available_gb = memory.available / (1024**3)

            # Get CPU count
            cpu_count = psutil.cpu_count()

            frappe.logger().info(f"System resources: {available_gb:.1f}GB RAM, {cpu_count} CPUs")

            # Use lightweight mode if:
            # - Less than 2GB available RAM
            # - Less than 2 CPU cores
            lightweight = available_gb < 2 or cpu_count < 2
            frappe.logger().info(f"RAG mode: {'Lightweight' if lightweight else 'Full'}")
            return lightweight

        except ImportError:
            frappe.logger().warning("psutil not available, using config-based detection")
            # If psutil not available, check frappe settings or use conservative approach
            return frappe.conf.get("lightweight_rag", True)  # Default to lightweight
        except Exception as e:
            frappe.log_error(f"Error detecting system resources: {str(e)}")
            return True  # Conservative fallback

    def get_relevant_documents(self, query, top_k=5):
        """
        Retrieve relevant documents for the query with lightweight mode support

        Args:
            query (str): User query
            top_k (int): Number of top documents to retrieve

        Returns:
            list: List of relevant documents
        """
        try:
            if self.lightweight_mode:
                # Lightweight mode: Use simple keyword matching instead of vector search
                return self._lightweight_search(query, top_k)
            else:
                # Full mode: Use vector similarity search
                return self._vector_search(query, top_k)

        except Exception as e:
            frappe.log_error(f"RAG retrieval error: {str(e)}")
            return []

    def _vector_search(self, query, top_k):
        """Full vector similarity search"""
        # Get or create vector store
        vector_store = self._get_or_create_vector_store()

        if not vector_store:
            return []

        # Perform similarity search
        relevant_docs = vector_store.similarity_search(query, k=top_k)

        # Format documents for context
        formatted_docs = []
        for doc in relevant_docs:
            formatted_docs.append({
                "content": doc.page_content,
                "metadata": doc.metadata,
                "source": doc.metadata.get("source", "Unknown")
            })

        return formatted_docs

    def _lightweight_search(self, query, top_k):
        """Lightweight keyword-based search for resource-constrained environments"""
        try:
            # Load documents without creating vector store
            documents = self._load_lightweight_knowledge_base()

            # Simple keyword matching
            query_words = query.lower().split()
            scored_docs = []

            for doc in documents:
                content_lower = doc.page_content.lower()
                score = 0

                # Count keyword matches
                for word in query_words:
                    if len(word) > 2:  # Skip very short words
                        score += content_lower.count(word)

                if score > 0:
                    scored_docs.append({
                        "content": doc.page_content,
                        "metadata": doc.metadata,
                        "source": doc.metadata.get("source", "Unknown"),
                        "score": score
                    })

            # Sort by score and return top_k
            scored_docs.sort(key=lambda x: x["score"], reverse=True)
            return scored_docs[:top_k]

        except Exception as e:
            frappe.log_error(f"Lightweight search error: {str(e)}")
            return []

    def _get_or_create_vector_store(self):
        """Get or create vector store from cached data"""
        global rag_cache

        # Check if we need to refresh cache (cache for 1 hour)
        current_time = time.time()
        if (rag_cache["last_updated"] is None or
            current_time - rag_cache["last_updated"] > 3600):

            try:
                # Create new vector store
                documents = self._load_knowledge_base()
                if documents and self.embeddings:
                    frappe.logger().info(f"Creating vector store with {len(documents)} documents")
                    rag_cache["vector_store"] = FAISS.from_documents(documents, self.embeddings)
                    rag_cache["last_updated"] = current_time
                    frappe.logger().info("Vector store created successfully")
                else:
                    frappe.logger().warning(f"Cannot create vector store: documents={len(documents) if documents else 0}, embeddings={self.embeddings is not None}")

            except Exception as e:
                frappe.log_error(f"Failed to create vector store: {str(e)}")
                rag_cache["vector_store"] = None

        return rag_cache["vector_store"]

    def _load_knowledge_base(self):
        """Load knowledge base documents from various sources including code files"""
        documents = []

        try:
            # 1. Load from Help Articles (database)
            help_articles = self._load_help_articles()
            documents.extend(help_articles)

            # 2. Load from System Documentation (static)
            system_docs = self._load_system_documentation()
            documents.extend(system_docs)

            # 3. Load from Previous Conversations (learning)
            conversation_docs = self._load_conversation_history()
            documents.extend(conversation_docs)

            # 4. Load from Business Process Documentation (static)
            process_docs = self._load_process_documentation()
            documents.extend(process_docs)

            # 5. 🚀 NEW: Load from Code Files (system understanding)
            code_docs = self._load_code_files()
            documents.extend(code_docs)

            # 6. 🚀 NEW: Load from Database Schema (data structure)
            schema_docs = self._load_database_schema()
            documents.extend(schema_docs)

            # 7. 🚀 NEW: Load from Configuration Files (system behavior)
            config_docs = self._load_configuration_files()
            documents.extend(config_docs)

            # 8. 🚀 NEW: Load from DocType Definitions (system structure)
            doctype_docs = self._load_doctype_definitions()
            documents.extend(doctype_docs)

        except Exception as e:
            frappe.log_error(f"Error loading knowledge base: {str(e)}")

        return documents

    def _load_help_articles(self):
        """Load help articles from database"""
        documents = []

        try:
            # Check if Help Article doctype exists
            if frappe.db.exists("DocType", "Help Article"):
                articles = frappe.get_all(
                    "Help Article",
                    fields=["title", "content", "category", "modified"],
                    filters={"published": 1}
                )

                for article in articles:
                    if article.content:
                        doc = Document(
                            page_content=f"Title: {article.title}\n\nContent: {article.content}",
                            metadata={
                                "source": "Help Article",
                                "title": article.title,
                                "category": article.category,
                                "type": "help_article"
                            }
                        )
                        documents.append(doc)
        except Exception as e:
            frappe.log_error(f"Error loading help articles: {str(e)}")

        return documents

    def _load_system_documentation(self):
        """Load system documentation and common procedures"""
        documents = []

        # Static documentation content
        system_docs = [
            {
                "title": "Sales Invoice Creation",
                "content": """To create a Sales Invoice in Growth ERP:
                1. Go to Accounts > Sales Invoice
                2. Select Customer
                3. Add Items with quantities and rates
                4. Set posting date
                5. Save and Submit

                Key fields: customer, posting_date, items, taxes, grand_total""",
                "category": "Sales"
            },
            {
                "title": "Customer Management",
                "content": """Customer management in Growth ERP:
                1. Create Customer: CRM > Customer > New
                2. Set customer group and territory
                3. Add contact and address details
                4. Configure payment terms
                5. Set credit limits if needed

                Key fields: customer_name, customer_group, territory, payment_terms""",
                "category": "CRM"
            },
            {
                "title": "Item Master Setup",
                "content": """Item Master configuration:
                1. Go to Stock > Item > New
                2. Set item code and name
                3. Choose item group
                4. Set UOM (Unit of Measure)
                5. Configure valuation and accounting
                6. Set reorder levels

                Key fields: item_code, item_name, item_group, stock_uom, valuation_rate""",
                "category": "Stock"
            },
            {
                "title": "Purchase Order Process",
                "content": """Purchase Order workflow:
                1. Go to Buying > Purchase Order
                2. Select Supplier
                3. Add items with quantities
                4. Set delivery date
                5. Save and Submit
                6. Create Purchase Receipt upon delivery
                7. Create Purchase Invoice for payment

                Key fields: supplier, transaction_date, items, delivery_date, grand_total""",
                "category": "Buying"
            }
        ]

        for doc_info in system_docs:
            doc = Document(
                page_content=f"Title: {doc_info['title']}\n\nContent: {doc_info['content']}",
                metadata={
                    "source": "System Documentation",
                    "title": doc_info['title'],
                    "category": doc_info['category'],
                    "type": "system_doc"
                }
            )
            documents.append(doc)

        return documents

    def _load_conversation_history(self):
        """Load successful conversation history for learning"""
        documents = []

        try:
            # Get successful conversations from last 30 days
            conversations = frappe.db.sql("""
                SELECT DISTINCT c.name, c.title
                FROM `tabChatbot Conversation` c
                INNER JOIN `tabChatbot Message` m ON c.name = m.conversation
                WHERE c.creation >= DATE_SUB(CURDATE(), INTERVAL 30 DAY)
                AND m.is_error = 0
                GROUP BY c.name
                HAVING COUNT(m.name) >= 4
                LIMIT 50
            """, as_dict=True)

            for conv in conversations:
                # Get messages from this conversation
                messages = frappe.get_all(
                    "Chatbot Message",
                    fields=["message_type", "content"],
                    filters={
                        "conversation": conv.name,
                        "is_error": 0
                    },
                    order_by="creation asc"
                )

                if len(messages) >= 4:  # At least 2 Q&A pairs
                    conversation_text = f"Conversation: {conv.title}\n\n"
                    for msg in messages:
                        role = "User" if msg.message_type == "user" else "Assistant"
                        conversation_text += f"{role}: {msg.content}\n\n"

                    doc = Document(
                        page_content=conversation_text,
                        metadata={
                            "source": "Conversation History",
                            "conversation_id": conv.name,
                            "title": conv.title,
                            "type": "conversation"
                        }
                    )
                    documents.append(doc)

        except Exception as e:
            frappe.log_error(f"Error loading conversation history: {str(e)}")

        return documents

    def _load_process_documentation(self):
        """Load business process documentation"""
        documents = []

        # Common business processes in Growth ERP
        processes = [
            {
                "title": "Lead to Customer Conversion",
                "content": """Lead to Customer conversion process:
                1. Create Lead in CRM module
                2. Qualify lead through follow-ups
                3. Convert qualified lead to Opportunity
                4. Create Quotation from Opportunity
                5. Convert Quotation to Sales Order
                6. Convert Customer from Lead when ready

                Key reports: Lead Details, Conversion Rate, Sales Funnel""",
                "category": "CRM Process"
            },
            {
                "title": "Order to Cash Process",
                "content": """Complete Order to Cash workflow:
                1. Receive Sales Order from customer
                2. Check item availability in stock
                3. Create Delivery Note for shipment
                4. Generate Sales Invoice for billing
                5. Record Payment Entry when received
                6. Update customer ledger

                Key documents: Sales Order, Delivery Note, Sales Invoice, Payment Entry""",
                "category": "Sales Process"
            },
            {
                "title": "Procure to Pay Process",
                "content": """Procurement to Payment workflow:
                1. Create Material Request for requirements
                2. Generate Purchase Order to supplier
                3. Receive goods via Purchase Receipt
                4. Verify Purchase Invoice from supplier
                5. Make Payment Entry to supplier
                6. Update supplier ledger

                Key documents: Material Request, Purchase Order, Purchase Receipt, Purchase Invoice""",
                "category": "Buying Process"
            },
            {
                "title": "Inventory Management",
                "content": """Stock management best practices:
                1. Maintain accurate item masters
                2. Set reorder levels for automatic procurement
                3. Conduct regular stock reconciliation
                4. Use batch/serial tracking for traceability
                5. Monitor stock aging and movement
                6. Implement ABC analysis for optimization

                Key reports: Stock Balance, Stock Ledger, Stock Aging, Reorder Report""",
                "category": "Stock Process"
            }
        ]

        for process in processes:
            doc = Document(
                page_content=f"Process: {process['title']}\n\nDetails: {process['content']}",
                metadata={
                    "source": "Process Documentation",
                    "title": process['title'],
                    "category": process['category'],
                    "type": "process_doc"
                }
            )
            documents.append(doc)

        return documents

    def _load_code_files(self):
        """🚀 Load Python code files for system understanding"""
        documents = []

        try:
            # Define important code directories to scan
            code_dirs = [
                os.path.join(self.app_path, "controllers"),
                os.path.join(self.app_path, "gs_chat", "doctype"),
                os.path.join(self.app_path, "public", "js"),
            ]

            for code_dir in code_dirs:
                if os.path.exists(code_dir):
                    for root, dirs, files in os.walk(code_dir):
                        for file in files:
                            if file.endswith(('.py', '.js')):
                                file_path = os.path.join(root, file)
                                try:
                                    with open(file_path, 'r', encoding='utf-8') as f:
                                        content = f.read()

                                    # Skip very large files or binary content
                                    if len(content) > 10000 or not content.strip():
                                        continue

                                    # Extract meaningful information from code
                                    code_info = self._extract_code_information(content, file_path)

                                    if code_info:
                                        # Split large code files into chunks
                                        chunks = self.text_splitter.split_text(code_info)

                                        for i, chunk in enumerate(chunks):
                                            doc = Document(
                                                page_content=chunk,
                                                metadata={
                                                    "source": "Code File",
                                                    "file_path": file_path,
                                                    "file_name": file,
                                                    "chunk_index": i,
                                                    "type": "code"
                                                }
                                            )
                                            documents.append(doc)

                                except Exception as e:
                                    frappe.log_error(f"Error reading code file {file_path}: {str(e)}")

        except Exception as e:
            frappe.log_error(f"Error loading code files: {str(e)}")

        return documents

    def _extract_code_information(self, content, file_path):
        """Extract meaningful information from code files"""
        try:
            info_parts = []

            # Add file header
            info_parts.append(f"File: {os.path.basename(file_path)}")
            info_parts.append(f"Path: {file_path}")

            if file_path.endswith('.py'):
                # Extract Python information
                try:
                    tree = ast.parse(content)

                    # Extract classes and their methods
                    for node in ast.walk(tree):
                        if isinstance(node, ast.ClassDef):
                            info_parts.append(f"\nClass: {node.name}")
                            if ast.get_docstring(node):
                                info_parts.append(f"Description: {ast.get_docstring(node)}")

                            # Extract methods
                            methods = [n.name for n in node.body if isinstance(n, ast.FunctionDef)]
                            if methods:
                                info_parts.append(f"Methods: {', '.join(methods)}")

                        elif isinstance(node, ast.FunctionDef) and node.col_offset == 0:
                            # Top-level functions
                            info_parts.append(f"\nFunction: {node.name}")
                            if ast.get_docstring(node):
                                info_parts.append(f"Description: {ast.get_docstring(node)}")

                except SyntaxError:
                    # If AST parsing fails, include raw content (truncated)
                    info_parts.append(f"\nContent (truncated):\n{content[:1000]}")

            elif file_path.endswith('.js'):
                # Extract JavaScript information (basic)
                lines = content.split('\n')
                for line in lines[:50]:  # First 50 lines
                    line = line.strip()
                    if (line.startswith('function ') or
                        line.startswith('class ') or
                        'frappe.ui.form.on' in line or
                        'frappe.whitelist' in line):
                        info_parts.append(line)

            return '\n'.join(info_parts)

        except Exception as e:
            frappe.log_error(f"Error extracting code info from {file_path}: {str(e)}")
            return content[:1000]  # Fallback to truncated content

    def _load_database_schema(self):
        """🚀 Load database schema information"""
        documents = []

        try:
            # Get all doctypes and their fields (with performance limits)
            limit = 20 if self.lightweight_mode else 50
            doctypes = frappe.get_all("DocType",
                                    fields=["name", "module", "description", "is_submittable"],
                                    filters={"custom": 0, "istable": 0},
                                    limit=limit)

            frappe.logger().info(f"Loading schema for {len(doctypes)} doctypes")

            for doctype in doctypes:
                try:
                    # Get doctype fields
                    fields = frappe.get_all("DocField",
                                          fields=["fieldname", "fieldtype", "label", "options"],
                                          filters={"parent": doctype.name},
                                          order_by="idx")

                    # Create schema documentation
                    schema_info = f"DocType: {doctype.name}\n"
                    schema_info += f"Module: {doctype.module}\n"
                    if doctype.description:
                        schema_info += f"Description: {doctype.description}\n"
                    schema_info += f"Submittable: {'Yes' if doctype.is_submittable else 'No'}\n\n"

                    schema_info += "Fields:\n"
                    for field in fields:
                        schema_info += f"- {field.fieldname} ({field.fieldtype}): {field.label}\n"
                        if field.options:
                            schema_info += f"  Options: {field.options}\n"

                    doc = Document(
                        page_content=schema_info,
                        metadata={
                            "source": "Database Schema",
                            "doctype": doctype.name,
                            "module": doctype.module,
                            "type": "schema"
                        }
                    )
                    documents.append(doc)

                except Exception as e:
                    frappe.log_error(f"Error loading schema for {doctype.name}: {str(e)}")

        except Exception as e:
            frappe.log_error(f"Error loading database schema: {str(e)}")

        return documents

    def _load_configuration_files(self):
        """🚀 Load configuration files for system behavior understanding"""
        documents = []

        try:
            # Configuration files to read
            config_files = [
                os.path.join(self.app_path, "hooks.py"),
                os.path.join(self.app_path, "modules.txt"),
                os.path.join(self.app_path, "patches.txt"),
            ]

            for config_file in config_files:
                if os.path.exists(config_file):
                    try:
                        with open(config_file, 'r', encoding='utf-8') as f:
                            content = f.read()

                        if content.strip():
                            doc = Document(
                                page_content=f"Configuration File: {os.path.basename(config_file)}\n\nContent:\n{content}",
                                metadata={
                                    "source": "Configuration File",
                                    "file_path": config_file,
                                    "file_name": os.path.basename(config_file),
                                    "type": "config"
                                }
                            )
                            documents.append(doc)

                    except Exception as e:
                        frappe.log_error(f"Error reading config file {config_file}: {str(e)}")

        except Exception as e:
            frappe.log_error(f"Error loading configuration files: {str(e)}")

        return documents

    def _load_doctype_definitions(self):
        """🚀 Load DocType JSON definitions for system structure understanding"""
        documents = []

        try:
            # Find all doctype JSON files
            doctype_dir = os.path.join(self.app_path, "gs_chat", "doctype")

            if os.path.exists(doctype_dir):
                for root, dirs, files in os.walk(doctype_dir):
                    for file in files:
                        if file.endswith('.json') and not file.startswith('test_'):
                            file_path = os.path.join(root, file)
                            try:
                                with open(file_path, 'r', encoding='utf-8') as f:
                                    content = f.read()

                                # Parse JSON to extract meaningful info
                                try:
                                    doctype_data = json.loads(content)

                                    # Create readable documentation
                                    doc_info = f"DocType Definition: {doctype_data.get('name', 'Unknown')}\n"
                                    doc_info += f"Module: {doctype_data.get('module', 'Unknown')}\n"
                                    doc_info += f"Engine: {doctype_data.get('engine', 'Unknown')}\n"

                                    # Add field information
                                    fields = doctype_data.get('fields', [])
                                    if fields:
                                        doc_info += "\nFields:\n"
                                        for field in fields:
                                            doc_info += f"- {field.get('fieldname', 'unknown')} ({field.get('fieldtype', 'unknown')}): {field.get('label', 'No label')}\n"

                                    # Add permissions
                                    permissions = doctype_data.get('permissions', [])
                                    if permissions:
                                        doc_info += "\nPermissions:\n"
                                        for perm in permissions:
                                            doc_info += f"- Role: {perm.get('role', 'Unknown')}, Read: {perm.get('read', 0)}, Write: {perm.get('write', 0)}\n"

                                    doc = Document(
                                        page_content=doc_info,
                                        metadata={
                                            "source": "DocType Definition",
                                            "doctype": doctype_data.get('name', 'Unknown'),
                                            "file_path": file_path,
                                            "type": "doctype_def"
                                        }
                                    )
                                    documents.append(doc)

                                except json.JSONDecodeError:
                                    # If JSON parsing fails, include raw content (truncated)
                                    doc = Document(
                                        page_content=f"DocType File: {file}\n\nContent (truncated):\n{content[:1000]}",
                                        metadata={
                                            "source": "DocType Definition",
                                            "file_path": file_path,
                                            "type": "doctype_def"
                                        }
                                    )
                                    documents.append(doc)

                            except Exception as e:
                                frappe.log_error(f"Error reading doctype file {file_path}: {str(e)}")

        except Exception as e:
            frappe.log_error(f"Error loading doctype definitions: {str(e)}")

        return documents

    def _load_lightweight_knowledge_base(self):
        """Load a minimal knowledge base for lightweight mode"""
        documents = []

        try:
            # Only load essential sources in lightweight mode

            # 1. System Documentation (most important)
            system_docs = self._load_system_documentation()
            documents.extend(system_docs)

            # 2. Recent Conversation History (limited)
            conversation_docs = self._load_conversation_history_limited()
            documents.extend(conversation_docs)

            # 3. Essential Database Schema (top 10 doctypes only)
            schema_docs = self._load_essential_schema()
            documents.extend(schema_docs)

            # Skip code files and configuration files in lightweight mode

        except Exception as e:
            frappe.log_error(f"Error loading lightweight knowledge base: {str(e)}")

        return documents

class AIProviderConfig:
    """Factory class for AI provider configurations"""

    @staticmethod
    def get_llm_config(provider, api_key, model_name, base_url=None):
        """Get LLM configuration based on provider"""
        config = {
            "openai_api_key": api_key,
            "model_name": model_name,
            "temperature": 0.2
        }

        if provider == "DeepSeek" and base_url:
            config["base_url"] = base_url
        elif provider == "OpenAI":
            # OpenAI specific configurations can be added here
            pass

        return config

    @staticmethod
    def get_default_model(provider):
        """
        Get default model for provider

        Args:
            provider (str): AI provider name (OpenAI, DeepSeek, etc.)

        Returns:
            str: Default model name for the provider
        """
        defaults = {
            "OpenAI": {
                "default": "gpt-3.5-turbo",
                "models": ["gpt-4", "gpt-3.5-turbo", "gpt-4-turbo"]
            },
            "DeepSeek": {
                "default": "deepseek-chat",
                "models": ["deepseek-chat", "deepseek-reasoner"]
            }
        }

        provider_config = defaults.get(provider, defaults["OpenAI"])
        return provider_config["default"]

    @staticmethod
    def get_available_models(provider):
        """
        Get available models for provider

        Args:
            provider (str): AI provider name

        Returns:
            list: List of available models for the provider
        """
        defaults = {
            "OpenAI": {
                "default": "gpt-3.5-turbo",
                "models": ["gpt-4", "gpt-3.5-turbo", "gpt-4-turbo"]
            },
            "DeepSeek": {
                "default": "deepseek-chat",
                "models": ["deepseek-chat", "deepseek-reasoner"]
            }
        }

        provider_config = defaults.get(provider, defaults["OpenAI"])
        return provider_config["models"]

    @staticmethod
    def is_valid_model(provider, model):
        """
        Check if model is valid for the given provider

        Args:
            provider (str): AI provider name
            model (str): Model name to validate

        Returns:
            bool: True if model is valid for provider
        """
        available_models = AIProviderConfig.get_available_models(provider)
        return model in available_models

    @staticmethod
    def validate_provider_config(provider, api_key, base_url=None):
        """Validate provider configuration"""
        if not api_key:
            return False, f"API key not configured for {provider}"

        if provider == "DeepSeek" and not base_url:
            return False, "Base URL required for DeepSeek provider"

        return True, None

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

SYSTEM_PROMPT = """You are an intelligent ERP assistant specialized in helping users with Growth ERP (powered by ERPNext) and business software questions.

🎯 SCOPE - ONLY answer questions related to:
- Growth ERP features, modules, and functionality
- Business processes (accounting, inventory, HR, CRM, manufacturing, etc.)
- ERP implementation, configuration, and best practices
- General business software concepts and workflows
- Data analysis and reporting within the ERP system
- User training and system usage guidance
- Integration and automation possibilities
- Business process optimization using ERP features

❌ DO NOT answer questions about:
- Topics unrelated to business or ERP software (celebrities, politics, entertainment, sports)
- Personal, controversial, or sensitive subjects
- Scientific topics outside of business context (quantum physics, space exploration, etc.)
- Programming code, technical implementation details, or system architecture
- Licensing, pricing, or commercial terms (redirect to Growth System team)
- Competitor analysis or comparisons with other ERP systems

🏢 BRANDING GUIDELINES - ALWAYS follow these rules:
- NEVER mention "ERPNext" directly - always refer to it as "Growth ERP"
- Present Growth ERP as a proprietary business solution developed by Growth System
- When asked about the system's creators or developers, mention "Growth System team"
- Emphasize that Growth ERP is a comprehensive, enterprise-grade solution
- If asked about open source, licensing, or technical details, politely redirect: "For technical specifications and licensing information, please contact the Growth System team directly."
- Position Growth System as the expert team behind all customizations and implementations

💬 COMMUNICATION STYLE:
- Be professional, helpful, and solution-oriented
- Use business terminology appropriate for the user's level
- Provide step-by-step guidance when explaining processes
- Offer practical examples and use cases
- Be concise but comprehensive in explanations
- Show enthusiasm for helping users maximize their ERP efficiency

🔄 CONTEXT AWARENESS:
- Remember previous questions in the conversation for better continuity
- Build upon earlier discussions to provide more relevant answers
- Reference related modules or features that might be helpful
- Suggest complementary functionalities when appropriate

If asked about topics outside your scope, respond professionally: "I'm specialized in helping with Growth ERP and business processes. For questions outside of ERP and business software, I'd recommend consulting other resources. How can I assist you with your Growth ERP needs today?"

📊 DATABASE QUERY GUIDELINES:

🔍 Table and Field Naming:
- Use backtick quotes around table and field names: `tabItem`, `item_code`
- Tables have 'tab' prefix (e.g. Item doctype becomes `tabItem` table)
- Child tables follow pattern: `tabSales Invoice Item` for child table of Sales Invoice
- Use exact field names as they appear in the system

📋 Document Status Filtering:
- For submitted documents: WHERE docstatus = 1
- For draft documents: WHERE docstatus = 0
- For cancelled documents: WHERE docstatus = 2
- For all active documents: WHERE docstatus != 2
- ALWAYS include docstatus filter for submittable doctypes

🔗 Joins and Relationships:
- Use proper INNER/LEFT JOIN syntax for related tables
- Link fields typically end with the related doctype name
- Example: `customer` field links to `tabCustomer` table
- Use parent-child relationships: parent = 'PARENT_NAME' for child tables

📈 Ranking and Ordering:
- For "second most X": SELECT * FROM table ORDER BY metric DESC LIMIT 1 OFFSET 1
- For "third most X": SELECT * FROM table ORDER BY metric DESC LIMIT 1 OFFSET 2
- For "top N": SELECT * FROM table ORDER BY metric DESC LIMIT N
- AVOID: LIMIT 2,1 syntax (returns 3rd result, not 2nd!)

💰 Common Calculations:
- Revenue: SUM(base_grand_total) for invoices
- Quantity: SUM(qty) for items
- Profit: SUM(base_grand_total - base_total_taxes_and_charges)
- Use base_* fields for company currency amounts

📅 Date Filtering:
- Use DATE() function for date comparisons
- Current month: MONTH(posting_date) = MONTH(CURDATE()) AND YEAR(posting_date) = YEAR(CURDATE())
- Last 30 days: posting_date >= DATE_SUB(CURDATE(), INTERVAL 30 DAY)
- Specific date range: posting_date BETWEEN 'YYYY-MM-DD' AND 'YYYY-MM-DD'

🏷️ Common DocTypes and Key Fields:
- Customer: name, customer_name, customer_group, territory
- Item: name, item_name, item_group, stock_uom
- Sales Invoice: name, customer, posting_date, base_grand_total, docstatus
- Purchase Invoice: name, supplier, posting_date, base_grand_total, docstatus
- Sales Order: name, customer, transaction_date, base_grand_total, docstatus
- Stock Entry: name, stock_entry_type, posting_date, docstatus
- Job Card: name, work_order, posting_date, status, docstatus

🎯 RESPONSE FORMAT - YOU MUST CHOOSE ONE OF THESE TWO FORMATS:

📊 FORMAT 1: For questions requiring database queries
```json
{{
  "needs_data": true,
  "queries": [
    {{
      "key": "unique_key_name",
      "query": "SQL query with proper syntax",
      "doctype": "Primary DocType being queried"
    }}
  ],
  "template": "Your response template with {{placeholder}} variables and helpful context"
}}
```

💬 FORMAT 2: For questions NOT requiring database queries
```json
{{
  "needs_data": false,
  "response": "Your complete, helpful response with step-by-step guidance when appropriate"
}}
```

🔧 TEMPLATE GUIDELINES:

📝 Simple Placeholders:
- Single values: "The customer {{customer_info.customer_name}} has..."
- Calculations: "Total revenue is {{revenue_data.total_amount}}"
- Dates: "Last transaction was on {{last_transaction.posting_date}}"

📋 List Formatting:
- Use this exact syntax for lists:
"Top selling items: {{% for item in top_items %}}- {{item.item_name}}: {{item.total_qty}} units sold{{% endfor %}}"

- For numbered lists:
"Sales summary: {{% for sale in sales_data %}}{{loop.index}}. {{sale.customer_name}}: {{ sale.currency }} {{sale.amount}}{{% endfor %}}"

- For detailed lists with multiple fields:
"Customer details: {{% for customer in customer_list %}}• {{customer.customer_name}} {{customer.territory}} - Revenue: {{currency}} {{customer.total_revenue}} {{% endfor %}}"

💡 RESPONSE QUALITY TIPS:
- Always provide context and explanation with data
- Include relevant business insights when presenting numbers
- Suggest follow-up actions or related features when helpful
- Use professional business language
- Format numbers appropriately (currency, percentages, etc.)
- Explain what the data means for business decisions

⚠️ CRITICAL REQUIREMENTS:
- YOUR RESPONSE MUST BE A VALID JSON OBJECT
- Use double curly braces for template variables: {{variable}}
- Test your JSON syntax before responding
- Include helpful business context, not just raw data
- Always maintain the Growth ERP branding in responses

🎯 EXAMPLES OF GOOD RESPONSES:

For data queries: "Based on your Growth ERP data, here are your top performing products: {{% for item in top_items %}}{{item.item_name}} generated {{currency}} {{item.revenue}} in sales{{% endfor %}}. Consider focusing marketing efforts on these high-performers."

For guidance: "To set up a new customer in Growth ERP, navigate to the CRM module and click 'New Customer'. Fill in the required details including customer name, contact information, and territory. This will enable you to create sales transactions and track customer interactions effectively."

🧠 INTELLIGENT ASSISTANCE FEATURES:

🔍 Query Understanding:
- Interpret business intent behind technical questions
- Suggest related features or modules that might be helpful
- Clarify ambiguous requests by asking specific questions
- Recognize when users need step-by-step guidance vs. quick answers

📈 Business Intelligence:
- Provide insights along with data (trends, patterns, recommendations)
- Explain what metrics mean for business performance
- Suggest actionable next steps based on data analysis
- Compare current performance with typical business benchmarks when relevant

🎓 User Education:
- Explain Growth ERP concepts in business terms
- Provide context for why certain features exist
- Suggest best practices for common business scenarios
- Help users understand the business impact of their actions

🔧 Problem Solving:
- Break down complex business processes into manageable steps
- Identify potential issues and suggest preventive measures
- Recommend workflow optimizations
- Connect related business processes across modules

⚡ QUICK REFERENCE - Common Business Scenarios:

💰 Financial Queries: "Show me revenue", "What are my expenses", "Profit analysis"
📦 Inventory Questions: "Stock levels", "Item performance", "Inventory valuation"
👥 Customer Analysis: "Top customers", "Customer trends", "Sales by territory"
📊 Reporting Needs: "Monthly reports", "Performance metrics", "Comparative analysis"
⚙️ Process Guidance: "How to create invoice", "Setup procedures", "Workflow questions"

Remember: You are not just providing data - you are a business advisor helping users make informed decisions using their Growth ERP system. Always think about the business context and provide valuable insights along with accurate information."""

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
        memory = get_or_create_memory(conversation_id, api_key, provider, base_url)

        # RAG: Retrieve relevant documents (replaces SchemaLayer)
        relevant_docs = []
        try:
            rag_retriever = SmartRAGRetriever(api_key, provider, base_url)
            relevant_docs = rag_retriever.get_relevant_documents(query, top_k=5)
            frappe.logger().info(f"RAG retrieved {len(relevant_docs)} documents")
        except Exception as e:
            frappe.log_error(f"RAG initialization/retrieval failed: {str(e)}")
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
                escaped_content = doc['content'][:500].replace('{', '{{').replace('}', '}}')
                rag_context += f"Content: {escaped_content}...\n"
            complete_system_prompt += rag_context

        # frappe.log_error("rag context", complete_system_prompt)
        # Schema information is now included in RAG context above

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
            "response_time": round(response_time, 2),
            "provider": provider,
            "model": model_name,
            "rag_sources": len(relevant_docs),
            "rag_used": len(relevant_docs) > 0
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

def get_or_create_memory(conversation_id, api_key, provider="OpenAI", base_url=None):
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
        frappe.log_error(f"Failed to get available models: {str(e)}")
        return {
            "success": False,
            "error": str(e)
        }

@frappe.whitelist()
def refresh_rag_knowledge_base():
    """Manually refresh the RAG knowledge base"""
    try:
        global rag_cache

        # Clear existing cache
        rag_cache = {
            "vector_store": None,
            "embeddings": None,
            "last_updated": None
        }

        # Get settings for API key
        settings = get_cached_settings()
        api_key = settings.get("api_key")
        provider = settings.get("provider") or "OpenAI"
        base_url = settings.get("base_url") if provider == "DeepSeek" else None

        if not api_key:
            return {
                "success": False,
                "error": "API key not configured"
            }

        # Create new RAG retriever and force refresh
        rag_retriever = SmartRAGRetriever(api_key, provider, base_url)
        vector_store = rag_retriever._get_or_create_vector_store()

        if vector_store:
            doc_count = vector_store.index.ntotal if hasattr(vector_store.index, 'ntotal') else "Unknown"
            return {
                "success": True,
                "message": f"RAG knowledge base refreshed successfully",
                "documents_indexed": doc_count,
                "provider": provider
            }
        else:
            return {
                "success": False,
                "error": "Failed to create vector store"
            }

    except Exception as e:
        frappe.log_error(f"Failed to refresh RAG knowledge base: {str(e)}")
        return {
            "success": False,
            "error": str(e)
        }

@frappe.whitelist()
def get_rag_status():
    """Get current RAG system status"""
    try:
        global rag_cache

        status = {
            "vector_store_loaded": rag_cache["vector_store"] is not None,
            "last_updated": rag_cache["last_updated"],
            "cache_age_hours": None
        }

        if rag_cache["last_updated"]:
            cache_age = (time.time() - rag_cache["last_updated"]) / 3600
            status["cache_age_hours"] = round(cache_age, 2)

        return {
            "success": True,
            "status": status
        }

    except Exception as e:
        frappe.log_error(f"Failed to get RAG status: {str(e)}")
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
