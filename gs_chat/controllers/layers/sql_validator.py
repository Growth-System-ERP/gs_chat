"""
SQL Validator for GS Chat
Ensures only safe read operations and controlled record creation
"""

import re
import frappe
from frappe import _

class SQLValidator:
    """Validates SQL queries for safety and permissions"""

    # Dangerous keywords that should never be allowed
    FORBIDDEN_KEYWORDS = [
        r'\b(DELETE|DROP|TRUNCATE|ALTER|UPDATE|GRANT|REVOKE|CREATE\s+DATABASE|DROP\s+DATABASE)\b',
        r'\b(EXEC|EXECUTE|XP_|SP_)\b',  # Stored procedures
        r'(--|#|\/\*)',  # SQL comments that could hide injections
    ]

    # Only allow these specific operations
    ALLOWED_OPERATIONS = {
        'SELECT': 'read',
        'INSERT': 'create',  # Only for specific doctypes
        'SHOW': 'read',
        'DESCRIBE': 'read',
    }

    # DocTypes allowed for INSERT operations
    ALLOWED_INSERT_DOCTYPES = [
        'Lead', 'Opportunity', 'Customer', 'Supplier',
        'Item', 'Task', 'Event', 'Note'
    ]

    def __init__(self):
        self.user = frappe.session.user

    def validate_query(self, query, doctype=None):
        """
        Validate SQL query for safety and permissions

        Args:
            query: SQL query string
            doctype: Primary doctype being accessed

        Returns:
            tuple: (is_valid, error_message)
        """
        if not query:
            return False, "Empty query"

        query_upper = query.upper().strip()

        # Check for forbidden operations
        for pattern in self.FORBIDDEN_KEYWORDS:
            if re.search(pattern, query_upper, re.IGNORECASE):
                return False, f"Forbidden operation detected: {pattern}"

        # Determine operation type
        operation = self._get_operation(query_upper)

        if operation not in self.ALLOWED_OPERATIONS:
            return False, f"Operation '{operation}' is not allowed"

        # Handle based on operation type
        if operation == 'SELECT':
            return self._validate_select(query, doctype)
        elif operation == 'INSERT':
            return self._validate_insert(query, doctype)
        else:
            # SHOW, DESCRIBE - generally safe
            return True, None

    def _get_operation(self, query):
        """Extract the main operation from query"""
        first_word = query.split()[0] if query.split() else ""
        return first_word

    def _validate_select(self, query, doctype):
        """Validate SELECT queries"""
        # Extract table names from query
        tables = self._extract_tables(query)

        # Check permissions for each table
        for table in tables:
            doctype_name = self._table_to_doctype(table)
            if doctype_name and not frappe.has_permission(doctype_name, "read"):
                return False, f"No read permission for {doctype_name}"

        # Additional safety checks
        if 'INTO OUTFILE' in query.upper():
            return False, "File operations not allowed"

        return True, None

    def _validate_insert(self, query, doctype):
        """Validate INSERT queries - only for allowed doctypes"""
        if not doctype:
            # Try to extract from query
            match = re.search(r'INTO\s+`?tab(\w+)`?', query, re.IGNORECASE)
            if match:
                doctype = match.group(1)

        if not doctype:
            return False, "Cannot determine target doctype for INSERT"

        if doctype not in self.ALLOWED_INSERT_DOCTYPES:
            return False, f"Creating {doctype} records via AI is not allowed"

        if not frappe.has_permission(doctype, "create"):
            return False, f"No create permission for {doctype}"

        # Ensure no system fields are being set
        forbidden_fields = ['docstatus', 'idx', 'lft', 'rgt', '_user_tags', '_liked_by']
        query_lower = query.lower()
        for field in forbidden_fields:
            if field in query_lower:
                return False, f"Cannot set system field: {field}"

        return True, None

    def _extract_tables(self, query):
        """Extract table names from query"""
        tables = set()

        # Pattern for FROM and JOIN clauses
        patterns = [
            r'FROM\s+`?(\w+)`?',
            r'JOIN\s+`?(\w+)`?',
        ]

        for pattern in patterns:
            matches = re.findall(pattern, query, re.IGNORECASE)
            tables.update(matches)

        return tables

    def _table_to_doctype(self, table):
        """Convert table name to doctype"""
        if table.startswith('tab'):
            return table[3:]
        return None

    def create_safe_record(self, doctype, data):
        """
        Safely create a record with validation

        Args:
            doctype: DocType to create
            data: Dictionary of field values

        Returns:
            dict: Result with success status and message/name
        """
        try:
            if doctype not in self.ALLOWED_INSERT_DOCTYPES:
                return {
                    "success": False,
                    "error": f"Creating {doctype} records via AI is not allowed"
                }

            if not frappe.has_permission(doctype, "create"):
                return {
                    "success": False,
                    "error": f"No create permission for {doctype}"
                }

            # Create the document (as draft only)
            doc = frappe.get_doc({
                "doctype": doctype,
                **data
            })

            # Validate
            doc.validate()

            # Insert (never submit via AI)
            doc.insert()

            return {
                "success": True,
                "name": doc.name,
                "message": f"{doctype} {doc.name} created successfully (draft)"
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

# Singleton instance
_validator = None

def get_sql_validator():
    """Get singleton SQL validator instance"""
    global _validator
    if not _validator:
        _validator = SQLValidator()
    return _validator

@frappe.whitelist()
def validate_and_execute_query(query, doctype=None):
    """
    Validate and execute a query with permission checks

    Args:
        query: SQL query to execute
        doctype: Primary doctype being queried

    Returns:
        dict: Result with data or error
    """
    validator = get_sql_validator()

    # Validate query
    is_valid, error = validator.validate_query(query, doctype)

    if not is_valid:
        return {
            "success": False,
            "error": error
        }

    try:
        # Execute query
        result = frappe.db.sql(query, as_dict=True)

        return {
            "success": True,
            "data": result
        }

    except Exception as e:
        frappe.log_error(f"Query execution error: {str(e)}")
        return {
            "success": False,
            "error": f"Query execution failed: {str(e)}"
        }
