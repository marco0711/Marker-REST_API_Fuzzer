import json
from typing import Dict, Any, List, Union, Set

def EXTRACT_IDS(json_body: str, param_names: Set[str]) -> Dict[str, List[str]]:
    """
    Extract potential IDs from a JSON response, filtering out
    unrealistic values (error messages, long strings, etc.).
    """
    try:
        parsed = json.loads(json_body)
    except Exception:
        return {}

    found = {}
    base_tokens = {"id", "key", "token"}
    match_tokens = {t.lower() for t in base_tokens.union(param_names)}

    def is_valid_id(val: str) -> bool:
        # Reject long error-like strings
        if len(val) > 30:
            return False
        # Reject whitespace-containing values
        if " " in val:
            return False
        # Basic check: allow alphanumeric and simple punctuation
        if not all(c.isalnum() or c in "-_" for c in val):
            return False
        return True

    def recursive_extract(obj):
        if isinstance(obj, dict):
            for k, v in obj.items():
                if isinstance(v, (str, int)):
                    key_lower = k.lower()
                    value = str(v)

                    if is_valid_id(value):
                        for token in match_tokens:
                            if key_lower.startswith(token) or key_lower.endswith(token):
                                found.setdefault(token, set()).add(value)
                                break
                elif isinstance(v, (dict, list)):
                    recursive_extract(v)
        elif isinstance(obj, list):
            for item in obj:
                recursive_extract(item)

    recursive_extract(parsed)
    return {k: list(v) for k, v in found.items()}

