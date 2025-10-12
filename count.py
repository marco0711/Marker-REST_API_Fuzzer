python3 - <<'EOF'
import json
data = json.load(open("feedback/logs/20251004_125929_bugs_grouped.json"))
print("Top-level type:", type(data))
if isinstance(data, dict):
    for k,v in data.items():
        print(k, "->", len(v))
EOF
