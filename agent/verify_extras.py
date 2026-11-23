"""Verify the enrichment fields with the same non-LLM machinery as the core evidence.

1. Quote check on every extra-field quote (plain fetch, then browser-rendered text if
   verify_browser.py --extras has rendered the page).
2. OpenAPI spec: if the agent gives a spec URL, fetch it and confirm it parses as an OpenAPI/Swagger
   or GraphQL document; if APIs.guru lists a spec for the vendor but the agent said "no", flag it.

Usage: python agent/verify_extras.py   -> results/verify_extras.json
"""
import json, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import verify as V  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
FIELDS = ("webhooks", "sandbox", "rate_limits", "sdks", "openapi_spec")


def spec_parses(url):
    if not url.startswith("http"):
        return None
    if "github.com/" in url and "/blob/" in url:
        url = url.replace("github.com/", "raw.githubusercontent.com/").replace("/blob/", "/")
    body = V.fetch(url, timeout=40)
    if body.startswith("__FETCH_FAILED__"):
        return "fetch_failed"
    head = body[:4000].lower()
    if '"openapi"' in head or "openapi:" in head or '"swagger"' in head or "swagger:" in head:
        return "openapi_document"
    if "__schema" in head or "type query" in head:
        return "graphql_schema"
    return "points_to_page"  # a docs page or repo landing page, not the raw spec file


def check(rec):
    r = rec["result"]
    out = {"quotes": {}, "issues": []}
    for f in FIELDS:
        ev = r[f]["evidence"]
        st, note = V.quote_on_page(ev["quote"], ev["url"])
        out["quotes"][f] = {"url": ev["url"], "quote": ev["quote"], "status": st, "note": note}
        if st == "not_found":
            out["issues"].append(("quote_not_found", f, f"Quote for {f} not found on {ev['url']}"))
    spec = r["openapi_spec"]
    out["spec_check"] = spec_parses(spec["url"]) if spec["url"] else None
    app_hint = next((a for a in V_APPS if a["id"] == rec["id"]), {})
    g = V.guru_auth(V.domain_of(app_hint.get("hint", ""), rec["app"]))
    out["apis_guru_spec"] = g["spec"] if g else None
    # A spec counts as confirmed if we downloaded and parsed it, or APIs.guru independently lists one.
    out["spec_confirmed"] = out["spec_check"] in ("openapi_document", "graphql_schema") or bool(g)
    if g and spec["available"] in ("no", "unknown"):
        out["issues"].append(("source_disagrees", "openapi_spec", f"APIs.guru lists an OpenAPI spec ({g['spec']}), agent said {spec['available']}."))
    return rec["id"], out


V_APPS = []


def main():
    import csv
    V_APPS.extend(dict(r, id=int(r["id"])) for r in csv.DictReader(open(ROOT / "data" / "apps.csv", encoding="utf-8")))
    recs = [json.loads(p.read_text(encoding="utf-8")) for p in sorted((ROOT / "results" / "extras").glob("[0-9][0-9][0-9].json"))]
    V.guru_index()
    with ThreadPoolExecutor(12) as ex:
        res = dict(ex.map(check, recs))
    (ROOT / "results" / "verify_extras.json").write_text(json.dumps({str(k): res[k] for k in sorted(res)}, indent=2, ensure_ascii=False), encoding="utf-8")
    q = [x for c in res.values() for x in c["quotes"].values()]
    from collections import Counter
    print(f"{len(res)} apps | extra quotes {len(q)}: {dict(Counter(x['status'] for x in q))}")
    print("spec checks:", dict(Counter(c["spec_check"] for c in res.values())), "| confirmed:", sum(c["spec_confirmed"] for c in res.values()))
    print("issues:", dict(Counter(t for c in res.values() for t, _, _ in c["issues"])))


if __name__ == "__main__":
    main()
