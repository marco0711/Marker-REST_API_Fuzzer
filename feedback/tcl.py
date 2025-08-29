import json
import re
from typing import Any, Dict, List, Set, Tuple
from feedback.utils import match_paths_with_dependencies, match_operations_with_dependencies

def extract_seq_coverage(requests: List[Dict], responses: List[Dict]) -> Dict[str, Set]:
    """
    Extracts which API elements (paths, operations, parameters, status codes,
    response fields, and input content-types) are exercised by a request sequence.
    """
    coverage = {
        "paths": set(),
        "operations": set(),
        "parameters": set(),
        "status_codes": set(),
        "response_fields": set(),
        "input_content_types": set()
    }

    for req in requests:
        url = req["url"].split("?")[0]
        method = req["method"]
        coverage["paths"].add(url)
        coverage["operations"].add((method, url))

        # Parameters from headers and body
        if req.get("headers"):
            coverage["parameters"].update(req["headers"].keys())
        if req.get("body") and isinstance(req["body"], dict):
            coverage["parameters"].update(req["body"].keys())

        # Content-Type used
        if req.get("body"):
            ctype = req.get("headers", {}).get("Content-Type")
            if ctype:
                coverage["input_content_types"].add((method, url, ctype))

    for resp in responses:
        coverage["status_codes"].add(str(resp["status"]))
        try:
            body = json.loads(resp["body"])
            if isinstance(body, dict):
                coverage["response_fields"].update(body.keys())
        except Exception:
            continue

    return coverage


def calculate_tcl_score(seq_coverage: Dict[str, Set], spec_info: Dict[str, Set]) -> float:
    """
    Calculates the sequence-level TCL score as the sum of partial coverage
    ratios across six coverage dimensions (including path dependencies).
    """
    total_score = 0.0
    fields = [
        "paths",
        "operations",
        "parameters",
        "status_codes",
        "response_fields",
        "input_content_types"
    ]

    for field in fields:
        covered = seq_coverage.get(field, set())
        total = spec_info.get(field, set())

        if not total:
            continue

        # Use custom matching for paths and operations
        if field == "paths":
            matched = match_paths_with_dependencies(covered, total)
        elif field == "operations":
            matched = match_operations_with_dependencies(covered, total)
        else:
            matched = covered & total

        partial_score = len(matched) / len(total)
        total_score += partial_score

    return total_score



def CALCULATE_DIVERSITY(response: dict, seen_fields: set) -> Tuple[float, set]:
    """
    Calculates the diversity score of a response by comparing its fields
    to the global set of already seen fields.

    Args:
        response: A dict with a "body" key containing the raw JSON string.
        seen_fields: Set of all previously seen flattened field paths.

    Returns:
        A float representing the number of new fields discovered.
        current set of seen fields
    """
    body = response.get("body", "")
    content_type = response.get("headers", {}).get("content-type", "")

    # Return early for empty or non-JSON responses
    if not body.strip() or "application/json" not in content_type:
        return 0.0, seen_fields

    try:
        json_body = json.loads(body)
    except json.JSONDecodeError:
        return 0.0, seen_fields

    flat = flatten_json(json_body)
    fields = set(flat.keys())
    new_fields = fields - seen_fields
    return float(len(new_fields)), fields # return also current fields for updating the global set

def flatten_json(data: Any, parent_key: str = '', sep: str = '.') -> Dict[str, Any]:
    """
    Recursively flattens a nested JSON object (dicts and lists) into a flat dictionary
    where keys represent the path to each value using dot notation or indexed paths.

    Example:
        {
            "a": {
                "b": 1,
                "c": [ {"d": 2}, {"e": 3} ]
            }
        }
    Becomes:
        {
            "a.b": 1,
            "a.c.0.d": 2,
            "a.c.1.e": 3
        }
    Parameters:
        data (Any): The input JSON-like data structure (parsed from json.loads)
        parent_key (str): Used internally during recursion to build full key paths
        sep (str): The separator used between nested keys (default: '.')

    Returns:
        Dict[str, Any]: A flat dictionary mapping composite keys to leaf values
    """
    items = []

    # If the current item is a dictionary, recurse into its keys
    if isinstance(data, dict):
        for key, value in data.items():
            new_key = f"{parent_key}{sep}{key}" if parent_key else key
            items.extend(flatten_json(value, new_key, sep=sep).items())

    # If it's a list, recurse into each item with numeric indices as keys
    elif isinstance(data, list):
        for index, value in enumerate(data):
            new_key = f"{parent_key}{sep}{index}" if parent_key else str(index)
            items.extend(flatten_json(value, new_key, sep=sep).items())

    # If it's a primitive (string, int, etc.), store it directly
    else:
        items.append((parent_key, data))

    return dict(items)
