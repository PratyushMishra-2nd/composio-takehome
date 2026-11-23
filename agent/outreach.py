"""Ops follow-up queue, executed through Composio (MCP -> GitHub toolkit).

The research says which apps cannot ship until someone gets an approval, a partnership or a customer
account. This step turns each of those into a tracked GitHub issue (one per app) in this repo, using
COMPOSIO_MULTI_EXECUTE_TOOL -> GITHUB_CREATE_AN_ISSUE on the user's Composio-connected GitHub account.
Each issue carries the gate, the evidence, Composio catalog status and a concrete next step, so the
repo's issue list is the approval tracker. Nothing is emailed or sent to any vendor.

Idempotent: created issues are recorded in results/outreach_issues.json and skipped on re-run.
Usage: python agent/outreach.py [--dry-run] [--owner X --repo Y]
"""
import argparse, json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from composio_mcp import call  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "results" / "outreach_issues.json"
GATES = ("admin_approval", "customer_account", "partner_gated")

NEXT_STEP = {
    "admin_approval": "Build the toolkit against a developer account now; in parallel, submit the app for the vendor's review / verification "
                      "(or request the developer token). Track the review ticket here and chase until approved.",
    "customer_account": "Find a design partner: an existing Composio customer who uses this app and can grant a sandbox or test tenant. "
                        "Failing that, ask the vendor's partnerships team for a developer sandbox.",
    "partner_gated": "Apply to the vendor's partner / ISV program or contact sales for API access; record the contact and each follow-up here.",
}


def body(a, cat):
    ev = "\n".join(f"- **{e['field']}**: [{e['url'][:80]}]({e['url']}) {'✅ quote verified on page' if e.get('status') == 'verified' else '⚠️ quote not re-verified'}\n  > {e['quote']}"
                   for e in a["evidence"] if e["field"] in ("access", "auth", "verdict"))
    c = cat.get(str(a["id"]), {})
    comp = f"Already in Composio (`{', '.join(c['matched_toolkits'])}`)" if c.get("in_composio") else "**Not found in Composio's catalog** (toolkit gap)"
    return f"""**Gate:** `{a['access']}` · **Verdict:** `{a['verdict']}` · **Auth:** {', '.join(a['auth_methods'])}
**Composio catalog:** {comp}

**What blocks it**
{a['blocker'] or a['access_detail']}

**Access detail (agent research)**
{a['access_detail']}

**Next step**
{NEXT_STEP.get(a['access'], 'Confirm the gate, then decide build vs outreach.')}

**Evidence**
{ev}

---
Opened automatically by `agent/outreach.py` via Composio MCP (`GITHUB_CREATE_AN_ISSUE`) from the research run. Case study: https://pratyushmishra-2nd.github.io/composio-takehome/"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--owner", default="PratyushMishra-2nd")
    ap.add_argument("--repo", default="composio-takehome")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    data = json.loads((ROOT / "docs" / "data.json").read_text(encoding="utf-8"))
    cat = json.loads((ROOT / "results" / "composio_catalog.json").read_text(encoding="utf-8"))
    done = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    picks = [x for x in data["apps"] if (x["verdict"] == "needs_outreach" or x["access"] in GATES) and str(x["id"]) not in done]
    print(f"{len(picks)} apps need an approval / partnership / customer account", flush=True)
    items = []
    for x in picks:
        labels = [f"gate:{x['access']}", f"verdict:{x['verdict']}", "composio:listed" if cat.get(str(x["id"]), {}).get("in_composio") else "composio:gap"]
        items.append((x, {"tool_slug": "GITHUB_CREATE_AN_ISSUE", "arguments": {
            "owner": a.owner, "repo": a.repo, "title": f"[{x['category']}] {x['app']}: {x['access'].replace('_', ' ')} before toolkit can ship",
            "body": body(x, cat), "labels": labels}}))
    if a.dry_run:
        for x, it in items:
            print("-", it["arguments"]["title"], it["arguments"]["labels"])
        return
    for i in range(0, len(items), 10):
        chunk = items[i:i + 10]
        res = call("COMPOSIO_MULTI_EXECUTE_TOOL", {"tools": [it for _, it in chunk], "thought": "Open approval-tracker issues for gated apps",
                                                   "session_id": "wait"}, timeout=300)
        results = (res or {}).get("data", {}).get("results", []) if isinstance(res, dict) else []
        for (x, _), r in zip(chunk, results):
            resp = r.get("response", r)
            d = (resp.get("data") or resp.get("data_preview") or resp) if isinstance(resp, dict) else {}
            url = d.get("html_url") or (d.get("data") or {}).get("html_url") if isinstance(d, dict) else None
            done[str(x["id"])] = {"app": x["app"], "url": url, "ok": bool(url), "raw": None if url else str(r)[:500]}
            print(f"  #{x['id']:03d} {x['app']}: {url or 'FAILED ' + str(r)[:200]}", flush=True)
        OUT.write_text(json.dumps(done, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
