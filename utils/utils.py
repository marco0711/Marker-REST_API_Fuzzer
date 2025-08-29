def sequence_signature(sequence):
    """
    Generates a normalized signature of a request sequence, based only on method + canonicalized URL path
    (i.e., replaces all dynamic path segments with placeholders)
    """
    def normalize_path(path):
        parts = path.strip("/").split("/")
        return "/".join(["{param}" if p.isdigit() or p.isalnum() and not p.islower() else p for p in parts])

    return tuple((req["method"], normalize_path(req["url"])) for req in sequence)