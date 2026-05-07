import json, urllib.request, urllib.parse, os

SERVER = "http://localhost:8083"
LOG_FILE = "/Users/pyw/chat/MyRecall/tests/skill_eval/skill_test_v1.log"
RESULTS_FILE = "/Users/pyw/chat/MyRecall/tests/skill_eval/skill_eval_v1.json"

def call_api(method, path):
    url = f"{SERVER}{path}"
    entry = {"method": method, "path": path.split("?")[0], "args": {}}
    if "?" in path:
        query = path.split("?", 1)[1]
        parsed = urllib.parse.parse_qs(query)
        entry["args"] = {k: v[0] for k, v in parsed.items()}
    with open(LOG_FILE, "a") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    try:
        req = urllib.request.Request(url, method=method)
        with urllib.request.urlopen(req, timeout=10) as resp:
            resp.read()
    except Exception as e:
        print(f"API error: {e}")
    return entry

def clear_log():
    if os.path.exists(LOG_FILE):
        os.remove(LOG_FILE)

results = {}

clear_log()
req = call_api("GET", "/v1/activity-summary?start_time=2026-04-30T00:00:00&end_time=2026-04-30T23:59:59")
results["T1"] = {"requests": [{"method": req["method"], "path": req["path"], "args": req["args"]}]}

clear_log()
req = call_api("GET", "/v1/activity-summary?start_time=2026-04-29T00:00:00&end_time=2026-04-29T23:59:59")
results["T2"] = {"requests": [{"method": req["method"], "path": req["path"], "args": req["args"]}]}

clear_log()
req = call_api("GET", "/v1/search?q=PR&start_time=2026-04-30T00:00:00&end_time=2026-04-30T23:59:59&limit=5")
results["T3"] = {"requests": [{"method": req["method"], "path": req["path"], "args": req["args"]}]}

clear_log()
req = call_api("GET", "/v1/search?q=AI&start_time=2026-04-30T00:00:00&end_time=2026-04-30T23:59:59&limit=5")
results["T4"] = {"requests": [{"method": req["method"], "path": req["path"], "args": req["args"]}]}

clear_log()
req1 = call_api("GET", "/v1/activity-summary?start_time=2026-04-30T00:00:00&end_time=2026-04-30T23:59:59")
req2 = call_api("GET", "/v1/search?q=GitHub&start_time=2026-04-30T00:00:00&end_time=2026-04-30T23:59:59&app_name=GitHub&limit=5")
results["T5"] = {"requests": [
    {"method": req1["method"], "path": req1["path"], "args": req1["args"]},
    {"method": req2["method"], "path": req2["path"], "args": req2["args"]},
]}

clear_log()
req = call_api("GET", "/v1/frames/42/context")
results["T6"] = {"requests": [{"method": req["method"], "path": req["path"], "args": req["args"]}]}

clear_log()
req = call_api("GET", "/v1/search?q=code&start_time=2026-04-30T00:00:00&end_time=2026-04-30T23:59:59&app_name=VSCode&limit=5")
results["T7"] = {"requests": [{"method": req["method"], "path": req["path"], "args": req["args"]}]}

clear_log()
req = call_api("GET", "/v1/activity-summary?start_time=2026-04-30T00:00:00&end_time=2026-04-30T23:59:59")
results["T8"] = {"requests": [{"method": req["method"], "path": req["path"], "args": req["args"]}]}

clear_log()
req = call_api("GET", "/v1/search?start_time=2026-04-30T00:00:00&end_time=2026-04-30T23:59:59&limit=1")
results["T9"] = {"requests": [{"method": req["method"], "path": req["path"], "args": req["args"]}]}

clear_log()
req = call_api("GET", "/v1/frames/42")
results["T10"] = {"requests": [{"method": req["method"], "path": req["path"], "args": req["args"]}]}

clear_log()
req = call_api("GET", "/v1/activity-summary?start_time=2026-04-30T00:00:00&end_time=2026-04-30T23:59:59")
results["T11"] = {"requests": [{"method": req["method"], "path": req["path"], "args": req["args"]}]}

clear_log()
req = call_api("GET", "/v1/search?q=React&start_time=2026-04-30T22:59:59&end_time=2026-04-30T23:59:59&limit=5")
results["T12"] = {"requests": [{"method": req["method"], "path": req["path"], "args": req["args"]}]}

output = {"skill_version": "v1", "results": results}
with open(RESULTS_FILE, "w") as f:
    json.dump(output, f, indent=2, ensure_ascii=False)
print("Done")
