# gestire autenticazione

# Inizializzazione
openapi_spec = LOAD_SPEC("api.yaml")
endpoints = PARSE_ENDPOINTS(openapi_spec)
dynamic_id_table = {}
corpus = []

# Step 1: Generazione test iniziali
for endpoint in endpoints:
    if IS_SEED_ENDPOINT(endpoint):
        request = BUILD_REQUEST_FROM_SCHEMA(endpoint)
        response = SEND_REQUEST(request)
        ids = EXTRACT_IDS(response.body)
        UPDATE_ID_TABLE(dynamic_id_table, ids)
        tcl = CALCULATE_TCL(response)
        # Se la risposta è interessante, salva il test nel corpus
        if IS_INTERESTING(tcl, ?diversity?):
            test_entry = {
                "sequence": [request],
                "responses": [response],
                "tcl": tcl
            }
            corpus.append(test_entry)

# Step 2: Ciclo di fuzzing
while not TIME_BUDGET_EXCEEDED:
    # 2.1: Selezione test dal corpus
    base_test = SELECT_TEST(corpus)

    # 2.2 Scegli un nuovo endpoint da estendere
    next_endpoint = CHOOSE_COMPATIBLE_ENDPOINT(base_test, openapi_spec, dynamic_id_table)

    # 2.3 Costruisci nuova richiesta
    new_request = BUILD_REQUEST_FROM_SCHEMA(next_endpoint)

    # 2.4: Mutazione controllata (pairwise)
    mutated_test = MUTATE(base_test)

    # 2.5: Inserimento ID dinamici nei path/parametri
    resolved_test = RESOLVE_DEPENDENCIES(mutated_test, dynamic_id_table)

    # 2.6 Estendi nuova sequenza
    extended_sequence = base_test["sequence"] + [resolved_request]

    # 2.7 Esegui tutta la sequenza
    responses = []
    for req in extended_sequence:
        resp = SEND_REQUEST(req)
        responses.append(resp)

    # 2.8: Analisi della risposta
    tcl = CALCULATE_TCL(responses[-1])
    ?diversity_score = CALCULATE_RESPONSE_DIVERSITY(responses[-1])?

    if IS_INTERESTING(tcl, diversity_score):
        corpus.append({
            "sequence": extended_sequence,
            "responses": responses,
            "tcl": tcl
        })
    
    # 2.6: Estrazione nuovi ID
    new_ids = EXTRACT_IDS(responses[-1].body)
    UPDATE_ID_TABLE(dynamic_id_table, new_ids)
