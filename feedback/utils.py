import re
from typing import Set, Dict, Tuple
from urllib.parse import urlparse

def deduplicate_url(url: str, paths: Set[str]) -> str:
        """
        Normalizes a URL using the spec-defined paths.
        - Keeps only the path part (drops scheme, host, query)
        - Replaces dynamic path params by matching them to known spec paths
        """
         # Try to find a matching spec path
        for spec_path in paths:
            if match_path(url, spec_path):
                # Found a canonical match → return the spec pattern
                return spec_path
        print("ERROR: no match found")

def normalize_url(url: str) -> str: 
    parsed = urlparse(url) 
    return parsed.path or url

def match_path(concrete: str, spec: str) -> bool:
    """
    Determines if a concrete path like '/posts/123' matches a spec
    path like '/posts/{postId}' without using regex.
    """
    concrete_parts = concrete.strip("/").split("/")
    spec_parts = spec.strip("/").split("/")

    if len(concrete_parts) != len(spec_parts):
        return False

    for cp, sp in zip(concrete_parts, spec_parts):
        if sp.startswith("{") and sp.endswith("}") or sp == "*":
            continue  # it's a parameter → allow any value
        if cp != sp:
            return False

    return True

def match_paths_with_dependencies(concrete_paths: Set[str], spec_paths: Set[str]) -> Set[str]:
    matched = set()
    for concrete in concrete_paths:
        for spec in spec_paths:
            if match_path(concrete, spec):
                matched.add(spec)
    return matched

def match_operations_with_dependencies(actual_ops: Set[Tuple[str, str]], spec_ops: Set[Tuple[str, str]]) -> Set[Tuple[str, str]]:
    matched = set()
    for method, concrete_path in actual_ops:
        for spec_method, spec_path in spec_ops:
            if method == spec_method and match_path(concrete_path, spec_path):
                matched.add((spec_method, spec_path))
    return matched

def collect_nested_fields(data: dict) -> set:
    """
    Recursively collect all field names (keys) from a nested JSON-like structure.
    This is useful for extracting parameter names from request or response bodies.
    """
    fields = set()

    if not isinstance(data, dict):
        return fields

    for key, value in data.items():
        # Add the current key
        fields.add(key)

        # Recurse into nested dicts
        if isinstance(value, dict):
            fields.update(collect_nested_fields(value))

        # Recurse into lists of dicts
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    fields.update(collect_nested_fields(item))

    return fields


def print_tcl_breakdown(seq_coverage: Dict[str, Set], spec_info: Dict[str, Set]) -> None:
    """
    Prints a detailed breakdown of TCL dimensions showing:
    - expected values
    - covered values
    - matched values (with relaxed path/operation matching)
    - partial score
    """
    print("\n📊 TCL Score Breakdown:")
    fields = [
        "paths",
        "operations",
        "input_content_types",
        "status_codes",
        "parameters",
        "response_fields"
    ]

    for field in fields:
        covered = seq_coverage.get(field, set())
        total = spec_info.get(field, set())

        if not total:
            continue

        # Match using custom logic where needed
        if field == "paths":
            matched = match_paths_with_dependencies(covered, total)
        elif field == "operations":
            matched = match_operations_with_dependencies(covered, total)
        else:
            matched = covered & total

        partial_score = len(matched) / len(total)
        missing = total - matched
        
        # Print section
        print(f"\n🧩 {field}:")
        print(f"   • Expected: {len(total)} → {total}")
        print(f"   • Covered : {len(covered)} → {covered}")
        print(f"   • Matched : {len(matched)} → {matched}")
        print(f"   • Missing : {len(missing)} → {missing}")
        print(f"   • Partial Score: {partial_score:.2f}")

