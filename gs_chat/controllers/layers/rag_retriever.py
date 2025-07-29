
import frappe
import time
import os
import json
import ast


try:
    from langchain_text_splitters import RecursiveCharacterTextSplitter
except ImportError:
    from langchain.text_splitter import RecursiveCharacterTextSplitter

try:
    from langchain_community.vectorstores import FAISS
except ImportError:
    from langchain.vectorstores import FAISS

try:
    from langchain_openai import OpenAIEmbeddings
except ImportError:
    from langchain.embeddings import OpenAIEmbeddings

try:
    from langchain_core.documents import Document
except ImportError:
    from langchain.schema import Document

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

    def _load_conversation_history_limited(self):
        """Load limited conversation history for lightweight mode"""
        documents = []

        try:
            # Get only recent successful conversations (last 10)
            conversations = frappe.db.sql("""
                SELECT DISTINCT c.name, c.title
                FROM `tabChatbot Conversation` c
                INNER JOIN `tabChatbot Message` m ON c.name = m.conversation
                WHERE c.creation >= DATE_SUB(CURDATE(), INTERVAL 7 DAY)
                AND m.is_error = 0
                GROUP BY c.name
                HAVING COUNT(m.name) >= 4
                ORDER BY c.modified DESC
                LIMIT 10
            """, as_dict=True)

            for conv in conversations:
                # Get messages from this conversation (limit to 10 messages)
                messages = frappe.get_all(
                    "Chatbot Message",
                    fields=["message_type", "content"],
                    filters={
                        "conversation": conv.name,
                        "is_error": 0
                    },
                    order_by="creation asc",
                    limit=10
                )

                if len(messages) >= 4:  # At least 2 Q&A pairs
                    conversation_text = f"Conversation: {conv.title}\n\n"
                    for msg in messages:
                        role = "User" if msg.message_type == "user" else "Assistant"
                        conversation_text += f"{role}: {msg.content[:200]}...\n\n"  # Truncate long messages

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
            frappe.log_error(f"Error loading limited conversation history: {str(e)}")

        return documents

    def _load_essential_schema(self):
        """Load only essential doctypes for lightweight mode"""
        documents = []

        essential_doctypes = [
            "Customer", "Item", "Sales Invoice", "Purchase Invoice",
            "Sales Order", "Purchase Order", "Quotation", "Lead",
            "Opportunity", "Delivery Note", "Purchase Receipt"
        ]

        try:
            for doctype_name in essential_doctypes:
                if not frappe.db.exists("DocType", doctype_name):
                    continue

                # Get basic fields only
                fields = frappe.get_all("DocField",
                                    fields=["fieldname", "fieldtype", "label"],
                                    filters={
                                        "parent": doctype_name,
                                        "fieldtype": ["in", ["Data", "Link", "Currency", "Float", "Int", "Date"]]
                                    },
                                    order_by="idx",
                                    limit=15)

                # Create minimal schema documentation
                schema_info = f"DocType: {doctype_name}\n"
                schema_info += "Key Fields:\n"
                for field in fields:
                    schema_info += f"- {field.fieldname}: {field.label}\n"

                doc = Document(
                    page_content=schema_info,
                    metadata={
                        "source": "Database Schema",
                        "doctype": doctype_name,
                        "type": "schema"
                    }
                )
                documents.append(doc)

        except Exception as e:
            frappe.log_error(f"Error loading essential schema: {str(e)}")

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
