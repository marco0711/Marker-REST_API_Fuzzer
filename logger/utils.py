import json

def log_iteration_debug(iteration_num, sequence, responses, timestamp_prefix, phase="Iteration"):
    with open(f"logger/logs/{timestamp_prefix}_iteration_log.txt", "a") as log_file:
        log_file.write(f"\n=== {phase} {iteration_num} ===\n")
        for i, (req, resp) in enumerate(zip(sequence, responses)):
            log_file.write(f"\n--- Request {i+1} ---\n")
            log_file.write(json.dumps(req, indent=2))
            log_file.write(f"\n--- Response {i+1} ---\n")
            log_file.write(json.dumps(resp, indent=2))
        log_file.write("\n=============================\n")
