#!/usr/bin/env python3
import json
import argparse
from urllib.parse import urlparse
import argparse

def normalize_url(url: str) -> str:
    """Return a comparable version of a URL (path only, without base prefixes)."""
    if not url:
        return ""
    parsed = urlparse(url)
    path = parsed.path.lstrip("/")

    # Remove known prefixes like 'petclinic/' or 'api/'
    for prefix in ("petclinic/", "api/", "v1/"):
        if path.startswith(prefix):
            path = path[len(prefix):]
            break

    # Normalize trailing slashes
    return path.rstrip("/")


def load_bugs(file_path: str):
    """Load all bugs from the JSON report file into a flat list of comparable entries."""
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    bugs = []
    for category, entries in data.items():
        for entry in entries:
            req = entry.get("request", {})
            url = normalize_url(req.get("url", ""))
            method = req.get("method", "").upper()
            reason = entry.get("reason", "").strip()

            # Build comparable signature
            sig = (category, method, url, reason)
            bugs.append(sig)

    return bugs


def compare_bugs(brute_bugs, smart_bugs):
    """Compute unique and shared bugs between the two fuzzers."""
    brute_set = set(brute_bugs)
    smart_set = set(smart_bugs)

    shared = brute_set & smart_set
    brute_unique = brute_set - smart_set
    smart_unique = smart_set - brute_set

    return {
        "brute_total": len(brute_bugs),
        "smart_total": len(smart_bugs),
        "brute_unique": len(brute_unique),
        "smart_unique": len(smart_unique),
        "shared": len(shared),
        "brute_unique_details": brute_unique,
        "smart_unique_details": smart_unique
    }


def main():
    parser = argparse.ArgumentParser(description="Compare bug reports from two fuzzers (brute vs smart).")
    parser.add_argument("--brute", required=True, help="Path to brute fuzzer bug JSON report")
    parser.add_argument("--smart", required=True, help="Path to smart fuzzer bug JSON report")
    parser.add_argument("--output", default="comparison_results.txt", help="Path to output file (default: comparison_results.txt)")
    args = parser.parse_args()

    brute_bugs = load_bugs(args.brute)
    smart_bugs = load_bugs(args.smart)

    result = compare_bugs(brute_bugs, smart_bugs)

    with open(args.output, "w", encoding="utf-8") as f:
        f.write("\n=== 🧪 FUZZER BUG COMPARISON RESULTS ===\n")
        f.write(f"Brute fuzzer total bugs: {result['brute_total']}\n")
        f.write(f"Smart fuzzer total bugs: {result['smart_total']}\n")
        f.write(f"Shared bugs: {result['shared']}\n")
        f.write(f"Unique to brute fuzzer: {result['brute_unique']}\n")
        f.write(f"Unique to smart fuzzer: {result['smart_unique']}\n")

        f.write("\n=== 🔍 UNIQUE BUGS (Brute) ===\n")
        if result["brute_unique_details"]:
            for bug in result["brute_unique_details"]:
                f.write(f"{bug}\n")
        else:
            f.write("None\n")

        f.write("\n=== 🔍 UNIQUE BUGS (Smart) ===\n")
        if result["smart_unique_details"]:
            for bug in result["smart_unique_details"]:
                f.write(f"{bug}\n")
        else:
            f.write("None\n")

    print(f"\n✅ Comparison results written to: {args.output}\n")


if __name__ == "__main__":
    main()

