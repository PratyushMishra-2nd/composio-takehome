"""Composio coverage check, through Composio's own MCP (COMPOSIO_SEARCH_TOOLS).

For each of the 100 apps, ask Composio's tool router for that app's tools and record which toolkit(s)
it resolves to and how many tools. This replaces guessing composio.dev/toolkits/<slug> pages, and
lets the page answer the question that matters for Composio: which researched apps are NOT yet
toolkits, and which of those are easy wins (the build backlog).

Usage: python agent/composio_catalog.py   -> results/composio_catalog.json
"""
import csv, json, re, sys, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from composio_mcp import call  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "results" / "composio_catalog.json"


def norm(s):
    return re.sub(r"[^a-z0-9]", "", s.lower())


def tokens(app):
    base = app.split("(")[0]
    t = {norm(base)}  # whole name only: single words like "cloud" or "google" cause false matches
    alias = {"Google Ads": {"googleads"}, "Meta Ads": {"metaads", "facebookads", "facebook"}, "LinkedIn Ads": {"linkedin"},
             "WhatsApp Business": {"whatsapp"}, "Threads (Meta)": {"threads"}, "Amazon Selling Partner": {"amazon", "sellingpartner"},
             "Magento (Adobe Commerce)": {"magento", "adobecommerce"}, "Salesforce Commerce Cloud": {"commercecloud", "salesforcecommerce"},
             "Lark (Larksuite)": {"lark", "larksuite"}, "Monday.com": {"monday"}, "Waterfall.io": {"waterfall"},
             "systeme.io": {"systeme", "systemeio"}, "QuickBooks": {"quickbooks"}, "YouTube Transcript": {"youtube", "transcript"},
             "Mermaid CLI": {"mermaid"}, "GoHighLevel": {"highlevel"}, "Zoho CRM": {"zoho"}, "Help Scout": {"helpscout"},
             "MongoDB Atlas": {"mongodb", "mongo"}, "Bright Data": {"brightdata"}, "NotebookLM": {"notebooklm"}, "Neo4j": {"neo4j"}, "Otter AI": {"otter"}, "Paygent Connect": {"paygent"}}
    return t | alias.get(app, set())


PHRASINGS = ["use the {app} API ({hint}): list or read records", "{app}", "{app} {category}: search, list and get items"]


def check(app, phrasing=0):
    q = [{"use_case": PHRASINGS[phrasing].format(app=app["app"], hint=app["hint"], category=app["category"])}]
    for attempt in range(3):
        try:
            res = call("COMPOSIO_SEARCH_TOOLS", {"queries": q})
            break
        except Exception as e:  # transient network errors
            err = str(e); time.sleep(3 * (attempt + 1))
    else:
        return app["id"], {"error": err}
    data = (res or {}).get("data", {}) if isinstance(res, dict) else {}
    r0 = (data.get("results") or [{}])[0]
    toolkits = r0.get("toolkits") or []
    statuses = {s["toolkit"]: s for s in data.get("toolkit_connection_statuses", [])}
    toks = tokens(app["app"])
    match = [t for t in toolkits if any(k and (k in norm(t) or norm(t) in k) for k in toks)]
    return app["id"], {
        "app": app["app"], "toolkits_returned": toolkits, "matched_toolkits": match,
        "in_composio": bool(match),
        "primary_tools": r0.get("primary_tool_slugs", []), "related_tools": r0.get("related_tool_slugs", []),
        "toolkit_description": next((statuses[t]["description"] for t in match if t in statuses), ""),
        "guidance": r0.get("execution_guidance", ""), "phrasing": phrasing,
    }


def check_all_phrasings(app):
    # Tool search is semantic: a miss on one phrasing is not proof of absence, so try all three.
    seen = []
    for k in range(len(PHRASINGS)):
        i, r = check(app, k)
        seen += r.get("toolkits_returned", [])
        if r.get("in_composio"):
            break
    r["toolkits_returned_all"] = sorted(set(seen))
    return i, r


def main():
    apps = [dict(r, id=int(r["id"])) for r in csv.DictReader(open(ROOT / "data" / "apps.csv", encoding="utf-8"))]
    done = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    todo = apps if "--all" in sys.argv else [a for a in apps if str(a["id"]) not in done or "error" in done[str(a["id"])]]
    print(f"checking {len(todo)} apps against Composio's catalog via MCP", flush=True)
    with ThreadPoolExecutor(6) as ex:
        for i, r in ex.map(check_all_phrasings, todo):
            done[str(i)] = r
            print(f"  #{i:03d} {r.get('app')}: {r.get('matched_toolkits') or r.get('error') or '-'}  (returned {r.get('toolkits_returned')})", flush=True)
    OUT.write_text(json.dumps(dict(sorted(done.items(), key=lambda kv: int(kv[0]))), indent=2, ensure_ascii=False), encoding="utf-8")
    print("in composio:", sum(1 for v in done.values() if v.get("in_composio")), "/", len(done))


if __name__ == "__main__":
    main()
