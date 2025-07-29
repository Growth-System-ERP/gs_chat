import frappe
from frappe import _
import json
import re
from typing import Dict, List, Any, Set, Tuple

class SchemaLayer:
    """Class for determining relevant doctypes and providing schema information"""

    # Mapping of common terms to doctypes
    TERM_TO_DOCTYPE_MAP = {
        # Items/Products
        "item": "Item",
        "product": "Item",
        "material": "Item",
        "inventory": "Item",
        "stock": "Item",

        # Customers
        "customer": "Customer",
        "client": "Customer",
        "buyer": "Customer",

        # Sales
        "sale": "Sales Invoice",
        "invoice": "Sales Invoice",
        "order": "Sales Order",
        "quotation": "Quotation",

        # Suppliers
        "supplier": "Supplier",
        "vendor": "Supplier",

        # Employees
        "employee": "Employee",
        "staff": "Employee",
        "worker": "Employee",

        # Accounts
        "account": "Account",
        "ledger": "GL Entry",
        "payment": "Payment Entry",
        "transaction": "GL Entry",

        # Manufacturing
        "production": "Work Order",
        "manufacturing": "Work Order",
        "bom": "BOM",
        "job": "Job Card",
        "card": "Job Card",
    }

    # Cache for doctype schemas
    _schema_cache = {}

    @classmethod
    def get_relevant_doctypes(cls, query: str, references: List[Dict[str, str]] = None) -> List[str]:
        """
        Identify relevant doctypes based on query and references

        Args:
            query: User's query text
            references: Optional list of document references

        Returns:
            List of relevant doctype names
        """
        relevant_doctypes = set()

        # Add doctypes from explicit references
        if references:
            for ref in references:
                doctype = ref.get("doctype")
                if doctype:
                    relevant_doctypes.add(doctype)

        # Scan query for common terms mapped to doctypes
        query_lower = query.lower()
        for term, doctype in cls.TERM_TO_DOCTYPE_MAP.items():
            if term in query_lower:
                relevant_doctypes.add(doctype)

        # Look for doctype mentions directly in query (CamelCase words might be doctypes)
        camel_case_pattern = r'\b([A-Z][a-z]+(?:[A-Z][a-z]+)+)\b'
        camel_case_matches = re.findall(camel_case_pattern, query)
        for match in camel_case_matches:
            # Check if this is a valid doctype
            if frappe.db.exists("DocType", match):
                relevant_doctypes.add(match)

        # Add related doctypes
        all_doctypes = set(relevant_doctypes)
        for doctype in relevant_doctypes:
            related = cls.get_related_doctypes(doctype)
            all_doctypes.update(related)

        return list(all_doctypes)

    @classmethod
    def get_related_doctypes(cls, doctype: str) -> List[str]:
        """Get doctypes related to the given doctype through common relationships"""
        related_doctypes = []

        # Common related doctype pairs
        doctype_pairs = {
            "Item": ["Sales Invoice Item", "Purchase Invoice Item", "BOM Item", "Bin"],
            "Sales Invoice": ["Sales Invoice Item", "Payment Entry"],
            "Customer": ["Sales Invoice", "Sales Order", "Quotation"],
            "Supplier": ["Purchase Invoice", "Purchase Order"],
            "Employee": ["Salary Slip", "Expense Claim"],
            "Account": ["GL Entry"],
            "Job Card": ["Work Order", "BOM"],
            "Work Order": ["Job Card", "BOM"],
        }

        # Add related doctypes if defined
        if doctype in doctype_pairs:
            related_doctypes.extend(doctype_pairs[doctype])

        return related_doctypes

    @classmethod
    def get_doctype_schema(cls, doctype: str) -> Dict[str, Any]:
        """
        Get schema information for a doctype

        Args:
            doctype: Name of the doctype

        Returns:
            Dictionary with fields, types, and other schema information
        """
        # Check cache first
        if doctype in cls._schema_cache:
            return cls._schema_cache[doctype]

        try:
            # Get doctype metadata
            meta = frappe.get_meta(doctype)

            # Extract field information
            fields = []
            for field in meta.fields:
                fields.append({
                    "fieldname": field.fieldname,
                    "label": field.label,
                    "fieldtype": field.fieldtype,
                    "options": field.options,
                    "reqd": field.reqd,
                    "in_list_view": field.in_list_view,
                    "in_standard_filter": field.in_standard_filter
                })

            # Build schema object
            schema = {
                "name": doctype,
                "table_name": f"tab{doctype}",
                "module": meta.module,
                "fields": fields,
                "key_fields": [f.fieldname for f in meta.fields if f.in_list_view or f.in_standard_filter][:5],
            }

            # Cache the result
            cls._schema_cache[doctype] = schema
            return schema

        except Exception as e:
            frappe.log_error(f"Error getting schema for {doctype}: {str(e)}")
            # Return basic schema on error
            return {
                "name": doctype,
                "table_name": f"tab{doctype}",
                "fields": [],
                "key_fields": []
            }

    @classmethod
    def build_schema_context(cls, doctypes: List[str]) -> str:
        """
        Build a context string with schema information for the given doctypes

        Args:
            doctypes: List of doctype names

        Returns:
            Formatted string with schema information
        """
        if not doctypes:
            return ""

        context_parts = ["## Database Schema Information"]

        for doctype in doctypes:
            schema = cls.get_doctype_schema(doctype)

            # Add doctype header
            context_parts.append(f"\n### {doctype} (`{schema['table_name']}`)")

            # Add key fields section if available
            if schema['key_fields']:
                key_fields_str = ', '.join([f"`{field}`" for field in schema['key_fields']])
                context_parts.append(f"Key fields: {key_fields_str}")

            # Add fields table
            if schema['fields']:
                # Start fields section
                context_parts.append("\nFields:")

                # Filter to the most important fields (avoid overwhelming context)
                important_fields = [
                    f for f in schema['fields']
                    if f['fieldname'] in schema['key_fields']
                    or f['fieldname'] in ['name', 'creation', 'modified', 'owner']
                    or f['reqd'] == 1
                    or f['in_list_view'] == 1
                ]

                # Add all fields if important fields are too few
                if len(important_fields) < 5:
                    important_fields = schema['fields'][:10]  # At least show first 10

                # Format field information
                for field in important_fields[:15]:  # Limit to 15 fields max
                    fieldname = field['fieldname']
                    fieldtype = field['fieldtype']
                    label = field['label'] or fieldname
                    options = field['options'] if fieldtype in ['Link', 'Select'] else ""

                    field_str = f"- `{fieldname}`: {fieldtype}"
                    if options:
                        field_str += f" -> {options}"
                    if label != fieldname:
                        field_str += f" ({label})"

                    context_parts.append(field_str)

                # Note if fields were truncated
                if len(schema['fields']) > 15:
                    context_parts.append(f"*...and {len(schema['fields']) - 15} more fields*")

            # Add some examples of SQL queries for this doctype
            context_parts.append("\nExample queries:")
            context_parts.append(f"- `SELECT name, {', '.join(schema['key_fields'][:3])} FROM `{schema['table_name']}` LIMIT 10`")

            if 'status' in [f['fieldname'] for f in schema['fields']]:
                context_parts.append(f"- `SELECT status, COUNT(*) as count FROM `{schema['table_name']}` GROUP BY status`")

            if any(f['fieldtype'] == 'Date' for f in schema['fields']):
                date_field = next(f['fieldname'] for f in schema['fields'] if f['fieldtype'] == 'Date')
                context_parts.append(f"- `SELECT {date_field}, COUNT(*) FROM `{schema['table_name']}` GROUP BY {date_field} ORDER BY {date_field} DESC`")

            # Add doctype relationships if applicable
            if doctype in ["Sales Invoice", "Item", "Customer"]:
                if doctype == "Sales Invoice":
                    context_parts.append(
                        "\nRelations: "
                        "\n- `tabSales Invoice Item` has `parent` field pointing to this doctype's `name`"
                        "\n- `customer` field links to `tabCustomer` doctype"
                    )
                elif doctype == "Item":
                    context_parts.append(
                        "\nRelations: "
                        "\n- `tabSales Invoice Item` has `item_code` field pointing to this doctype's `name`"
                        "\n- `tabPurchase Invoice Item` has `item_code` field pointing to this doctype's `name`"
                        "\n- `tabBin` has `item_code` field pointing to this doctype's `name`"
                    )
                elif doctype == "Customer":
                    context_parts.append(
                        "\nRelations: "
                        "\n- `tabSales Invoice` has `customer` field pointing to this doctype's `name`"
                        "\n- `tabSales Order` has `customer` field pointing to this doctype's `name`"
                    )

        return "\n".join(context_parts)
