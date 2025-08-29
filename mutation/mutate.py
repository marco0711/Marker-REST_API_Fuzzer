import random
import string
import json
import copy
from copy import deepcopy
from typing import Dict, List
from generator.request import generate_example_value
from mutation.utils import find_endpoint_by_request

def mutate_request(request: Dict, schema: Dict) -> List[Dict]:
    """
    Apply value mutations and optional field additions to a single request.

    Args:
        request: The original request dictionary.
        schema: The OpenAPI schema for the request body ("properties" + "required" fields).

    Returns:
        List of mutated request dictionaries.
    """
    mutations = []

    original_body = request.get("body", {})

    if not isinstance(original_body, dict) or not original_body:
        return [request]  # No mutations possible

    headers = request.get("headers", {})
    method = request["method"]
    url = request["url"]

    # Mutate required fields' values
    for field in original_body:
        mutated = deepcopy(original_body)
        mutated[field] = mutate_value(mutated[field])
        mutations.append({
            "method": method,
            "url": url,
            "headers": headers,
            "body": mutated
        })

    # Add optional fields (from schema)
    properties = schema.get("properties", {})
    required = set(schema.get("required", []))
    optional_fields = [f for f in properties if f not in original_body and f not in required]

    for field in optional_fields:
        example_val = generate_example_value(properties[field])
        if example_val is not None:
            mutated = deepcopy(original_body)
            mutated[field] = example_val
            mutations.append({
                "method": method,
                "url": url,
                "headers": headers,
                "body": mutated
            })

    return mutations

def mutate_value(value):
    """Apply basic value mutation based on type."""
    if isinstance(value, int):
        return random.choice([0, -1, value + 1, value - 1, 999999])
    if isinstance(value, float):
        return random.choice([0.0, -1.1, value * 2, 99999.99])
    if isinstance(value, str):
        return random.choice(["", value + "_mutated", "\n".join([value]*3), random_string(50)])
    if isinstance(value, bool):
        return not value
    if isinstance(value, list):
        return value + value  # duplicate entries
    return value

def random_string(length):
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

def deep_mutation(sequence: list, endpoints: list) -> list:
    """
    Apply deep mutations to a full sequence of requests.
    Mutations include:
      - Adding optional fields to JSON body
      - Edge-case values for numeric/string fields
      - Wrong types for fuzzing
    Headers are not mutated.
    
    Returns a new mutated sequence.
    """
    mutated_sequence = []

    for req in sequence:
        # Copy original request
        mutated_req = copy.deepcopy(req)
        ep = find_endpoint_by_request(req, endpoints)

        if not ep or not ep.request_body:
            mutated_sequence.append(mutated_req)
            continue

        try:
            original_body = json.loads(mutated_req.get("body", "{}"))
        except Exception:
            mutated_sequence.append(mutated_req)
            continue

        schema = ep.request_body.get("content", {}).get("application/json", {}).get("schema", {})
        if not schema or schema.get("type") != "object":
            mutated_sequence.append(mutated_req)
            continue

        properties = schema.get("properties", {})
        required_fields = schema.get("required", [])

        # Add optional fields not present
        for field, field_schema in properties.items():
            if field not in original_body:
                if field not in required_fields:
                    original_body[field] = generate_fuzz_value(field_schema)
        '''
        
        # Mutate existing and newly added fields with random (wrong) value
        for field, value in original_body.items():
            field_schema = properties.get(field, {})
            original_body[field] = mutate_value(value, field_schema)
        '''

        # Reassign mutated body
        mutated_req["body"] = json.dumps(original_body)
        mutated_sequence.append(mutated_req)
        
    return mutated_sequence


def generate_fuzz_value(schema: dict):
    """Generate a synthetic value for an optional field based on its schema."""
    typ = schema.get("type")
    if typ == "string":
        return random.choice(["", "a" * 1000, "💥💥💥", "\x00", "null", "1234"])
    elif typ == "integer":
        return random.choice([-1, 0, 1, 2**31 - 1, -2**31])
    elif typ == "number":
        return random.choice([-1.0, 0.0, 3.14159, float("inf"), float("-inf")])
    elif typ == "boolean":
        return random.choice([True, False])
    elif typ == "array":
        return []
    elif typ == "object":
        return {}
    else:
        return "fuzz"  # fallback

'''
def mutate_value(value, schema: dict):
    """Mutate an existing value into an edge case or type violation."""
    typ = schema.get("type")

    # Wrong type
    if random.random() < 0.3:
        return random.choice([123, "string", None, True, [], {}])

    # Edge-case value
    if typ == "string":
        return random.choice(["", "X" * 1000, "🔥", "\x00", "null"])
    elif typ == "integer":
        return random.choice([0, -1, 2**31 - 1, -2**31])
    elif typ == "number":
        return random.choice([float("inf"), float("-inf"), 0.0])
    elif typ == "boolean":
        return not value
    elif typ == "array":
        return [value, value]
    elif typ == "object":
        return value  # Could be expanded to deep-mutate nested objects
    else:
        return value
'''