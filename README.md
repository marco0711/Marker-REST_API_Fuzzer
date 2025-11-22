# Marker-REST_API_Fuzzer
Barbieri Marco master thesis 2025, a tool for rest api fuzzing 

## Usage
To run the fuzzer launch the test_fuzz.py script 

```
python3 test_fuzz.py --target [targetURL] --spec [targetOpenAPI] --time [fuzzing_time] --out [path_to_output_dir] --deep-fuzz=[True/False]
```
--target: specify base url of target app to fuzz

--spec: path to OpenAPI spec

--time: time budget in seconds

--out: path to directory in which the results and iteration log will be created

--deep-fuzz: default to False, is specified and set to True it will use the whole time budget for the mutation phase.
Fuzzing will ensure a TCL score >= 3
