import json
import os
from typing import Dict, List, Optional



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
        status = str(response.get("status"))
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

    def write_bug_report(self):
        with open(self.bug_log_path, "a") as log:
            for category, entries in self.bug_groups.items():
                if not entries:
                    continue
                log.write(f"\n=== {category.upper().replace('_', ' ')} ({len(entries)}) ===\n")
                for entry in entries:
                    log.write(f"\nReason: {entry['reason']}\n")
                    log.write("--- Request ---\n")
                    log.write(json.dumps(entry["request"], indent=2))
                    log.write("\n--- Response ---\n")
                    log.write(json.dumps(entry["response"], indent=2))
                    log.write("\n-----------------------------\n")
