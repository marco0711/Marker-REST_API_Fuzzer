import random
import string
import json
import copy
from copy import deepcopy
from typing import Dict, List, Any
from generator.request import generate_example_value
from mutation.utils import find_endpoint_by_request, resolve_ref

# =====> Config <=======
MUTATE_EXISTING_PROB = 0.3   # chance to mutate an existing field
MUTATE_TYPE_CONFUSION_P = 0.3  # when mutating, prob of type-confusion vs edge-of-type
MAX_STRING_LEN = 10000
MAX_ARRAY_LEN = 10


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

      - Add optional fields.
      - Mutate existing fields probabilistically using `mutate_bad_value`.
      - Use schema information to pick sensible fuzz values (via generate_fuzz_value).
      - Keep headers unchanged.

    Returns a new mutated sequence (deep-copied).
    """
    mutated_sequence = []

    for req in sequence:
        ep = find_endpoint_by_request(req, endpoints)

        # If there is no endpoint keep unchanged
        if not ep:
            mutated_sequence.append(req)
            print(f"DEEP MUTATION ERROR, no ep found for: {req}")
            continue
        
        # Get request body properties
        if ep.request_body:
            schema = ep.request_body
            props = schema.get("properties", {})
            body = {}
        else:
            mutated_sequence.append(req)
            print(f"WARNING: No request body found for endpoint: {ep.path} skipping mutation")
            continue

        # === Populate every field except readOnly
        for name, definition in props.items():
            # Resolve $ref if present
            if "$ref" in definition:
                definition = resolve_ref(definition, ep.root_spec)

            print(f"Populating field: {name} → {definition}")

            if definition.get("readOnly", False):
                continue  # Skip read-only fields
            
            try:
                # Always generate a base fuzzing value
                value = generate_fuzz_value(definition)

                # Occasionally mutate it further
                if random.random() < MUTATE_EXISTING_PROB:
                    value = mutate_bad_value(value, definition)

                body[name] = value
            except Exception as e:
                print(f"⚠️ Error generating fuzz value for field '{name}' in {ep.path}: {e}")

        # Copy original request
        mut_req = copy.deepcopy(req)
        print(f"original req: {mut_req}")

        mut_req["body"] = body
        mutated_sequence.append(mut_req) 

        print(f"✅ Mutated request for {ep.method} {ep.path}: {list(body.keys())}")
    return mutated_sequence




def deep_mutation_old(sequence: list, endpoints: list) -> list:
    """
    Apply deep mutations to a full sequence of requests.

      - Add optional fields.
      - Mutate existing fields probabilistically using `mutate_bad_value`.
      - Use schema information to pick sensible fuzz values (via generate_fuzz_value).
      - Keep headers unchanged.

    Returns a new mutated sequence (deep-copied).
    """
    mutated_sequence = []

    for req in sequence:
        mutated_req = copy.deepcopy(req)
        ep = find_endpoint_by_request(req, endpoints)

        # If there is no endpoint keep unchanged
        if not ep:
            mutated_sequence.append(mutated_req)
            print(f"UNCHANGED, no ep found: {mutated_req}")
            continue

        # Parse body safely
        body_data = mutated_req.get("body", {})
        if isinstance(body_data, str):
            try:
                original_body = json.loads(body_data or "{}")
            except Exception as e:
                print(f"ERROR parsing body JSON: {e}")
                mutated_sequence.append(mutated_req)
                continue
        elif isinstance(body_data, dict):
            original_body = copy.deepcopy(body_data)
        else:
            original_body = {}

        schema = {}
        if ep.request_body:
            schema = ep.request_body.get("content", {}).get("application/json", {}).get("schema", {})
        # Fallback for OpenAPI v2 body schemas
        elif ep.raw.get("parameters"):
            for p in ep.raw["parameters"]:
                if p.get("in") == "body" and "schema" in p:
                    schema = p["schema"]
                    break

        # Do not apply mutation to endpoints with no schema
        if not schema:
            mutated_sequence.append(mutated_req)
            continue

        # Resolve $ref if needed
        if "$ref" in schema:
            schema = resolve_ref(schema["$ref"], ep.root_spec)


        # Recursive population and mutation
        original_body = mutate_body_by_schema(original_body, schema, ep.root_spec)
        '''
        if not schema or schema.get("type") != "object":
            mutated_sequence.append(mutated_req)
            print("SCHEMA NOT FOUND")
            continue

        properties = schema.get("properties", {})
        required_fields = schema.get("required", [])

        # 1) Add optional fields not present (using schema-aware generator)

        for field, field_schema in properties.items():
            if field not in original_body and field not in required_fields:
                try:
                    original_body[field] = generate_fuzz_value(field_schema)
                except Exception as e:
                    print(f"ERROR: Couldn't generate fuzz value during deep mutation: {e}")    

        # 2) Mutate existing fields probabilistically
        for field, value in list(original_body.items()):
            # Apply mutation with MUTATE_EXISTING_PROB
            if random.random() < MUTATE_EXISTING_PROB:
                field_schema = properties.get(field, {})
                original_body[field] = mutate_bad_value(value, field_schema)
        '''
        # Serialize safely
        try:
            mutated_req["body"] = json.dumps(original_body)
        except Exception as e:
            print(f"ERROR serializing mutated body: {e}")
            mutated_req["body"] = json.dumps(original_body, default=str)

        mutated_sequence.append(mutated_req)
        print(f"✅ Mutated: {ep.method} {ep.path} → {list(original_body.keys())}")

    return mutated_sequence

def mutate_body_by_schema(original_body, schema, root_spec):
    """
    Recursively mutate or populate a JSON body according to a given schema.
    Supports objects, arrays, and primitive types.
    """
    if "$ref" in schema:
        schema = resolve_ref(schema, root_spec)

    # Resolve object schemas
    if schema.get("type") == "object" or "properties" in schema:
        if not isinstance(original_body, dict):
            original_body = {}

        props = schema.get("properties", {})
        required_fields = schema.get("required", [])

        # Add missing fields
        for field, subschema in props.items():
            if field not in original_body:
                original_body[field] = generate_fuzz_value(subschema)

        # Mutate existing fields recursively
        for field, value in list(original_body.items()):
            if random.random() < MUTATE_EXISTING_PROB:
                subschema = props.get(field, {})
                original_body[field] = mutate_bad_value(value, subschema)
            elif field in props:
                # Recurse into nested structure
                original_body[field] = mutate_body_by_schema(original_body[field], props[field], root_spec)

        return original_body

    # Resolve array schemas
    elif schema.get("type") == "array" and "items" in schema:
        if not isinstance(original_body, list):
            original_body = []
        if not original_body:
            # Add one element
            original_body.append(generate_fuzz_value(schema["items"]))
        else:
            # Mutate existing elements
            for i, elem in enumerate(original_body):
                if random.random() < MUTATE_EXISTING_PROB:
                    original_body[i] = mutate_bad_value(elem, schema["items"])
                else:
                    original_body[i] = mutate_body_by_schema(elem, schema["items"], root_spec)
        return original_body

    # Fallback for primitives (string, number, boolean, etc.)
    else:
        if random.random() < MUTATE_EXISTING_PROB:
            return mutate_bad_value(original_body, schema)
        return original_body

def generate_fuzz_value(schema: Dict[str, Any]):
    """
    Generate a synthetic value for a field given its JSON Schema.
    This returns *aggressive* edge-case values.
    """
    if not isinstance(schema, dict):
        print("ERROR: no schema in generate_fuzz_value")
        return "fuzz"

    typ = schema.get("type")
    fmt = schema.get("format", "").lower()
    minimum = schema.get("minimum")
    maximum = schema.get("maximum")
    pattern = schema.get("pattern")

    # Strings: many edge-case payloads
    if typ == "string" or (not typ and fmt in ("date-time", "uuid", "email")):
        candidates = []

        # empty and very long
        candidates.append("")
        candidates.append("a" * 1024)
        candidates.append("a" * 10000 if MAX_STRING_LEN >= 10000 else "a" * MAX_STRING_LEN)

        # unicode and control
        candidates.append("💥" * 100)
        candidates.append("\x00\x00\x00")
        candidates.append("\r\n\r\n")
        candidates.append(" " * 2000)

        # payloads
        candidates.append("<script>alert(1)</script>")
        candidates.append("'; DROP TABLE users; --")
        candidates.append("../../../../etc/passwd")
        candidates.append("%00%00")  # NUL-like
        candidates.append("../../../" + "a" * 1000)

        # format-aware values
        if fmt == "date-time":
            candidates.append("1970-01-01T00:00:00Z")
            candidates.append("9999-12-31T23:59:59Z")
        if fmt == "uuid":
            candidates.append("00000000-0000-0000-0000-000000000000")
            candidates.append("ffffffff-ffff-ffff-ffff-ffffffffffff")
        if fmt == "email":
            candidates.append("a@b.c")
            candidates.append(("verylong" + "a"*200 + "@example.com"))

        # pattern-aware: try to break with non-matching or matching weirdness
        if pattern:
            candidates.append("pattern_breaker_!!")

        # numeric-like strings
        candidates.append("123456789012345678901234567890")
        candidates.append("0")
        candidates.append("-1")

        # binary-ish base64
        candidates.append("A" * 1024)

        return random.choice(candidates)

    # Integer
    if typ == "integer":
        candidates = []
        # typical edge ints
        candidates.extend([0, -1, 1, 2**31 - 1, -2**31, 2**63 - 1, -2**63])
        if minimum is not None:
            candidates.append(minimum - 1 if isinstance(minimum, int) else int(minimum) - 1)
        if maximum is not None:
            candidates.append(maximum + 1 if isinstance(maximum, int) else int(maximum) + 1)
        # other weird
        candidates.append(999999999999999999)
        return random.choice(candidates)

    # Number (float)
    if typ == "number":
        candidates = [-1.0, 0.0, 1e308, -1e308, 3.1415926535, float("nan"), float("inf"), float("-inf")]
        if minimum is not None:
            candidates.append(float(minimum) - 1.0)
        if maximum is not None:
            candidates.append(float(maximum) + 1.0)
        return random.choice(candidates)

    # Boolean
    if typ == "boolean":
        return random.choice([True, False, 0, 1])

    # Array
    if typ == "array":
        items = schema.get("items", {})
        # produce 0-length arrays and very long arrays and arrays with wrong types
        if random.random() < 0.3:
            return []
        if random.random() < 0.2:
            return [generate_fuzz_value(items) for _ in range(MAX_ARRAY_LEN)]
        # sometimes return a scalar to cause type confusion
        if random.random() < 0.2:
            return generate_fuzz_value(items)
        return [generate_fuzz_value(items) for _ in range(random.randint(1, 4))]

    # Object
    if typ == "object":
        # produce empty object, nested fuzzed object, or a wrong scalar sometimes
        if random.random() < 0.3:
            return {}
        # produce small nested object with fuzzed values
        obj = {}
        props = schema.get("properties", {})
        # limit to a few props to avoid explosion
        for k, v in list(props.items())[:3]:
            obj[k] = generate_fuzz_value(v)
        return obj

    # fallback: return varied tokens (keeps as string)
    print("FALLBACK for generate_fuzz_value")
    return random.choice(["fuzz", "NULL", "null", None, "1234", "{}"])


def mutate_bad_value(value: Any, schema: Dict[str, Any]):
    """
    Mutate an existing value using schema hints.
    Two mutation styles:
      - type confusion: replace with different type (string for number, number for string)
      - edge-of-type: extreme values within the same type (very long strings, big ints)
    """
    typ = schema.get("type")

    # Type confusion
    if typ and random.random() < MUTATE_TYPE_CONFUSION_P:
        # replace with a different type
        other = random.choice(["string", "integer", "number", "boolean", "null", "array", "object"])
        fake_schema = {"type": other}
        return generate_fuzz_value(fake_schema)

    # Edge-of-type mutation (prefer same type)
    if typ == "string" or isinstance(value, str):
        # return heavy unicode or CRLF or injection
        return generate_fuzz_value({"type": "string"})
    if typ == "integer" or isinstance(value, int):
        # flip sign, overflow, off-by-one
        candidates = [value, -value, value + 1, value - 1]
        candidates.extend([2**31 - 1, -2**31, 2**63 - 1])
        return random.choice(candidates)
    if typ == "number" or isinstance(value, float):
        # extremes
        return random.choice([float("nan"), float("inf"), -1e308, 1e308, 0.0])
    if typ == "boolean" or isinstance(value, bool):
        return not bool(value)
    if typ == "array" or isinstance(value, (list, tuple)):
        # sometimes make it longer, sometimes scalar
        if random.random() < 0.3:
            return []
        return [generate_fuzz_value({}) for _ in range(random.randint(0, 8))]
    if typ == "object" or isinstance(value, dict):
        # drop fields or add garbage fields
        if isinstance(value, dict):
            mutated = dict(value)
            if mutated:
                # remove a random key sometimes
                if random.random() < 0.3:
                    k = random.choice(list(mutated.keys()))
                    mutated.pop(k, None)
            # add a noisy key
            if random.random() < 0.5:
                mutated["_fuzz"] = generate_fuzz_value({})
            return mutated
        else:
            return generate_fuzz_value({"type": "object"})

    # fallback: use generic fuzz value
    print("FALLBACK for mutate_bad_value")
    return generate_fuzz_value({})