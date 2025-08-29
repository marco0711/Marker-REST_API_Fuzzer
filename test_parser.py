import time
from parser.swagger import OpenAPIParser, IS_SEED_ENDPOINT
from generator.request import build_request
from generator.selection import SELECT_TEST, CHOOSE_COMPATIBLE_ENDPOINT, RESOLVE_DEPENDENCIES
from feedback.id_tracking import EXTRACT_IDS
from executor.sender import send_sequence
from feedback.tcl import CALCULATE_TCL, CALCULATE_DIVERSITY

# === Config ===
SPEC_PATH = "examples/api.json"
BASE_URL = "http://localhost:8888"
MAX_ITERATIONS = 10

# === Init ===
parser = OpenAPIParser(SPEC_PATH)
endpoints = parser.parse()

#DEBUG
print(endpoints)

corpus = []
seen_fields = set()
dynamic_id_table = {}

# === Step 1: Generate seed corpus ===
print("🔍 Generating seed corpus...")
for ep in endpoints:
    if IS_SEED_ENDPOINT(ep):
        request = build_request(ep)
        #DEBUG
        print(request)
        responses = send_sequence([request], BASE_URL)
        #DEBUG
        print(responses)
        last = responses[-1]
        
        tcl = CALCULATE_TCL(last)
        diversity, current_fields = CALCULATE_DIVERSITY(last, seen_fields)
        seen_fields.update(current_fields)

        new_ids = EXTRACT_IDS(last["body"])
        for key, values in new_ids.items():
            dynamic_id_table.setdefault(key, []).extend(values)

        corpus.append({
            "sequence": [request],
            "responses": responses,
            "tcl": tcl,
            "diversity": diversity
        })

print(f"✅ Seed corpus initialized with {len(corpus)} tests.\n")

#DEBUG
print("corpus: ", corpus )

# === Step 2: Fuzzing Loop ===
for i in range(MAX_ITERATIONS):
    print(f"\n🔁 Iteration {i+1}")

    try:
        base_test = SELECT_TEST(corpus)
    except ValueError as e:
        print("❌ Corpus empty or invalid:", e)
        break

    try:
        next_ep = CHOOSE_COMPATIBLE_ENDPOINT(base_test, endpoints, dynamic_id_table)
    except RuntimeError as e:
        print("⚠️ No compatible endpoint:", e)
        continue

    new_request = build_request(next_ep)
    resolved_request = RESOLVE_DEPENDENCIES(new_request, dynamic_id_table)
    extended_sequence = base_test["sequence"] + [resolved_request]

    print(f"📤 Sending sequence: {[req['method'] + ' ' + req['url'] for req in extended_sequence]}")

    responses = send_sequence(extended_sequence, BASE_URL)
    last_response = responses[-1]

    tcl = CALCULATE_TCL(last_response)
    diversity, current_fields = CALCULATE_DIVERSITY(last_response, seen_fields)
    seen_fields.update(current_fields)

    new_ids = EXTRACT_IDS(last_response["body"])
    for key, values in new_ids.items():
        dynamic_id_table.setdefault(key, []).extend(values)

    corpus.append({
        "sequence": extended_sequence,
        "responses": responses,
        "tcl": tcl,
        "diversity": diversity
    })

    print(f"📈 TCL: {tcl:.2f}, Diversity: {diversity:.2f}, Total Corpus: {len(corpus)}")
    time.sleep(0.2)

print("\n🏁 Stateful fuzzing complete.")
