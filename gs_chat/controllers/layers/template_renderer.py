import re
import frappe

def render_template(template, query_results):
    """
    Render a template with query results

    Args:
        template: Template string with placeholders
        query_results: Dictionary of query results

    Returns:
        Rendered template
    """
    import re

    result = template

    # Handle array/index access like {{key[0].field}} or {{ key[0].field }}
    # Pattern matches: {{ key[index].field }} with optional spaces
    array_pattern = r'\{\{\s*(\w+)\[(\d+)\]\.(\w+)\s*\}\}'
    array_matches = re.findall(array_pattern, result)

    for key, index, field in array_matches:
        index = int(index)
        if key in query_results and isinstance(query_results[key], list):
            if index < len(query_results[key]) and field in query_results[key][index]:
                value = str(query_results[key][index][field])
                # Replace with spaces preserved
                result = re.sub(
                    r'\{\{\s*' + key + r'\[' + str(index) + r'\]\.' + field + r'\s*\}\}',
                    value,
                    result
                )

    # Handle simple placeholders {{key.field}} with optional spaces
    simple_pattern = r'\{\{\s*([^{}]+)\s*\}\}'
    simple_placeholders = re.findall(simple_pattern, result)

    for placeholder in simple_placeholders:
        placeholder = placeholder.strip()
        parts = placeholder.split('.')

        if len(parts) == 1:
            # Simple placeholder like {{key}}
            key = parts[0]
            if key in query_results:
                if isinstance(query_results[key], list) and query_results[key]:
                    value = str(query_results[key][0])
                else:
                    value = str(query_results[key])
                # Replace with spaces
                result = re.sub(r'\{\{\s*' + re.escape(placeholder) + r'\s*\}\}', value, result)

        elif len(parts) == 2 and '[' not in parts[0]:
            # Nested placeholder like {{key.field}}
            key, field = parts[0], parts[1]
            if key in query_results and isinstance(query_results[key], list) and query_results[key]:
                if field in query_results[key][0]:
                    value = str(query_results[key][0][field])
                    result = re.sub(r'\{\{\s*' + re.escape(placeholder) + r'\s*\}\}', value, result)

    # Handle loop templates {% for item in items %}...{% endfor %}
    loop_pattern = r'\{%\s*for\s+(\w+)\s+in\s+(\w+)\s*%\}(.*?)\{%\s*endfor\s*%\}'
    loop_blocks = re.findall(loop_pattern, result, re.DOTALL)

    for var_name, collection_name, block_content in loop_blocks:
        collection = None

        # Direct match
        if collection_name in query_results:
            collection = query_results[collection_name]
        else:
            # Fuzzy match
            for key in query_results:
                if collection_name in key or key in collection_name:
                    collection = query_results[key]
                    break

        if collection and isinstance(collection, list):
            rendered_items = []
            for i, item in enumerate(collection):
                item_result = block_content

                # Replace {{var.field}} with spaces
                var_pattern = r'\{\{\s*([\w.]+)\s*\}\}'
                var_matches = re.findall(var_pattern, block_content)

                for var_ref in var_matches:
                    var_parts = var_ref.split('.')

                    if var_parts[0] == var_name and len(var_parts) > 1:
                        field = var_parts[1]
                        if field in item:
                            value = str(item[field])
                            item_result = re.sub(
                                r'\{\{\s*' + re.escape(var_ref) + r'\s*\}\}',
                                value,
                                item_result
                            )
                    elif var_parts[0] == "loop" and len(var_parts) > 1:
                        if var_parts[1] == "index":
                            item_result = re.sub(
                                r'\{\{\s*' + re.escape(var_ref) + r'\s*\}\}',
                                f"\n{str(i + 1)}",
                                item_result
                            )

                rendered_items.append(item_result)

            # Replace the entire loop block
            full_pattern = r'\{%\s*for\s+' + var_name + r'\s+in\s+' + collection_name + r'\s*%\}.*?\{%\s*endfor\s*%\}'
            result = re.sub(full_pattern, "".join(rendered_items), result, flags=re.DOTALL)

    frappe.log_error("resp", repr([result, query_results, template]))

    return result
