"""Support check: does each confirmed quote actually support the claim it is cited for?

The quote check only proves a quote is present on the cited page. This pass gives a separate,
text-only judge (no web access) each claim next to its quotes and asks: supports / partial / no.
Output feeds per-field "supported" status on the page.

Usage: python agent/support_check.py [--workers 6] [--model haiku]  -> results/support/NNN.json
"""
import argparse, json, os, subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "results" / "support"
CLAUDE = os.environ.get("CLAUDE_BIN", "claude")
SCHEMA = json.dumps({"type": "object", "additionalProperties": False, "required": ["judgements"], "properties": {"judgements": {
    "type": "array", "items": {"type": "object", "additionalProperties": False, "required": ["n", "verdict", "why"], "properties": {
        "n": {"type": "integer"}, "verdict": {"type": "string", "enum": ["supports", "partial", "no"]},
        "why": {"type": "string", "description": "<= 15 words"}}}}}})

PROMPT = """You are checking citations, nothing else. For each numbered item, decide whether the QUOTE supports the CLAIM.
supports = the quote directly states the claim (or its key part); partial = related and consistent but not sufficient alone;
no = the quote is about something else, or is just a title/fragment. Judge only from the text shown. Do not use outside knowledge.

App: {app}
{items}"""


def claim_for(a, field):
    return {
        "auth": f"Auth methods for the public API: {', '.join(a['auth_methods'])}. Detail: {a['auth_detail']}",
        "access": f"Gate to working credentials: {a['access']}. Detail: {a['access_detail']}",
        "api": f"API: {', '.join(a['api_types'])}, breadth {a['api_breadth']}. {a['api_notes']}",
        "mcp": f"MCP server exists: {a['mcp_exists']}; vendor-official: {a['mcp_official']}; {a['mcp_url']}",
        "verdict": f"Verdict: {a['verdict']}. Blocker: {a['blocker']}",
        "description": f"What it does: {a['description']}",
    }[field]


def run(a, model):
    out = OUT / f"{a['id']:03d}.json"
    if out.exists():
        return a["id"], "cached"
    ev = [e for e in a["evidence"] if e.get("status") == "verified"]
    if not ev:
        out.write_text(json.dumps({"id": a["id"], "items": []}), encoding="utf-8")
        return a["id"], "no verified quotes"
    items = "\n".join(f"[{n}] FIELD {e['field']}\nCLAIM: {claim_for(a, e['field'])[:600]}\nQUOTE: \"{e['quote']}\"\n" for n, e in enumerate(ev))
    cmd = [CLAUDE, "-p", PROMPT.format(app=a["app"], items=items), "--output-format", "json", "--model", model,
           "--json-schema", SCHEMA, "--tools", "", "--max-turns", "3", "--strict-mcp-config"]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", timeout=180)
        env = json.loads(p.stdout)
        js = (env.get("structured_output") or json.loads(env["result"]))["judgements"]
    except Exception as e:
        return a["id"], f"error {type(e).__name__}"
    by_n = {j["n"]: j for j in js}
    res = [{"field": e["field"], "url": e["url"], "quote": e["quote"], **{k: by_n.get(n, {}).get(k) for k in ("verdict", "why")}} for n, e in enumerate(ev)]
    out.write_text(json.dumps({"id": a["id"], "app": a["app"], "model": model, "items": res}, indent=2, ensure_ascii=False), encoding="utf-8")
    return a["id"], "ok"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--model", default="haiku")
    a = ap.parse_args()
    apps = json.loads((ROOT / "docs" / "data.json").read_text(encoding="utf-8"))["apps"]
    OUT.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(a.workers) as ex:
        futs = {ex.submit(run, x, a.model): x for x in apps}
        for f in as_completed(futs):
            i, st = f.result()
            print(f"  #{i:03d} {futs[f]['app']}: {st}", flush=True)


if __name__ == "__main__":
    main()
