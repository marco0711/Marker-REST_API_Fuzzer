LOAD_SPEC(path)
Purpose:
Loads the OpenAPI specification from a YAML or JSON file.

Input:
-path: path to the spec file (e.g., "api.yaml")

Output:
-A parsed OpenAPI spec (e.g., a dictionary)

----------------------------------------------------------------------------------------------------------------------------------

PARSE_ENDPOINTS(spec)
Purpose:
Extracts all endpoints (paths + HTTP methods + schema) from the OpenAPI spec.

Input:
-spec: parsed OpenAPI specification

Output:
-A list of endpoint objects, each containing:
    -method
    -path
    -parameters (path/query/body)
    -requestBody schema
    -response schema

----------------------------------------------------------------------------------------------------------------------------------

IS_SEED_ENDPOINT(endpoint)
Purpose:
Decides whether an endpoint is suitable for seeding the corpus (i.e., can run independently).

Input:
-endpoint: an object describing one API endpoint

Output:
-Boolean (True if it can be a seed)

----------------------------------------------------------------------------------------------------------------------------------

BUILD_REQUEST_FROM_SCHEMA(endpoint)
Purpose:
Builds a valid HTTP request using the schema of the endpoint.

Input:
-endpoint object (from OpenAPI)

Output:
-A request object:
    -URL with placeholders or concrete values
    -HTTP method
    -Headers
    -Body (filled according to schema)

----------------------------------------------------------------------------------------------------------------------------------

SEND_REQUEST(request)
Purpose:
Sends the actual HTTP request to the server and gets the response.

Input:
-request: the HTTP request object

Output:
-response: containing status code, headers, body

----------------------------------------------------------------------------------------------------------------------------------

EXTRACT_IDS(response_body)
Purpose:
Extracts dynamically generated resource IDs from the response.

Input:
-JSON response body (as a dict)

Output:
-A dictionary of extracted IDs, e.g., {"userId": "abc123"}

----------------------------------------------------------------------------------------------------------------------------------

UPDATE_ID_TABLE(table, new_ids)
Purpose:
Updates the dynamic ID table with newly extracted IDs.

Input:
-table: current dynamic_id_table
-new_ids: new key-value pairs to add

----------------------------------------------------------------------------------------------------------------------------------

CALCULATE_TCL(response)
Purpose:
Computes a code-coverage proxy (Test Coverage Level) from the response.

Input:
-Final response of the sequence

Output:
-Integer representing the TCL

----------------------------------------------------------------------------------------------------------------------------------

IS_INTERESTING(tcl, diversity_score)
Purpose:
Determines if a sequence should be added to the corpus (diverse and high-coverage).

Input:
-tcl: current test’s Test Coverage Level
-diversity_score: how different the response is from existing tests

Output:
-Boolean

----------------------------------------------------------------------------------------------------------------------------------

SELECT_TEST(corpus)
Purpose:
Selects a test case from the corpus to extend (based on strategy).

Input:
-corpus: list of test entries

Output:
-Selected test entry (dict with sequence, responses, tcl)

----------------------------------------------------------------------------------------------------------------------------------

CHOOSE_COMPATIBLE_ENDPOINT(base_test, spec, dynamic_id_table)
Purpose:
Selects a next endpoint to extend the test, ensuring dependencies can be resolved.

Input:
-base_test: test case from corpus
-spec: OpenAPI spec
-dynamic_id_table: current table of IDs

Output:
-An endpoint whose required IDs are satisfied

----------------------------------------------------------------------------------------------------------------------------------

MUTATE(base_test)
Purpose:
Mutates the request by changing parameters (e.g. using a pairwise combinatorial approach.)

Input:
-base_test: original sequence

Output:
-A mutated test

----------------------------------------------------------------------------------------------------------------------------------

RESOLVE_DEPENDENCIES(request, dynamic_id_table)
Purpose:
Replaces placeholders in path/headers/body with actual values from dynamic_id_table.

Input:
-A request with placeholders (e.g., /users/{userId})
-The ID table

Output:
-A request with actual values (e.g., /users/abc123)

----------------------------------------------------------------------------------------------------------------------------------

CALCULATE_RESPONSE_DIVERSITY(response)
Purpose:
Measures how different the response is from previous ones.

Input:
-Last response from the sequence

Output:
-A numeric diversity score

