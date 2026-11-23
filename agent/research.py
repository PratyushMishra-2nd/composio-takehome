"""Research agent: one headless Claude Code worker per app.

Each worker gets web search + web fetch, researches one app's developer docs and
returns JSON validated against agent/schema.json. Every claim must carry a
verbatim quote and the URL it came from, so the verifier can check it later.

Usage:
  python agent/research.py --pass pass1                 # all 100 apps
  python agent/research.py --pass pass1 --ids 1,2,61    # subset
  python agent/research.py --pass pass2 --redo results/redo.json   # re-research flagged fields
"""
import argparse, csv, json, os, subprocess, sys, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCHEMA = (ROOT / "agent" / "schema.json").read_text(encoding="utf-8")
CLAUDE = os.environ.get("CLAUDE_BIN", "claude")

PROMPT = """You are researching ONE app for Composio, which turns apps into tools that AI agents can call.
App: {app}  (category: {category}; hint: {hint})

Find out, from the vendor's own developer documentation wherever possible:
1. What the app does (one line).
2. Every auth method a third-party developer can use against its public API (OAuth2, API key, Basic, bearer/personal token, ...).
3. The gate to get WORKING credentials: free self-serve signup, trial-only, paid plan required, app review / admin approval, or partnership / contact-sales. Check the pricing or plan page if the API is plan-restricted.
4. API surface: REST / GraphQL / etc., and how broad it is.
5. Whether an MCP server exists (vendor-official or credible community), with its URL.
6. Verdict: could an agent toolkit be built today, and the main blocker if not.

Rules:
- Prefer official docs over blogs. Use WebSearch to find the docs, then WebFetch the actual pages.
- Every evidence quote MUST be copied verbatim from the page at that URL (one sentence, <=200 chars). Never paraphrase inside a quote. If you cannot find a supporting quote, lower the confidence instead of inventing one.
- Provide at least one evidence item each for auth, access, api and mcp (for mcp with no server found, cite where you looked and set confidence accordingly).
- If the hint says something specific (e.g. "MCP server", "OAuth requested", "Enterprise API"), check it rather than assuming it.
{extra}
Return only the structured result."""


def load_apps():
    with open(ROOT / "data" / "apps.csv", encoding="utf-8") as f:
        return [dict(r, id=int(r["id"])) for r in csv.DictReader(f)]


def run_one(app, out_dir, model, extra=""):
    out = out_dir / f"{app['id']:03d}.json"
    if out.exists():
        return app["id"], "cached"
    prompt = PROMPT.format(extra=extra, **app)
    cmd = [CLAUDE, "-p", prompt, "--output-format", "json", "--model", model,
           "--json-schema", SCHEMA, "--allowedTools", "WebSearch", "WebFetch",
           "--max-turns", "30",
           # No MCP servers: research only needs WebSearch/WebFetch, and each
           # user-level server costs a node/python process per worker.
           "--strict-mcp-config"]
    t0 = time.time()
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", timeout=900)
    except subprocess.TimeoutExpired:
        return app["id"], "timeout"
    try:
        env = json.loads(p.stdout)
    except json.JSONDecodeError:
        (out_dir / f"{app['id']:03d}.err.txt").write_text(p.stdout + "\n---\n" + p.stderr, encoding="utf-8")
        return app["id"], "bad-json"
    data = env.get("structured_output")
    if data is None:
        try:
            data = json.loads(env.get("result", ""))
        except Exception:
            (out_dir / f"{app['id']:03d}.err.txt").write_text(p.stdout, encoding="utf-8")
            return app["id"], "no-structured-output"
    record = {"id": app["id"], "app": app["app"], "category": app["category"], "hint": app["hint"],
              "model": model, "seconds": round(time.time() - t0), "cost_usd": env.get("total_cost_usd"),
              "turns": env.get("num_turns"), "result": data}
    out.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
    return app["id"], "ok"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pass", dest="pass_name", default="pass1")
    ap.add_argument("--ids", default="")
    ap.add_argument("--redo", default="", help="JSON {id: 'instructions'} from verify.py; re-research only these")
    ap.add_argument("--model", default="sonnet")
    ap.add_argument("--workers", type=int, default=5)
    a = ap.parse_args()

    apps = load_apps()
    extras = {}
    if a.redo:
        extras = {int(k): v for k, v in json.loads(Path(a.redo).read_text(encoding="utf-8")).items()}
        apps = [x for x in apps if x["id"] in extras]
    if a.ids:
        want = {int(i) for i in a.ids.split(",")}
        apps = [x for x in apps if x["id"] in want]

    out_dir = ROOT / "results" / a.pass_name
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"{a.pass_name}: {len(apps)} apps, model={a.model}, workers={a.workers}", flush=True)
    with ThreadPoolExecutor(a.workers) as ex:
        futs = {ex.submit(run_one, x, out_dir, a.model,
                          ("\nA verifier disputed the first answer. Re-check carefully:\n" + extras[x["id"]]) if x["id"] in extras else ""): x
                for x in apps}
        for f in as_completed(futs):
            i, status = f.result()
            print(f"  #{i:03d} {futs[f]['app']}: {status}", flush=True)


if __name__ == "__main__":
    main()
