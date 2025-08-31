import time
import random
import datetime
import argparse
from parser.swagger import OpenAPIParser
from generator.request import build_request, RESOLVE_DEPENDENCIES
from generator.selection import SELECT_TEST, CHOOSE_COMPATIBLE_ENDPOINT, IS_SEED_ENDPOINT, SELECT_FALLBACK_SEEDS
from feedback.tcl import CALCULATE_DIVERSITY, extract_seq_coverage, calculate_tcl_score
from feedback.utils import print_tcl_breakdown
from feedback.id_tracking import EXTRACT_IDS
from feedback.bug_list import ResponseAnalyzer
from executor.sender import send_sequence
from executor.auth import AuthHandler
from logger.utils import log_iteration_debug
from mutation.mutate import mutate_request, deep_mutation
from utils.utils import sequence_signature

# === Config from CLI ===
cli = argparse.ArgumentParser(description="Run SAPIEN fuzzer")
cli.add_argument("--spec", type=str, default="examples/target-ncs.json",
                    help="Path to OpenAPI specification (JSON/YAML)")
cli.add_argument("--base-url", type=str, default="http://localhost:8080",
                    help="Base URL of the target service")
cli.add_argument("--time", type=int, default=120,
                    help="Maximum fuzzing time in seconds")

args = cli.parse_args()

# === Config ===
SPEC_PATH = args.spec
BASE_URL = args.base_url
MAX_TIME_SECONDS = args.time
ALPHA = 1.0
BETA = 0.5
MUTATION_PROBABILITY = 0.4  
# For adaptive mutation mode
mutation_mode = False
stagnation_counter = 0
STAGNATION_WINDOW = 25
last_total_score = 0.0
#compatible endpoints count
no_comp_count = 0

#MAX_ITERATIONS = 50  
start_time = time.time()

timestamp_prefix = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")


# === Initialization ===
parser = OpenAPIParser(SPEC_PATH)
endpoints = parser.parse()
spec_info = parser.get_spec_info()
param_names = parser.get_dynamic_param_names()
response_analyzer = ResponseAnalyzer(spec_info, timestamp_prefix=timestamp_prefix)
cumulative_coverage = {
    "paths": set(),
    "operations": set(),
    "parameters": set(),
    "status_codes": set(),
    "response_fields": set(),
    "input_content_types": set()
}
seen_signatures = set()

# Use parsed authentication info
auth_handler = AuthHandler(
    auth_type=parser.auth_type,
    token=parser.auth_token,
    header=parser.auth_header
)

print("🔍 Parsed endpoints:")
print(endpoints)

corpus = []
seen_fields = set()
dynamic_id_table = {}

# === Step 1: Generate Seed Corpus ===
print("\n🌱 Initializing seed corpus...")

seed_endpoints = [ep for ep in endpoints if IS_SEED_ENDPOINT(ep)]

if not seed_endpoints:
    print("⚠️ No seed endpoints found — using fallback strategy.")
    seed_endpoints = SELECT_FALLBACK_SEEDS(endpoints, k=3)


for ep in seed_endpoints:
    request = build_request(ep)
    resolved = RESOLVE_DEPENDENCIES(request, dynamic_id_table)
    responses = send_sequence([resolved], BASE_URL, auth_handler=auth_handler)
    last_response = responses[-1]

    #save seeds signatures
    sig = sequence_signature([resolved])
    seen_signatures.add(sig)

    # Genereating log file
    log_iteration_debug(len(corpus) + 1, [resolved], responses, timestamp_prefix, phase="Seed")

    #Response analysis for bugs
    response_analyzer.analyze(resolved, last_response)

    #cumulative tcl 
    seq_coverage = extract_seq_coverage([resolved], responses)
    for k in cumulative_coverage:
        cumulative_coverage[k].update(seq_coverage.get(k, set()))

    # Diversity feedback
    diversity, new_fields = CALCULATE_DIVERSITY(last_response, seen_fields)
    seen_fields.update(new_fields)

    # Coverage feedback
    seq_coverage = extract_seq_coverage([resolved], responses)
    tcl_score = calculate_tcl_score(seq_coverage, spec_info)

    # Extract dynamic IDs
    new_ids = EXTRACT_IDS(last_response["body"], param_names)
    for k, v in new_ids.items():
        dynamic_id_table.setdefault(k, [])
        for val in v:
            if val not in dynamic_id_table[k]:
                dynamic_id_table[k].append(val)

    corpus.append({
        "sequence": [resolved],
        "responses": responses,
        "diversity": diversity,
        "tcl": tcl_score
    })


print(f"✅ Seed corpus initialized with {len(corpus)} tests.\n")
print(dynamic_id_table)

# === Step 2: Fuzzing Loop ===
#for i in range(MAX_ITERATIONS):
i = 0
while time.time() - start_time < MAX_TIME_SECONDS:
    print(f"\n🔁 Iteration {i+1}")
    #print(f"id table:  {dynamic_id_table}")

    try:
        base_test = SELECT_TEST(corpus)
    except ValueError as e:
        print("❌ No tests to select:", e)
        break

    if not mutation_mode:
        #extend sequence if in discovery mode
        try:
            next_ep = CHOOSE_COMPATIBLE_ENDPOINT(base_test, endpoints, dynamic_id_table)
            print(f"➕ Extending with: {next_ep.method} {next_ep.path}")

            new_request = build_request(next_ep)
            resolved_request = RESOLVE_DEPENDENCIES(new_request, dynamic_id_table)

            # Apply mutation probabilistically
            if (not mutation_mode) and (random.random() < MUTATION_PROBABILITY):
                mutated_variants = mutate_request(resolved_request, next_ep.request_body)
                if mutated_variants:
                    resolved_request = random.choice(mutated_variants)
                
            
            extended_sequence = base_test["sequence"] + [resolved_request]
            no_comp_count = 0
    
        except RuntimeError as e:
            no_comp_count +=1
            print("⚠️ No compatible endpoint:", e)

            if no_comp_count >=5 :        
                # collect endpoints not yet in corpus
                used_paths = {req["url"] for test in corpus for req in test["sequence"]}
                unused_endpoints = [ep for ep in endpoints if ep.path not in used_paths]

                if unused_endpoints:
                    next_ep = random.choice(unused_endpoints)
                    print(f"🌱 Forcing exploration with unused endpoint: {next_ep.method} {next_ep.path}")

                new_request = build_request(next_ep)
                resolved_request = RESOLVE_DEPENDENCIES(new_request, dynamic_id_table)
                extended_sequence = [resolved_request]

                no_comp_count = 0
            else:
                continue

    else:
        # MUTATION MODE: mutate entire sequence
        extended_sequence = deep_mutation(base_test["sequence"], endpoints)


    sig = sequence_signature(extended_sequence)
    new_signature = sig not in seen_signatures

    # Run mutation mode trigger logic 
    if not mutation_mode:
        current_total_score = calculate_tcl_score(cumulative_coverage, spec_info)

        if not new_signature:
            stagnation_counter += 1
            print(f"🔁 Duplicate sequence detected, skipping. \n stagnation counter: {stagnation_counter}")
        elif current_total_score <= last_total_score:
            # unique but not useful — softer penalty
            stagnation_counter += 0.2
            seen_signatures.add(sig)
            print(f"⚠️ Unique sequence but no coverage gain. stagnation counter: {stagnation_counter}")
        else:
            stagnation_counter = 0
            seen_signatures.add(sig)

        last_total_score = current_total_score

        if stagnation_counter >= STAGNATION_WINDOW:
                mutation_mode = True
                print(r"""
                        🚨 ENTERING MUTATION MODE 🚨
                        Exploration has stagnated — fuzzing with mutations only.
                        """)
                print(f"\n🔄 Entering MUTATION MODE after {i+1} iterations (stagnation for {STAGNATION_WINDOW})")
                continue

    print(f"📤 Sending sequence: {[req['method'] + ' ' + req['url'] for req in extended_sequence]}")
    responses = send_sequence(extended_sequence, BASE_URL, auth_handler=auth_handler)
    last_response = responses[-1]

    # Producing log file
    log_iteration_debug(i + 1, extended_sequence, responses, timestamp_prefix=timestamp_prefix)

    #Response analysis for bugs
    response_analyzer.analyze(extended_sequence[-1], responses[-1])

    #Cumulative tcl
    seq_coverage = extract_seq_coverage(extended_sequence, responses)
    for k in cumulative_coverage:
        cumulative_coverage[k].update(seq_coverage.get(k, set()))


    # Feedback: diversity
    diversity, new_fields = CALCULATE_DIVERSITY(last_response, seen_fields)
    seen_fields.update(new_fields)

    # Feedback: coverage
    seq_coverage = extract_seq_coverage(extended_sequence, responses)
    tcl_score = calculate_tcl_score(seq_coverage, spec_info)
    #DEBUG 
    #print_tcl_breakdown(seq_coverage, spec_info)

    # Update ID table
    new_ids = EXTRACT_IDS(last_response["body"], param_names)
    for k, v in new_ids.items():
        dynamic_id_table.setdefault(k, [])
        for val in v:
            if val not in dynamic_id_table[k]:
                dynamic_id_table[k].append(val)

    corpus.append({
        "sequence": extended_sequence,
        "responses": responses,
        "diversity": diversity,
        "tcl": tcl_score
    })

    print(f"📈 TCL: {tcl_score:.2f}, Diversity: {diversity:.2f}, Total Corpus: {len(corpus)}")
    time.sleep(0.2)
    i+=1

print("\n🏁 Stateful fuzzing complete.")
final_score = calculate_tcl_score(cumulative_coverage, spec_info)
print(f"\n✅ Final Cumulative TCL Score: {final_score:.2f}")
response_analyzer.write_bug_report()
print(f"\n🐞 Grouped bug report saved to: {response_analyzer.bug_log_path}")
