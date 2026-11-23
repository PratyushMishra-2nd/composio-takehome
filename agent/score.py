"""Score agent output against the human gold set (data/gold.csv), per pass.
Usage: python agent/score.py   -> results/accuracy.json"""
import csv, json
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent

def load(name):
    d = ROOT / "results" / name
    return {int(p.stem): json.loads(p.read_text(encoding="utf-8"))["result"] for p in d.glob("[0-9][0-9][0-9].json")} if d.exists() else {}

def final():
    f = load("pass1"); f.update(load("pass2")); f.update(load("pass3")); f.update(load("pass4")); return f

yn = lambda s: s.strip().lower() in ("yes", "y", "true", "1")

# Auth is scored on what matters for building a toolkit: does the app support OAuth2, and does it
# support a static key/token credential. "API key sent as Bearer" vs "personal access token" is
# vendor naming, not a different integration. Strict set equality is reported separately.
KEYFAM = {"api_key", "bearer_token", "basic", "jwt", "hmac_signature"}
def auth_family(s):
    return ("oauth2" in s, bool(set(s) & KEYFAM))


def score(results, gold):
    fields = {"auth": 0, "access": 0, "mcp_exists": 0, "mcp_official": 0, "verdict": 0}
    misses, n, strict = [], 0, 0
    for g in gold:
        i = int(g["id"]); r = results.get(i)
        if not r: continue
        n += 1
        gauth = {x.strip() for x in g["auth_methods"].split(";") if x.strip()}
        strict += gauth == set(r["auth_methods"])
        checks = {
            "auth": auth_family(gauth) == auth_family(r["auth_methods"]),
            "access": g["access"].strip() == r["access"],
            "mcp_exists": yn(g["mcp_exists"]) == r["mcp_exists"],
            "mcp_official": yn(g["mcp_official"]) == r["mcp_official"],
            "verdict": g["verdict"].strip() == r["verdict"],
        }
        for k, ok in checks.items():
            fields[k] += ok
            if not ok:
                agent_val = sorted(r["auth_methods"]) if k == "auth" else r[k if k != "auth" else "auth_methods"]
                human_val = sorted(gauth) if k == "auth" else g[k if k != "auth" else "auth_methods"]
                misses.append({"id": i, "app": g["app"], "field": k, "agent": agent_val, "human": human_val, "note": g.get("notes", "")})
    total = n * len(fields)
    return {"apps": n, "field_accuracy": {k: round(v / n, 3) if n else None for k, v in fields.items()},
            "auth_strict_set_match": round(strict / n, 3) if n else None,
            "overall": round(sum(fields.values()) / total, 3) if total else None, "misses": misses}

gold = [g for g in csv.DictReader(open(ROOT / "data/gold.csv", encoding="utf-8")) if g["access"].strip()]
out = {"gold_apps": len(gold), "pass1": score(load("pass1"), gold), "final": score(final(), gold)}

# Adjudicated accuracy: a disagreement counts against the agent only if a third check (adjudicate.py)
# ruled for the reference or "neither". "both_defensible" = taxonomy ambiguity, reported separately.
adj_path = ROOT / "results/adjudication.json"
if adj_path.exists():
    adj = json.loads(adj_path.read_text(encoding="utf-8"))
    f = out["final"]; total = f["apps"] * 5
    wrong = 0; rulings = {}
    for m in f["misses"]:
        a = adj.get(f"{m['id']}:{m['field']}")
        m["adjudication"] = a
        ruling = (a or {}).get("ruling", "pending")
        rulings[ruling] = rulings.get(ruling, 0) + 1
        wrong += ruling in ("reference", "neither", "pending", "error")
    out["adjudicated"] = {"overall": round(1 - wrong / total, 3), "agent_wrong": wrong, "rulings": rulings}
    print("adjudicated", out["adjudicated"])

(ROOT / "results/accuracy.json").write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
for k in ("pass1", "final"):
    print(k, out[k]["overall"], out[k]["field_accuracy"])
