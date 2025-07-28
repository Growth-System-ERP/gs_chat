import frappe
from langchain.chat_models import ChatOpenAI
from langchain.prompts import PromptTemplate
from langchain.chains import LLMChain

# This template helps convert natural language into SQL queries
template = """
You are an expert ERPNext analyst. Convert the following question into a valid SQL query
that works on the ERPNext MariaDB schema. Use extreme caution while returning the sql query to use fields and doctypes and joins.
Question: {question}
SQL Query:
"""

prompt = PromptTemplate(
    input_variables=["question"],
    template=template.strip()
)

# Get settings for API configuration
settings = frappe.get_doc("Chatbot Settings")
api_key = settings.get("api_key")
provider = settings.get("provider") or "OpenAI"
base_url = settings.get("base_url") if provider == "DeepSeek" else None

# Create LLM instance with provider-specific configuration
llm_kwargs = {
    "temperature": 0,
    "openai_api_key": api_key
}

# Add base_url for DeepSeek
if provider == "DeepSeek" and base_url:
    llm_kwargs["base_url"] = base_url

llm = ChatOpenAI(**llm_kwargs)
chain = LLMChain(llm=llm, prompt=prompt)

@frappe.whitelist()
def generate_sql(question: str) -> str:
    return chain.run({"question": question})

@frappe.whitelist()
def get_sql_answer(question: str) -> str:
    sql_query = generate_sql(question)

    return frappe.db.sql(sql_query)

# from langchain.chat_models import ChatOpenAI
# from langchain.prompts import PromptTemplate
# from langchain.chains import LLMChain
# from sqlalchemy import create_engine, text, inspect
# import os

# # Database connection via SQLAlchemy
# DB_URI = os.getenv("ERP_DB_URI", "mysql+pymysql://user:password@localhost:3306/erpnext")
# engine = create_engine(DB_URI)
# inspector = inspect(engine)

# # Introspect key ERPNext tables to guide SQL generation
# tables = [
#     "tabSales Invoice",
#     "tabSales Invoice Item",
#     "tabItem",
#     "tabBin",
#     "tabStock Ledger Entry"
# ]
# schema_info = {}
# for tbl in tables:
#     try:
#         cols = inspector.get_columns(tbl)
#         schema_info[tbl] = [col["name"] for col in cols]
#     except Exception:
#         # table may not exist or permission issue
#         schema_info[tbl] = []

# # Build a schema description for the prompt
# schema_lines = []
# for tbl, cols in schema_info.items():
#     schema_lines.append(f"{tbl}: {', '.join(cols) if cols else 'no metadata available'}")
# schema_description = "\n".join(schema_lines)

# # Prompt template with injected schema
# prompt_template = f"""
# You are a skilled ERPNext database analyst. Use the following table schemas to write a valid SQL query in MariaDB syntax.

# {schema_description}

# Translate the user's question into one clear SQL query. Avoid unnecessary joins; only use tables provided above. Do not include explanations—output only the SQL.

# Question: {{question}}
# SQL Query:
# """

# prompt = PromptTemplate(
#     input_variables=["question"],
#     template=prompt_template.strip()
# )

# llm = ChatOpenAI(temperature=0)
# chain = LLMChain(llm=llm, prompt=prompt)

# def generate_sql(question: str) -> str:
#     """
#     Generate a SQL query string based on the user's question.
#     """
#     raw = chain.run({"question": question})
#     # Clean code fences if present
#     return raw.strip().strip("```sql").strip("```")


# def get_sql_answer(question: str) -> str:
#     """
#     Execute the generated SQL against the ERPNext database and return formatted results.
#     """
#     sql_query = generate_sql(question)
#     with engine.connect() as conn:
#         result = conn.execute(text(sql_query)).fetchall()
#     # Format rows for readability
#     return "\n".join(str(row) for row in result)
