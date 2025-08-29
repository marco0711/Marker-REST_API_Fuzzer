from parser.swagger import OpenAPIParser, IS_SEED_ENDPOINT
from generator.request import build_request
from generator.selection import SELECT_TEST
from executor.sender import send_request

# === Configuration ===
SPEC_PATH = "examples/api.json"
BASE_URL = "http://localhost:8888"  # RESTler demo server

# === Step 1: Load and parse the OpenAPI spec ===
parser = OpenAPIParser(SPEC_PATH)
endpoints = parser.parse()

# === Step 2: Build corpus from seed endpoints ===
corpus = []

for ep in endpoints:
    if IS_SEED_ENDPOINT(ep):
        request = build_request(ep)
        test_entry = {
            "sequence": [request],   # single request sequence
            "responses": [],
            "tcl": 0.0,              # no coverage metric yet
            "diversity" : 0.0
        }
        corpus.append(test_entry)

print(f"✅ Corpus initialized with {len(corpus)} seed endpoints.")

if not corpus:
    print("❌ No valid seed endpoints found. Cannot proceed.")
    exit(1)

# === Step 3: Select a test from the corpus ===
selected_test = SELECT_TEST(corpus)
selected_sequence = selected_test["sequence"]

print("\n📦 Selected test sequence:")
for req in selected_sequence:
    print(f"  {req['method']} {req['url']}")

# === Step 4: Send the request(s) ===
responses = []

for req in selected_sequence:
    print(f"\n📡 Sending {req['method']} {req['url']}...")
    response = send_request(req, BASE_URL)
    responses.append(response)

    print("📬 Response:")
    print(f"  Status: {response.get('status')}")
    if response.get("error"):
        print(f"  Error: {response['error']}")
    else:
        print(f"  Headers: {response.get('headers')}")
        print(f"  Body:\n{response.get('body')}")

# === Step 5: (Optional) Update corpus or log ===
# For now, just store the responses in the selected test
selected_test["responses"] = responses
