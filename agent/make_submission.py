"""One-page submission PDF (the form takes a single file). Numbers come from docs/data.json.
Usage: python agent/make_submission.py -> submission/Pratyush_Mishra_Composio_takehome.pdf"""
import json
from pathlib import Path
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

ROOT = Path(__file__).resolve().parent.parent
D = json.loads((ROOT / "docs" / "data.json").read_text(encoding="utf-8"))
P, V = D["patterns"], D["verification"]
acc = V["accuracy"]
c = dict(P["verdict"]); ac = dict(P["access"]); au = dict(P["auth"])
gaps_now = [g["app"] for g in P["composio_gaps"] if g["verdict"] == "build_now"]
LIVE = "https://pratyushmishra-2nd.github.io/composio-takehome/"
REPO = "https://github.com/PratyushMishra-2nd/composio-takehome"
ISSUES = REPO + "/issues"

ink, muted, blue = colors.HexColor("#0b0b0b"), colors.HexColor("#52514e"), colors.HexColor("#2a78d6")
H1 = ParagraphStyle("h1", fontName="Helvetica-Bold", fontSize=16, leading=19, textColor=ink, spaceAfter=2)
H2 = ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=10.5, leading=13, textColor=ink, spaceBefore=7, spaceAfter=3)
B = ParagraphStyle("b", fontName="Helvetica", fontSize=8.8, leading=11.6, textColor=ink)
S = ParagraphStyle("s", parent=B, textColor=muted, fontSize=8.2, leading=10.5)
L = lambda url, text=None: f'<link href="{url}" color="#2a78d6"><u>{text or url}</u></link>'
pct = lambda x: f"{round(x * 100)}%"

story = [
    Paragraph("100 apps, one agent: turning apps into agent toolkits", H1),
    Paragraph("Composio · AI Product Ops Intern take-home · Pratyush Mishra", S),
    Spacer(1, 6),
    Table([[Paragraph("<b>Live case study</b>", B), Paragraph(L(LIVE), B)],
           [Paragraph("<b>Source repo + README</b>", B), Paragraph(L(REPO), B)],
           [Paragraph("<b>Approval tracker</b>", B), Paragraph(L(ISSUES) + f" ({P['tracker_issues']} issues opened by the agent via Composio)", B)],
           [Paragraph("<b>Machine-readable</b>", B), Paragraph(L(LIVE + "data.json") + " (all fields, evidence and checks for agents)", B)]],
          colWidths=[38 * mm, 136 * mm],
          style=TableStyle([("BOX", (0, 0), (-1, -1), 0.6, blue), ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f3f7fd")),
                            ("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)])),
    Paragraph("The patterns", H2),
]
pts = [
    f"<b>Half are easy wins.</b> {c.get('build_now', 0)} of 100 can ship as a toolkit today; {c.get('build_with_caveat', 0)} with a caveat; only "
    f"{c.get('needs_outreach', 0) + c.get('not_buildable', 0)} need outreach or have no usable API.",
    f"<b>The blocker is credentials, not APIs.</b> {ac.get('self_serve_free', 0)} give free self-serve credentials; the rest hit vendor app review "
    f"({ac.get('admin_approval', 0)}), trial-only ({ac.get('self_serve_trial', 0)}), paid plan ({ac.get('paid_plan', 0)}), customer-only "
    f"({ac.get('customer_account', 0)}) or partnership ({ac.get('partner_gated', 0)}). The real question is \"can strangers connect it?\".",
    "<b>Friction clusters</b> in sales-led support/finance SaaS (customer-only: DealCloud, Gladly, Pylon, Brex, PitchBook) and ad platforms "
    "(app review / developer tokens: Google, Meta, LinkedIn Ads). Dev-infra and productivity are nearly all build-now.",
    f"<b>Both auth modes matter.</b> {au.get('oauth2', 0)} offer OAuth2, {P['both']} offer OAuth2 <i>and</i> a key/token; key-only apps "
    f"({P['key_only']}) concentrate in data/SEO and AI-native tools. MCP is table stakes: {P['mcp_any']} have a server, {P['mcp_official']} official.",
    f"<b>For Composio:</b> {P['composio_listed']} of 100 already resolve to a toolkit (checked through Composio's MCP); {len(P['composio_gaps'])} are gaps, "
    f"{len(gaps_now)} buildable now ({', '.join(gaps_now)}).",
]
story += [Paragraph(f"{i}. {t}", B) for i, t in enumerate(pts, 1)]
story += [
    Paragraph("The agent, and where a human was needed", H2),
    Paragraph("One headless Claude Code worker per app (WebSearch + WebFetch, JSON-schema output, a verbatim quote + URL required for every field) → "
              "a non-LLM verifier (re-fetches each cited page to confirm the quote; cross-checks auth with APIs.guru OpenAPI specs, MCP with the official "
              "MCP registry, consistency rules) → targeted re-research of flagged apps in two rounds → Composio MCP: catalog coverage "
              "(<font face='Courier'>COMPOSIO_SEARCH_TOOLS</font>) and an approval tracker (<font face='Courier'>GITHUB_CREATE_AN_ISSUE</font> via "
              "<font face='Courier'>COMPOSIO_MULTI_EXECUTE_TOOL</font>). Human decisions: the access taxonomy (a <i>customer-only</i> gate was split out after "
              "pass 1), which loops to keep, one OAuth click to connect GitHub, and the final review of the sample and every disagreement.", B),
    Paragraph("Verification, honestly", H2),
    Paragraph(f"Quotes found verbatim on the cited page: {V['pass1_quotes']['verified']}/{V['pass1_quotes']['total']} in pass 1 → "
              f"{V['final_quotes']['verified']}/{V['final_quotes']['total']} final. On a seeded 20-app sample checked blind by an independent model: "
              f"<b>{pct(acc['pass1']['overall'])} → {pct(acc['final']['overall'])}</b> field accuracy (auth {pct(acc['pass1']['field_accuracy']['auth'])} → "
              f"{pct(acc['final']['field_accuracy']['auth'])}); a third check on each remaining disagreement puts it at {pct(acc['adjudicated']['overall'])}. "
              f"One loop made things worse (a gate audit dropped accuracy to {pct(V['experiment_gate_audit']['overall'])}) and was rolled back; it is kept in the "
              "repo as an experiment. Gate classification remains the hardest field; misses are listed on the page.", B),
    Spacer(1, 5),
    Paragraph(f"Run: <font face='Courier'>python agent/research.py --pass try --ids 61</font> (one app) · full pipeline in the README. "
              f"Data generated {D['generated']}.", S),
]
out = ROOT / "submission" / "Pratyush_Mishra_Composio_takehome.pdf"
out.parent.mkdir(exist_ok=True)
SimpleDocTemplate(str(out), pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=14 * mm, bottomMargin=12 * mm,
                  title="Composio take-home: 100 apps → agent toolkits", author="Pratyush Mishra").build(story)
print(out, out.stat().st_size, "bytes")
