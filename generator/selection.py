import random
from typing import List, Dict
from parser.swagger import Endpoint
from .utils import has_matching_id, get_matching_key

ALPHA = 1  # weight for TCL
BETA = 1   # weight for Diversity

MAX_SEQUENCE_LENGTH = 8  # Do not extend tests longer than this
LENGTH_WEIGHT = 0.3

def SELECT_TEST(corpus: list) -> dict:
    """
    Selects a test sequence from the corpus using an ε-greedy strategy:
    - 80% of the time: weighted selection based on score.
    - 20% of the time: pure random from viable tests.
    """

    if not corpus:
        raise ValueError("Corpus is empty")

    viable_tests = [entry for entry in corpus if len(entry["sequence"]) < MAX_SEQUENCE_LENGTH]
    if not viable_tests:
        raise ValueError("No viable tests under the max sequence length.")

    if random.random() < 0.2:
        # Exploration: pick any viable test at random
        return random.choice(viable_tests)
    else:
        # Exploitation: weighted selection
        scores = []
        for entry in viable_tests:
            tcl = entry.get("tcl", 0.0)
            diversity = entry.get("diversity", 0.0)
            length_penalty = LENGTH_WEIGHT * len(entry["sequence"])
            score = tcl * ALPHA + diversity * BETA - length_penalty
            scores.append(max(score, 0.01))  # Avoid zero probability

        total_score = sum(scores)
        probabilities = [s / total_score for s in scores]
        return random.choices(viable_tests, weights=probabilities, k=1)[0]

 

def CHOOSE_COMPATIBLE_ENDPOINT(base_test: dict, endpoints: List[Endpoint], dynamic_id_table: Dict[str, List[str]]) -> Endpoint:
    """
    Chooses an endpoint that can be resolved using available dynamic IDs.
    
    Args:
        base_test: The current test sequence (dict with "sequence" key)
        endpoints: All known parsed endpoints
        dynamic_id_table: Available dynamic values (path/header params)
    
    Returns:
        A compatible Endpoint object
    """

    #DEBUG 
    #print("id table: ", dynamic_id_table)

    #used_paths = {req["url"].split("?")[0] for req in base_test["sequence"]}

    #track normalized endpoints of the sequence
    used_templates = set()
    for req in base_test["sequence"]:
        ep = find_endpoint_by_request(req, endpoints)
        if ep:
            used_templates.add((ep.method, ep.path))

    compatible = []

    for ep in endpoints:
        # Skip if already in the current sequence (avoid loops)
        if (ep.method, ep.path) in used_templates:
            continue

        # Check required path and header params
        required_params = [p for p in ep.path_params + ep.header_params if p.get("required")]

        all_resolvable = all(has_matching_id(p["name"], dynamic_id_table) for p in required_params)

        if all_resolvable:
            compatible.append(ep)

    if not compatible:
        raise RuntimeError("No compatible endpoint found to extend sequence.")
    
    base_endpoint = find_endpoint_by_request(base_test["sequence"][-1], endpoints)
    print(f"🧩 Compatible endpoints found: {len(compatible)}")
    scored = sorted(compatible, key=lambda ep: score_candidate(base_endpoint, ep), reverse=True)
    return scored[0]

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

def score_candidate(base_endpoint, candidate):
    score = 0

    # +3 if exactly the same path
    if candidate.path == base_endpoint.path:
        score += 3

    # +2 if candidate path extends the base path
    elif candidate.path.startswith(base_endpoint.path.rstrip("/") + "/"):
        score += 2

    # +1 if same resource root (fallback heuristic)
    elif candidate.path.split("/")[1:2] == base_endpoint.path.split("/")[1:2]:
        score += 1

    # +1 if method differs (encourages exploring other operations on same resource)
    if candidate.method != base_endpoint.method:
        score += 1

    return score


def IS_SEED_ENDPOINT(endpoint) -> bool:
    if any(p.get("required", True) for p in endpoint.path_params):
        return False

    for header in endpoint.header_params:
        name = header["name"].lower()
        if header.get("required", False) and name not in ["content-type", "accept"]:
            return False

    return True


def SELECT_FALLBACK_SEEDS(endpoints, k=3):
    """
    Select fallback seeds if no trivial seed endpoints exist.
    Strategy:
      - Rank endpoints by number of required path params (fewer is easier).
      - Pick k endpoints with the least required path params.
    """
    # Sort endpoints by required path params
    ranked = sorted(endpoints, key=lambda ep: sum(1 for p in ep.path_params if p.get("required", True)))
    selected = ranked[:k]

    return selected
