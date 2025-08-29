from typing import Optional

def has_matching_id(param_name: str, dynamic_id_table: dict) -> bool:
    """
    Returns True if param_name starts or ends with a key in dynamic_id_table (or vice versa).
    """
    param = param_name.lower()
    for key in dynamic_id_table:
        k = key.lower()
        if param.startswith(k) or param.endswith(k) or k.startswith(param) or k.endswith(param):
            return True
    return False

def get_matching_key(param_name: str, dynamic_id_table: dict) -> Optional[str]:
    param = param_name.lower()
    for key in dynamic_id_table:
        k = key.lower()
        if param.startswith(k) or param.endswith(k) or k.startswith(param) or k.endswith(param):
            return key
    return None