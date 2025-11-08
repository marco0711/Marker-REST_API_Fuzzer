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
        if tp.startswith("{") and tp.endswith("}"):
            continue  # Placeholder matches anything
        if tp != ap:
            return False
    return True

def resolve_ref(schema: dict, root_spec: dict) -> dict:
    """
    Resolves a $ref pointer inside the OpenAPI specification.
    Works for both OpenAPI 2.0 ('#/definitions/...') and 3.0 ('#/components/schemas/...').
    Returns the fully dereferenced schema.
    """
    if not schema or "$ref" not in schema:
        print("REF NOT FOUND")
        return schema

    ref_path = schema["$ref"].lstrip("#/").split("/")
    resolved = root_spec
    for part in ref_path:
        if not isinstance(resolved, dict):
            print("ERROR in ref resolve")
            return schema  # defensive fallback
        resolved = resolved.get(part)
        if resolved is None:
            print("ERROR: Couldn't resolve ref")
            return schema  # couldn't resolve
        
    # Recursively resolve if nested $ref exist
    if isinstance(resolved, dict) and "$ref" in resolved:
        return resolve_ref(resolved, root_spec)

    return resolved
