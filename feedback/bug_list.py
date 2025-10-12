import json
import os
from typing import Dict, List, Optional
from urllib.parse import urlparse

class ResponseAnalyzer:
    def __init__(self, spec_info: Dict, timestamp_prefix: Optional[str] = None, output_path: Optional[str] = None):
        self.valid_status_codes = spec_info.get("status_codes", set())
        self.spec_info = spec_info
        self.bug_groups = {
            "status_code": [],
            "server_error": [],
            "stack_trace": [],
            "empty_body": [],
            "invalid_content_type": [],
        }

        # Set log path
        if timestamp_prefix:
            self.bug_log_path = f"{output_path}/{timestamp_prefix}_bugs_grouped.log"
        else:
            self.bug_log_path = f"{output_path}/bugs_grouped.log"

        os.makedirs(os.path.dirname(self.bug_log_path), exist_ok=True)
        open(self.bug_log_path, "w").close()

    def analyze(self, request: Dict, response: Dict):
        #status = str(response.get("status"))
        status = str(response.get("status") or response.get("status_code"))
        body = response.get("body", "")
        headers = response.get("headers", {})
        content_type = headers.get("Content-Type", "")

        # 1. Undeclared status code
        if status not in self.valid_status_codes:
            self._record_bug("status_code", request, response, f"❗ Undeclared status code: {status}")

        # 2. Server error
        if status.startswith("5"):
            self._record_bug("server_error", request, response, "🔥 Server error")

        # 3. Stack trace patterns
        if any(x in body for x in ["NullPointerException", "StackTrace", "java.lang", "at "]):
            self._record_bug("stack_trace", request, response, "💥 Stack trace or crash pattern detected")

        # 4. Empty body when it shouldn’t be
        allowed_empty_statuses = {"204", "205", "304"}
        status_code = str(status)
        method = request.get("method", "GET")
        url = request.get("url", "")

        # Check if the spec says a body is expected for this response
        body_expected = (method, url, status_code) in self.spec_info.get("response_expectations", set())

        if status_code not in allowed_empty_statuses and body_expected:
            if content_type.startswith("application/json") and not body.strip():
                self._record_bug("empty_body", request, response, "📭 Empty body ")


        # 5. Invalid Content-Type
        if status.startswith("2") and "application/json" not in content_type:
            self._record_bug("invalid_content_type", request, response, f"📦 Unexpected Content-Type: {content_type}")

        # 6. Schema mismatch – placeholder
        # self._record_bug("schema_mismatch", request, response, "⚠️ Schema mismatch detected")

    def _record_bug(self, category: str, request: Dict, response: Dict, reason: str):
        self.bug_groups[category].append({
            "reason": reason,
            "request": request,
            "response": response
        })

    def write_bug_report(self, type: str = "text"):
        """
        Write bug report in either text or JSON format, removing duplicates.
        :param type: "text" (default, human-readable) or "json" (machine-readable).
        """

        # Helper: normalize URLs to remove host/scheme
        def normalize_url(url: str) -> str:
            parsed = urlparse(url)
            return parsed.path or url

        # Deduplicate: build a set of unique bug signatures
        unique_bugs = {}
        for category, entries in self.bug_groups.items():
            seen_signatures = set()
            deduped = []
            for entry in entries:
                req = entry.get("request", {})
                resp = entry.get("response", {})
                method = req.get("method", "")
                url = normalize_url(req.get("url", ""))
                status = str(resp.get("status") or resp.get("status_code"))
                reason = entry.get("reason", "")
                signature = f"{category}|{method}|{url}|{status}|{reason}"
                if signature not in seen_signatures:
                    seen_signatures.add(signature)
                    deduped.append(entry)
            if deduped:
                unique_bugs[category] = deduped

        # Severity order
        severity_order = {
            "server_error": 1,
            "status_code": 2,
            "stack_trace": 3,
            "invalid_content_type": 4,
            "empty_body": 5
        }

        # === TEXT FORMAT ===
        if type == "text":
            sorted_bug_groups = sorted(
                unique_bugs.items(),
                key=lambda kv: severity_order.get(kv[0], 99)
            )

            total_bugs = sum(len(v) for v in unique_bugs.values())

            with open(self.bug_log_path, "w", encoding="utf-8") as log:
                log.write("=== FUZZER BUG REPORT (deduplicated) ===\n")
                log.write(f"Total unique categories with bugs: {len(unique_bugs)}\n")
                log.write(f"Total unique bugs found: {total_bugs}\n")
                log.write("=========================================\n")

                for category, entries in sorted_bug_groups:
                    log.write(f"\n=== {category.upper().replace('_', ' ')} ({len(entries)}) ===\n")
                    for entry in entries:
                        req = entry.get("request", {})
                        resp = entry.get("response", {})
                        method = req.get("method", "")
                        url = normalize_url(req.get("url", ""))
                        status = resp.get("status") or resp.get("status_code")
                        body = resp.get("body", "")
                        text_snippet = resp.get("text", "")[:200] if "text" in resp else ""

                        log.write(f"\nstatus code: {status}\n")
                        log.write(f"operation: {method}\n")
                        log.write(f"url: {url}\n")

                        if body:
                            log.write(f"body: {body[:300]}\n")
                        elif text_snippet:
                            log.write(f"body snippet: {text_snippet}\n")

                        log.write(f"response ok: {resp.get('ok', True)}\n")
                        log.write("-" * 60 + "\n")

                    log.write(f"\n>>> Total unique {category} bugs: {len(entries)}\n")
                    log.write("=" * 60 + "\n")

                log.write("\n=== OVERALL SUMMARY ===\n")
                log.write(f"Total unique bugs across all categories: {total_bugs}\n")
                log.write("=========================================\n")

            print(f"✅ Bug report written to {self.bug_log_path} (deduplicated text summary)")

        # === JSON FORMAT ===
        elif type == "json":
            json_path = self.bug_log_path.replace(".log", ".json")
            with open(json_path, "w", encoding="utf-8") as log:
                json.dump(unique_bugs, log, indent=2)
            print(f"✅ Bug report written to {json_path} (deduplicated JSON)")

        else:
            raise ValueError("Invalid type for write_bug_report. Use 'text' or 'json'.")


