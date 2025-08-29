import json
import yaml
import requests
from typing import Dict, List, Any, Optional, Set


class Endpoint:
    def __init__(self, path: str, method: str, parameters: List[Dict], request_body: Optional[Dict], responses: Dict, raw: Optional[Dict] = None):
        self.path = path
        self.method = method.upper()
        self.parameters = parameters
        self.request_body = request_body
        self.responses = responses
        self.raw = raw

        self.path_params = [p for p in parameters if p.get("in") == "path"]
        self.query_params = [p for p in parameters if p.get("in") == "query"]
        self.header_params = [p for p in parameters if p.get("in") == "header"]

    def __repr__(self):
        return f"<{self.method} {self.path}>"


class OpenAPIParser:
    def __init__(self, spec_path: str, config_path: str = "config.json"):
        self.spec_path = spec_path
        self.spec = self._load_spec()
        self.version = self._detect_version()
        self.endpoints: List[Endpoint] = []
        self.requires_auth = False
        self.auth_type = None  # 'apiKey', 'http', 'bearer', etc.
        self.auth_token = None
        self.auth_header = {}
        self.config = self._load_config(config_path)
        self._check_auth_requirements()
        if self.config.get("auth_path"):
            self._attempt_auth()

    def _load_spec(self) -> Dict:
        with open(self.spec_path, 'r') as f:
            return yaml.safe_load(f) if self.spec_path.endswith(('.yaml', '.yml')) else json.load(f)

    def _load_config(self, path: str) -> Dict:
        try:
            with open(path, 'r') as f:
                return json.load(f)
        except Exception:
            return {}

    def _detect_version(self) -> str:
        if 'swagger' in self.spec:
            return '2.0'
        elif 'openapi' in self.spec:
            return self.spec['openapi'].split('.')[0]
        else:
            raise ValueError("Unknown OpenAPI version")

    def _check_auth_requirements(self):
        self.requires_auth = bool(self.spec.get("security", []))
        security_schemes = self.spec.get("components", {}).get("securitySchemes", {}) \
            if self.version == "3" else self.spec.get("securityDefinitions", {})

        for name, scheme in security_schemes.items():
            self.auth_type = scheme.get("type")
            break  # Use the first available scheme

    def _attempt_auth(self):
        """
        Perform authentication at auth_path if specified in config.
        Token or key is stored for later use in requests.
        """
        auth_path = self.config.get("auth_path")
        if not auth_path:
            return

        base_url = self.config.get("base_url", "").rstrip("/")
        url = f"{base_url}{auth_path}"
        headers = {"Content-Type": "application/json"}

        try:
            if self.auth_type == "http" or self.auth_type == "basic":
                username = self.config.get("username")
                password = self.config.get("password")
                r = requests.post(url, json={"username": username, "password": password}, headers=headers)

            elif self.auth_type == "apiKey":
                key_name = self.config.get("key_name")
                key_value = self.config.get("key_value")
                r = requests.post(url, headers={key_name: key_value})

            elif self.auth_type == "bearer":
                token = self.config.get("token")
                r = requests.post(url, headers={"Authorization": f"Bearer {token}"})

            else:
                print(f"⚠️ Unsupported auth_type '{self.auth_type}' for automatic login.")
                return

            if r.status_code in [200, 201]:
                data = r.json()
                token = data.get("token") or data.get("access_token") or data.get("key")
                if token:
                    self.auth_token = token
                    self.auth_header = {"Authorization": f"Bearer {token}"}
                    print("🔐 Auth token successfully retrieved.")
            else:
                print(f"⚠️ Auth request failed with status {r.status_code}")
        except Exception as e:
            print("❌ Authentication error:", e)

    def parse(self) -> List[Endpoint]:
        if self.endpoints:
            return self.endpoints

        paths = self.spec.get("paths", {})
        for path, methods in paths.items():
            for method, op_obj in methods.items():
                parameters = op_obj.get("parameters", [])
                request_body = None
                responses = {}

                if self.version == '3':
                    request_body = self._extract_request_body_v3(op_obj)
                    responses = self._extract_responses_v3(op_obj)
                elif self.version == '2.0':
                    request_body = self._extract_request_body_v2(parameters)
                    responses = self._extract_responses_v2(op_obj)

                self.endpoints.append(Endpoint(
                    path=path,
                    method=method,
                    parameters=parameters,
                    request_body=request_body,
                    responses=responses,
                    raw=op_obj
                ))
        return self.endpoints
    
    def get_spec_info(self) -> Dict[str, Set[str]]:
        paths = set()
        operations = set()
        parameters = set()
        status_codes = set()
        response_fields = set()
        input_content_types = set()
        response_expectations = set()  

        for ep in self.endpoints:
            paths.add(ep.path)
            operations.add((ep.method, ep.path))

            for p in ep.parameters:
                parameters.add(p["name"])

            if ep.request_body:
                for name in ep.request_body.get("properties", {}).keys():
                    parameters.add(name)

            if self.version == '3':
                if ep.raw.get("requestBody"):
                    content = ep.raw["requestBody"].get("content", {})
                    for ctype in content:
                        input_content_types.add((ep.method, ep.path, ctype))

            elif self.version == '2.0':
                input_content_types.add((ep.method, ep.path, "application/json"))

            if "responses" in ep.raw:
                for code, resp in ep.raw["responses"].items():
                    status_codes.add(str(code))
                    content = resp.get("content", {})
                    schema = content.get("application/json", {}).get("schema", {})

                    if not schema and self.version == '2.0':
                        schema = resp.get("schema", {})

                    if "$ref" in schema:
                        schema = self._resolve_ref(schema["$ref"])

                    if schema:
                        fields = schema.get("properties", {})
                        for name in fields:
                            response_fields.add(name)

                    #track body-expecting responses
                    if schema or ("content" in resp and resp["content"]):
                        response_expectations.add((ep.method, ep.path, str(code)))

        return {
            "paths": paths,
            "operations": operations,
            "parameters": parameters,
            "status_codes": status_codes,
            "response_fields": response_fields,
            "input_content_types": input_content_types,
            "response_expectations": response_expectations, 
        }


    def _extract_request_body_v3(self, op_obj: Dict) -> Optional[Dict]:
        content = op_obj.get("requestBody", {}).get("content", {})
        app_json = content.get("application/json", {})
        schema = app_json.get("schema", None)
        if schema:
            schema = self._resolve_schema(schema)
            required = schema.get("required", [])
            properties = schema.get("properties", {})
            return {"properties": properties, "required": required}
        return None



    def _extract_request_body_v2(self, parameters: List[Dict]) -> Optional[Dict]:
        for param in parameters:
            if param.get("in") == "body":
                schema = param.get("schema")
                if schema:
                    schema = self._resolve_schema(schema)
                    required = schema.get("required", [])
                    properties = schema.get("properties", {})
                    return {"properties": properties, "required": required}
        return None


    def _extract_responses_v3(self, op_obj: Dict) -> Dict:
        responses = op_obj.get("responses", {})
        parsed_responses = {}
        for status_code, response_obj in responses.items():
            if "$ref" in response_obj:
                response_obj = self._resolve_ref(response_obj["$ref"])
            description = response_obj.get("description", "")
            content = response_obj.get("content", {})
            parsed_content = {}
            for mime, mime_obj in content.items():
                schema = mime_obj.get("schema")
                if schema:
                    schema = self._resolve_schema(schema)
                parsed_content[mime] = schema
            parsed_responses[status_code] = {"description": description, "content": parsed_content}
        return parsed_responses


    def _extract_responses_v2(self, op_obj: Dict) -> Dict:
        responses = op_obj.get("responses", {})
        parsed_responses = {}

        for status_code, response_obj in responses.items():
            # Resolve top-level $ref on the response object itself
            if "$ref" in response_obj:
                response_obj = self._resolve_ref(response_obj["$ref"])

            description = response_obj.get("description", "")
            schema = response_obj.get("schema", {})

            # Fully resolve nested $ref within the schema
            schema = self._resolve_schema(schema)

            parsed_responses[status_code] = {
                "description": description,
                "content": {"application/json": schema} if schema else {}
            }

        return parsed_responses


    def _resolve_ref(self, ref: str) -> Optional[Dict]:
        parts = ref.lstrip("#/").split("/")
        obj = self.spec
        for part in parts:
            obj = obj.get(part)
            if obj is None:
                return None
        return obj
    
    def _resolve_schema(self, schema: Dict, seen_refs: Optional[Set[str]] = None) -> Dict:
        if not isinstance(schema, dict):
            return schema  # base case: not a dict

        if seen_refs is None:
            seen_refs = set()

        # If schema is a $ref, resolve it (unless it's already seen)
        if "$ref" in schema:
            ref = schema["$ref"]
            if ref in seen_refs:
                return {}  # Prevent infinite recursion
            seen_refs.add(ref)
            resolved = self._resolve_ref(ref)
            return self._resolve_schema(resolved, seen_refs)

        # Recursively resolve properties
        if "properties" in schema:
            resolved_props = {}
            for key, value in schema["properties"].items():
                resolved_props[key] = self._resolve_schema(value, seen_refs.copy())
            schema["properties"] = resolved_props

        # Resolve array items
        if "items" in schema:
            schema["items"] = self._resolve_schema(schema["items"], seen_refs.copy())

        # Optionally handle allOf / anyOf / oneOf
        for comb in ["allOf", "anyOf", "oneOf"]:
            if comb in schema:
                schema[comb] = [self._resolve_schema(s, seen_refs.copy()) for s in schema[comb]]

        return schema



    def get_dynamic_param_names(self) -> Set[str]:
        param_names = set()
        for ep in self.endpoints:
            for p in ep.path_params:
                param_names.add(p["name"])
        return param_names
