import requests
from typing import Dict, List, Any
from .auth import AuthHandler

def send_request(request: Dict, base_url: str, auth_handler: AuthHandler = None) -> Dict:
    """
    Sends a single HTTP request and returns the response info.
    Automatically includes auth header if available in the auth_handler.
    """
    method = request["method"]
    url = base_url.rstrip("/") + request["url"]
    headers = request.get("headers", {}).copy()
    body = request.get("body", None)

    # Inject auth header if available
    if auth_handler and auth_handler.has_auth():
        headers.update(auth_handler.get_auth_header())

    try:
        response = requests.request(method, url, headers=headers, json=body)
        return {
            "status": response.status_code,
            "body": response.text,
            "headers": dict(response.headers),
        }
    except requests.RequestException as e:
        return {
            "status": "error",
            "error": str(e),
            "body": None,
            "headers": {}
        }

def send_sequence(requests_list: List[Dict[str, Any]], base_url: str, auth_handler: AuthHandler = None) -> List[Dict[str, Any]]:
    """
    Sends a sequence of HTTP requests to the API, one by one.
    Uses available auth headers from auth_handler, and retries with auth if 401/403 received.

    Args:
        requests_list: List of request dicts (method, url, headers, body).
        base_url: Base URL of the API.
        auth_handler: Optional AuthHandler object to provide token/credentials.

    Returns:
        List of response dicts for each request.
    """
    responses = []

    for req in requests_list:
        method = req["method"]
        url = base_url.rstrip("/") + req["url"]
        headers = req.get("headers", {}).copy()
        body = req.get("body", None)

        # Try with auth immediately if available
        if auth_handler and auth_handler.has_auth():
            headers.update(auth_handler.get_auth_header())

        try:
            resp = requests.request(method, url, headers=headers, json=body, timeout=5)

            # Retry if 401/403 and auth_handler is available (token might not have been used)
            if resp.status_code in [401, 403] and auth_handler:
                retry_headers = req.get("headers", {}).copy()
                retry_headers.update(auth_handler.get_auth_header())
                print(f"🔑 Retrying {method} {url} with auth...")
                resp = requests.request(method, url, headers=retry_headers, json=body, timeout=5)

            responses.append({
                "status": resp.status_code,
                "body": resp.text,
                "headers": dict(resp.headers)
            })

        except Exception as e:
            responses.append({
                "status": 0,
                "body": f"Error: {e}",
                "headers": {}
            })

    return responses
