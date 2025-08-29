import random
import string
import re
from typing import Dict
from generator.utils import get_matching_key


def build_request(endpoint):
    """
    Builds a request dictionary from an Endpoint object.
    - Uses required fields if present.
    - For POST requests with no required fields, adds one optional non-readOnly field
      (preferring those with 'example').
    """
    url = endpoint.path
    method = endpoint.method
    headers = {"Content-Type": "application/json"}

    # Add example header values
    for param in endpoint.parameters:
        if param.get("in") == "header":
            name = param["name"]
            headers[name] = generate_example_value(param["schema"])

    body = {}
    if endpoint.request_body:
        schema = endpoint.request_body
        props = schema.get("properties", {})
        required = set(schema.get("required", []))

        # Use all required fields
        for name in required:
            definition = props.get(name)
            if definition:
                value = generate_example_value(definition)
                if value is not None:
                    body[name] = value

        # If POST and no required fields, add one optional field (non-readOnly)
        if method == "POST" and not body:
            optional_fields = [
                (name, definition)
                for name, definition in props.items()
                if name not in required and not definition.get("readOnly", False)
            ]

            # Prioritize those with an "example"
            with_example = [(n, d) for n, d in optional_fields if "example" in d]
            fallback_candidates = with_example or optional_fields

            if fallback_candidates:
                name, definition = random.choice(fallback_candidates)
                value = generate_example_value(definition)
                if value is not None:
                    body[name] = value

    return {
        "method": method,
        "url": url,
        "headers": headers,
        "body": body if body else None,
        "parameters": endpoint.parameters,
    }



def generate_example_value(schema_def):
    """
    Generate a dummy value that conforms to the given schema definition.
    """
    if "example" in schema_def:
        return schema_def["example"]

    schema_type = schema_def.get("type")
    schema_format = schema_def.get("format", "")
    pattern = schema_def.get("pattern")

    if schema_type == "string":
        if pattern:
            return generate_matching_string(pattern)
        if schema_format == "email":
            return "user@example.com"
        if schema_format == "date":
            return "2025-01-01"
        if schema_format == "date-time":
            return "2025-01-01T00:00:00Z"
        return "example-string"

    elif schema_type == "integer":
        minimum = schema_def.get("minimum", 0)
        maximum = schema_def.get("maximum", 9999999999)
        return min(max(123, minimum), maximum)

    elif schema_type == "number":
        minimum = schema_def.get("minimum", 0.0)
        maximum = schema_def.get("maximum", 9999999.99)
        return round(min(max(123.45, minimum), maximum), 2)

    elif schema_type == "boolean":
        return True

    elif schema_type == "array":
        items = schema_def.get("items", {})
        item_value = generate_example_value(items)
        return [item_value] if item_value is not None else []

    elif schema_type == "object":
        props = schema_def.get("properties", {})
        return {
            k: v for k, v in {
                k: generate_example_value(v)
                for k, v in props.items()
            }.items() if v is not None
        }

    print(f"⚠️ Warning: Unknown schema type, using fallback: {schema_def}")
    return "fallback"


def generate_matching_string(pattern):
    """
    Generate a simple string that matches a limited subset of regex patterns.
    This supports simple digit-length patterns like ^\d{0,10}$
    """
    if re.fullmatch(r"^\d\{\d+,\d+\}$", pattern):
        min_len, max_len = map(int, re.findall(r"\d+", pattern))
        return ''.join(random.choices(string.digits, k=random.randint(min_len, max_len)))

    # Support patterns like ^\d{0,10}$
    match = re.match(r"^\^\\d\{(\d+),?(\d*)\}\$$", pattern)
    if match:
        min_digits = int(match.group(1))
        max_digits = int(match.group(2) or match.group(1))
        length = random.randint(min_digits, max_digits)
        return ''.join(random.choices(string.digits, k=length))

    # Fallback: return a generic digit string if pattern starts with \d
    if pattern.startswith(r"^\d"):
        return "123456"

    return "example"  # fallback


def RESOLVE_DEPENDENCIES(request: Dict, dynamic_id_table: Dict[str, list]) -> Dict:
    """
    Replaces path and header placeholders with real dynamic values if available,
    otherwise falls back to dummy values.

    Args:
        request: A request dict with placeholders like /pets/{id}
        dynamic_id_table: Dict of ID names -> list of possible values

    Returns:
        A new request dict with placeholders resolved.
    """
    resolved = request.copy()

    # --- Resolve path parameters ---
    url = resolved["url"]
    placeholders = re.findall(r"\{(.*?)\}", url)

    for ph in placeholders:
        match_key = get_matching_key(ph, dynamic_id_table)
        if match_key and dynamic_id_table[match_key]:
            # Use a discovered value
            value = random.choice(dynamic_id_table[match_key])
        else:
            # Fallback: generate dummy based on schema if available, else str int
             # Look for schema definition of this path param
            schema = None
            if "parameters" in request:
                for p in request["parameters"]:
                    if p.get("name") == ph and p.get("in") == "path":
                        if "schema" in p:  # OpenAPI 3.x
                            schema = p["schema"]
                        elif "type" in p:  # Swagger 2.0
                            schema = {k: v for k, v in p.items() if k in ("type", "format", "enum")}
                        break
            # Generate value from schema (default string fallback)
            value = generate_example_value(schema if schema else {"type": "string"})
        url = url.replace(f"{{{ph}}}", str(value))

    resolved["url"] = url

    # --- Resolve headers ---
    headers = resolved.get("headers", {})
    new_headers = {}
    for key, val in headers.items():
        if isinstance(val, str) and val.startswith("{") and val.endswith("}"):
            ph = val.strip("{}")
            match_key = get_matching_key(ph, dynamic_id_table)
            if match_key and dynamic_id_table[match_key]:
                new_headers[key] = random.choice(dynamic_id_table[match_key])
            else:
                # fallback dummy for header
                new_headers[key] = str(generate_example_value({"type": "string"}))
        else:
            new_headers[key] = val
    resolved["headers"] = new_headers

    return resolved