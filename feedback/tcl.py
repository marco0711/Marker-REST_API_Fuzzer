import json
import os
import re
from typing import Any, Dict, List, Set, Tuple
from feedback.utils import match_paths_with_dependencies, match_operations_with_dependencies

def extract_seq_coverage(requests: List[Dict], responses: List[Dict], spec_info: Dict[str, Set]) -> Dict[str, Set]:
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

    all_paths = spec_info.get("paths")
    all_ops = spec_info.get("operations")


    for req in requests:
        url = req["url"].split("?")[0]
        method = req["method"]

        # Count paths
        normalized_path = match_paths_with_dependencies({url},all_paths)
        coverage["paths"].update(normalized_path)

        # Count operations
        normalized_ops = match_operations_with_dependencies({(method,url)},all_ops)
        coverage["operations"].update((normalized_ops))

        # Parameters from headers and body
        if req.get("headers"):
            coverage["parameters"].update(req["headers"].keys())
        if req.get("body") and isinstance(req["body"], dict):
            coverage["parameters"].update(req["body"].keys())

        # Content-Type used
        if req.get("body"):
            ctype = req.get("headers", {}).get("Content-Type")
            if ctype:
                for norm_op in normalized_ops:
                    coverage["input_content_types"].add((norm_op, ctype))

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

def total_TCL_score(cumulative_coverage: dict, spec_info: dict, output_file: str):
    """
    Computes a hierarchical total TCL score across the six coverage levels.
    You can only advance to the next level if you have 100% coverage on the current one.

    Levels:
        1. paths
        2. operations
        3. input_content_types
        4. parameters
        5. status_codes
        6. response_fields
    """

    levels = [
        ("paths", "Paths coverage"),
        ("operations", "Operations coverage"),
        ("input_content_types", "Input content types coverage"),
        ("parameters", "Parameters coverage"),
        ("status_codes", "Status code coverage"),
        ("response_fields", "Response fields coverage")
    ]

    score = 0.0
    detailed_results = {}

    for i, (field, label) in enumerate(levels, start=1):
        covered = cumulative_coverage.get(field, set())
        total = spec_info.get(field, set())

        if not total:
            # If spec doesn't define this level, skip it but count as full
            detailed_results[field] = {"covered": 0, "total": 0, "coverage": 1.0}
            score += 1
            continue

        coverage_ratio = len(covered) / len(total)
        detailed_results[field] = {
            "covered": len(covered),
            "total": len(total),
            "coverage": round(coverage_ratio, 3)
        }

        if coverage_ratio >= 1.0:
            score += 1
        else:
            # Optional: fractional contribution of last level
            score += coverage_ratio
            break  # stop at first incomplete level

    # Write final hierarchical score to bug report file
    result_data = {
        "final_total_TCL": round(score, 3),
        "level_breakdown": detailed_results
    }

    try:
        if os.path.exists(output_file):
            with open(output_file, "a", encoding="utf-8") as f:
                f.write("\n\n=== FINAL TCL SCORE ===\n")
                f.write(json.dumps(result_data, indent=2))
                f.write("\n")
        else:
            with open(output_file, "w", encoding="utf-8") as f:
                f.write(json.dumps(result_data, indent=2))
                f.write("\n")
    except Exception as e:
        print(f"[!] Error writing final TCL score: {e}")

    return score


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
