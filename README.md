# 100 apps → agent toolkits: research agent + verification loop

Composio AI Product Ops Intern take-home. **Live case study:** https://pratyushmishra-2nd.github.io/composio-takehome/

For each of 100 apps, an agent researches: what the app does, auth methods, the gate to working credentials (self-serve / trial / paid / app review / customer-only / partner), API surface, existing MCP servers, and a buildability verdict with the main blocker. Every answer carries a verbatim quote and the URL it came from. The page leads with the patterns, then the full matrix, the agent and the accuracy story.

## How it works

```
data/apps.csv ──► agent/research.py ──► results/pass1/*.json
                  (1 headless Claude Code worker per app,
                   WebSearch + WebFetch, JSON-schema output,
                   quote + URL required per field)
                         │
                         ▼
                  agent/verify.py  (no LLM)
                   1. re-fetch every cited URL, check the quote is on the page
                   2. auth vs APIs.guru OpenAPI securitySchemes
                   3. MCP claim vs official MCP registry (vendor-namespaced = official)
                   4. verdict vs Composio's public toolkit catalog
                   5. consistency rules (contradictions, missing evidence, low confidence)
                         │  results/redo_pass1.json  (per-app list of disputes)
                         ▼
                  agent/research.py --pass pass2 --redo …   (round 1: targeted re-research, 47 apps)
                         │
                         ▼
                  agent/verify.py --pass final  + claim-coverage rules learned from the blind sample
                         │  (every OAuth2 claim needs a verified quote naming OAuth; no MCP-login OAuth; no OAuth 1.0a)
                         ▼
                  agent/research.py --pass pass3 --redo …   (round 2, 52 apps)
                         │
                         ▼
                  gate audit: every self-serve app re-checked for public-app review / ISV status / paid plan
                  agent/research.py --pass pass4 --redo results/redo_gate_audit.json
                         │
                         ▼
                  agent/score.py      (vs data/gold.csv: blind independent check on 20 apps)
                  agent/adjudicate.py (third check rules on every remaining disagreement)
                         │
                         ▼
                  Composio MCP (connect.composio.dev/mcp)
                   agent/composio_catalog.py  COMPOSIO_SEARCH_TOOLS per app -> in catalog or gap (3 phrasings)
                   agent/outreach.py          COMPOSIO_MULTI_EXECUTE_TOOL -> GITHUB_CREATE_AN_ISSUE
                                              one approval-tracker issue per gated app (repo Issues tab)
                         │
                         ▼
                  agent/build.py ──► docs/data.json ──► docs/index.html
```

## Run it

Requirements: Python 3.10+, `pip install playwright && playwright install chromium` (browser-use loop and PDF), the [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code) logged in (`claude` on PATH), and for the Composio steps a Composio key in `.env`:

```
COMPOSIO_API_KEY=ck_...      # composio.dev dashboard; used as Bearer token for https://connect.composio.dev/mcp
```

Research runs through the Claude Code CLI's own login; the verification sources are public; the Composio steps go through Composio's MCP server (`agent/composio_mcp.py` is a ~60-line client). The tracker step needs GitHub connected once in Composio (`COMPOSIO_MANAGE_CONNECTIONS`, one OAuth click).

```bash
python agent/research.py --pass try --ids 61          # one app (GitHub), ~40 s
python agent/research.py --pass pass1 --workers 6     # all 100, ~15 min
python agent/verify.py   --pass pass1                 # writes results/verify_pass1.json + redo_pass1.json
python agent/research.py --pass pass2 --redo results/redo_pass1.json
python agent/verify.py   --pass final                 # round 2 checks -> results/redo_final.json
cp results/redo_final.json results/redo_pass2.json && cp results/verify_final.json results/verify_round2.json
python agent/research.py --pass pass3 --redo results/redo_pass2.json
python agent/research.py --pass pass4 --redo results/redo_gate_audit.json   # gate audit (list built from self-serve apps)
python agent/verify.py   --pass final
python agent/verify_browser.py && python agent/verify.py --pass final   # browser-use loop: render JS-heavy cited pages in headless Chromium
python agent/score.py                                 # accuracy vs the blind sample check
python agent/adjudicate.py && python agent/score.py   # third check on disagreements
python agent/composio_catalog.py --all                # Composio coverage via MCP -> results/composio_catalog.json
python agent/outreach.py --dry-run                    # preview approval-tracker issues; drop --dry-run to create them
python agent/build.py                                 # docs/data.json
python -m http.server -d docs 8000                    # open http://localhost:8000
```

Results are cached per app, so a re-run only researches missing apps. Delete `results/<pass>/` to start over.

## Files

| Path | What |
|---|---|
| `data/apps.csv` | The 100 apps from the brief (id, app, category, hint) |
| `agent/schema.json` | Output contract for each worker, including the taxonomy definitions |
| `agent/research.py` | Research agent (parallel headless `claude -p` workers) |
| `agent/verify.py` | Independent, non-LLM verification + re-research queue |
| `agent/sample.py` | Picks the human sample: 2 per category, seed 42 |
| `data/gold.csv`, `data/GOLD_GUIDE.md` | Blind reference check on the 20-app sample (independent model, never saw agent output), and the rules used |
| `agent/adjudicate.py` | Third check: rules on each remaining agent-vs-reference disagreement |
| `agent/verify_browser.py` | Browser-use loop: renders unconfirmed cited pages in headless Chromium for the quote check |
| `agent/make_submission.py` | One-page submission PDF, built from the same data as the page |
| `agent/score.py` | Field-level accuracy of pass 1 and final vs the reference set, plus adjudicated accuracy |
| `agent/composio_mcp.py` | Minimal client for Composio's MCP server |
| `agent/composio_catalog.py` | Which of the 100 apps already have a Composio toolkit (gap backlog) |
| `agent/outreach.py` | Opens one GitHub issue per gated app via Composio (approval tracker) |
| `agent/build.py` | Merges everything into `docs/data.json` (also the machine-readable export) |
| `results/` | Raw per-app outputs for every pass, verifier reports, accuracy |

## Where Composio is used, and where it is not

- **Used:** the catalog check, which asks Composio's tool router for every app, and the approval tracker, which creates GitHub issues through Composio's GitHub toolkit. Both go through Composio's MCP server.
- **Not used:** the research workers search the web with Claude Code's built-in WebSearch/WebFetch. Routing them through Composio's search toolkits (Exa/Tavily/Firecrawl) is a one-line `--mcp-config` change, but it would have meant re-running all 100 apps against the starter credit inside the 8-hour window.

## Known limits

- The quote check uses a plain HTTP fetch first, then a browser-use loop (`agent/verify_browser.py`, headless Chromium via Playwright) for pages the fetch couldn't read or match. That raised confirmed quotes from 639 to 677 of 698.
- The Composio catalog check uses semantic tool search: an app counts as a gap only after 3 phrasings fail to return a toolkit whose name matches. A gap is therefore "not found by the router", not proof of absence.
- The access taxonomy was revised after pass 1 (`customer_account` was split out of `admin_approval`). Every pass 1 app in the old bucket was re-researched under the new definitions.
