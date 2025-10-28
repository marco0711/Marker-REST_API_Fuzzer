def sequence_signature_old(sequence):
    """
    Generates a normalized signature of a request sequence, based only on method + canonicalized URL path
    (i.e., replaces all dynamic path segments with placeholders)
    """
    def normalize_path(path):
        parts = path.strip("/").split("/")
        return "/".join(["{param}" if p.isdigit() or p.isalnum() and not p.islower() else p for p in parts])

    return tuple((req["method"], normalize_path(req["url"])) for req in sequence)

def sequence_signature(sequence, all_endpoints):
    """
    Generates a normalized signature of a request sequence, based only on method + canonicalized URL path.
    
    Returns:
        tuple of (method, canonical_path) for each request in the sequence
    """

    signature = []
    for req in sequence:
        ep = find_endpoint_by_request(req, all_endpoints)
        if ep:
            canonical_path = ep.path 
        else:
            print("COULD NOT FIND REQUEST'S ENDPOINT IN SPECIFICATION")
        signature.append((req["method"], canonical_path))

    return tuple(signature)


def find_endpoint_by_request(request, all_endpoints):
    req_method = request["method"]
    req_path = request["url"]

    for ep in all_endpoints:
        if ep.method != req_method:
            continue
        # Normalize dynamic path segments like /users/123 to /users/{id}
        if match_path_with_placeholders(ep.path, req_path):
            return ep
    return None

def match_path_with_placeholders(template_path, actual_path):
    """
    Matches /api/owners/{ownerId} with /api/owners/5
    """
    template_parts = template_path.strip("/").split("/")
    actual_parts = actual_path.strip("/").split("/")

    if len(template_parts) != len(actual_parts):
        return False

    for tp, ap in zip(template_parts, actual_parts):
        if (tp.startswith("{") and tp.endswith("}")) or tp == "*":
            continue  # Placeholder matches anything
        if tp != ap:
            return False
    return True