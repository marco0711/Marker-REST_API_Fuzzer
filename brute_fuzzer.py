#!/usr/bin/env python3
"""
Brute-force baseline REST API fuzzer.

- Same CLI as main fuzzer: --spec, --target, --time, --out
- Uses the same bug detector as the main fuzzer so outputs are directly comparable.
- Request generation is still dumb (baseline).
"""

from typing import Dict, Any, List
import argparse
import json
import time
import random
import string
import os
import requests
from urllib.parse import urljoin
import datetime


try:
    import yaml
except Exception:
    yaml = None  # optional; if YAML spec used, require pyyaml installed

# === import bug detector ===
#from bug_detector import analyze_response   # <-- make sure this is in your PYTHONPATH
from feedback.bug_list import ResponseAnalyzer

# ----------------------
# Utility: default values
# ----------------------
def simple_default_for_schema(schema: Dict[str, Any]) -> Any:
    if not schema:
        return "fuzz"
    if "schema" in schema and isinstance(schema["schema"], dict):
        schema = schema["schema"]
    t = schema.get("type") or schema.get("format") or "string"
    if t == "integer" or schema.get("format") in ("int32", "int64"):
        return 1
    if t == "number" or schema.get("format") in ("float", "double"):
        return 1.0
    if t == "boolean":
        return True
    return "fuzz"

def random_edge_for_schema(schema: Dict[str, Any]) -> Any:
    if not schema:
        return ''.join(random.choices(string.ascii_letters, k=8))
    if "schema" in schema and isinstance(schema["schema"], dict):
        schema = schema["schema"]
    t = schema.get("type") or "string"
    if t == "integer":
        return random.choice([-1, 0, 2**31 - 1, random.randint(-1000, 1000)])
    if t == "number":
        return random.choice([-1.0, 0.0, float("inf"), -float("inf"), random.uniform(-1000, 1000)])
    if t == "boolean":
        return random.choice([True, False])
    if t == "array":
        return []
    if t == "object":
        return {}
    return random.choice(["", "A" * 512, "\x00", "fuzzed-"+''.join(random.choices(string.ascii_lowercase, k=6))])

# ----------------------
# Minimal spec loader
# ----------------------
def load_spec(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    try:
        return json.loads(text)
    except Exception:
        if yaml:
            return yaml.safe_load(text)
        else:
            raise RuntimeError("Spec is not JSON and PyYAML not available to parse YAML.")

def extract_endpoints(spec: Dict[str, Any]) -> List[Dict[str, Any]]:
    out = []
    paths = spec.get("paths", {})
    for path, ops in paths.items():
        if not isinstance(ops, dict):
            continue
        path_level_params = ops.get("parameters", []) or []
        for method, op in ops.items():
            if method.lower() not in ("get", "post", "put", "delete", "patch", "head", "options"):
                continue
            op_params = op.get("parameters", []) or []
            params = list(path_level_params) + list(op_params)
            request_body = None
            if "requestBody" in op and isinstance(op["requestBody"], dict):
                request_body = op["requestBody"]
            out.append({
                "path": path,
                "method": method.upper(),
                "parameters": params,
                "requestBody": request_body
            })
    return out

# ----------------------
# Request builder (dumb)
# ----------------------
def build_request_for_endpoint(base_url: str, ep: Dict[str, Any], randomize: bool=False) -> Dict[str, Any]:
    url = ep["path"]
    path_params = [p for p in ep.get("parameters", []) if p.get("in") == "path"]
    for p in path_params:
        name = p.get("name")
        schema = p.get("schema", {}) if "schema" in p else p
        val = random_edge_for_schema(schema) if randomize else simple_default_for_schema(schema)
        url = url.replace("{" + name + "}", str(val))

    full_url = urljoin(base_url.rstrip("/") + "/", url.lstrip("/"))

    headers = {"Accept": "application/json"}
    body_data = None
    if ep.get("requestBody"):
        rb = ep["requestBody"]
        content = rb.get("content", {})
        app_json = content.get("application/json")
        if app_json and isinstance(app_json, dict):
            schema = app_json.get("schema", {})
            props = schema.get("properties", {}) if isinstance(schema, dict) else {}
            required = schema.get("required", []) if isinstance(schema, dict) else []
            body = {}
            for req_field in required:
                field_schema = props.get(req_field, {}) if props else {}
                val = random_edge_for_schema(field_schema) if randomize else simple_default_for_schema(field_schema)
                body[req_field] = val
            if body:
                body_data = body
                headers["Content-Type"] = "application/json"
        else:
            body_data = {} if not randomize else {"fuzz": random_edge_for_schema({})}
            headers["Content-Type"] = "application/json"

    return {
        "method": ep["method"],
        "url": full_url,
        "headers": headers,
        "body": body_data
    }

# ----------------------
# Execution / logging with bug detector
# ----------------------
def send_request(req: Dict[str, Any], timeout: int=10) -> Dict[str, Any]:
    method = req["method"].lower()
    url = req["url"]
    headers = req.get("headers", {})
    body = req.get("body")
    start = time.time()
    try:
        if body is not None:
            r = requests.request(method, url, headers=headers, json=body, timeout=timeout)
        else:
            r = requests.request(method, url, headers=headers, timeout=timeout)
        latency = time.time() - start
        return {
            "ok": True,
            "status_code": r.status_code,
            "latency": latency,
            "length": len(r.content or b""),
            "text": r.text,
            "headers": dict(r.headers),
        }
    except Exception as e:
        latency = time.time() - start
        return {
            "ok": False,
            "error": str(e),
            "latency": latency
        }

# ----------------------
# Main loop
# ----------------------
def run_bruteforce(spec_path: str, base_url: str, max_time: int, out_path: str, randomize: bool=False):
    spec = load_spec(spec_path)
    endpoints = extract_endpoints(spec)
    if not endpoints:
        print("No endpoints found in spec.")
        return

    start = time.time()
    iteration = 0

    timestamp_prefix = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    OUTPUT = out_path

    response_analyzer = ResponseAnalyzer(spec, timestamp_prefix=timestamp_prefix, output_path=OUTPUT)

    while time.time() - start < max_time:
        for ep in endpoints:
            iteration += 1
            req = build_request_for_endpoint(base_url, ep, randomize=randomize)
            resp = send_request(req)

            # Run through bug detector
            response_analyzer.analyze(req, resp)

            if resp.get("ok"):
                print(f"[{iteration}] {req['method']} {req['url']} -> {resp['status_code']} ({resp['latency']:.3f}s)")
            else:
                print(f"[{iteration}] {req['method']} {req['url']} -> ERROR: {resp.get('error')}")

            if time.time() - start >= max_time:
                break

    # Save bug log only (identical to main fuzzer)
    response_analyzer.write_bug_report("json")

    print(f"Brute fuzzer finished. Log saved to {out_path}")

# ----------------------
# CLI
# ----------------------
def main():
    ap = argparse.ArgumentParser(description="Brute-force baseline REST fuzzer")
    ap.add_argument("--spec", type=str, default="examples/target-petclinic.json",
                    help="Path to OpenAPI specification (JSON/YAML)")
    ap.add_argument("--target", type=str, default="http://localhost:8080/petclinic",
                    help="Base URL of the target service")
    ap.add_argument("--time", type=int, default=60,
                    help="Maximum fuzzing time in seconds")
    ap.add_argument("--out", default="brute_results/bugs.json",
                    help="Output bug log path (json)")
    ap.add_argument("--randomize", action="store_true", help="Use random/edge values instead of trivial defaults")
    args = ap.parse_args()
    run_bruteforce(args.spec, args.target, args.time, args.out, randomize=args.randomize)

if __name__ == "__main__":
    main()
