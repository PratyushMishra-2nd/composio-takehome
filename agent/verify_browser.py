"""Browser-use verification loop: render the cited pages a plain HTTP fetch could not confirm.

Many docs sites are JS-rendered or bot-protected, so verify.py's plain fetch marks their quotes
"unreadable", "fetch_failed" or "not_found". This step opens each of those URLs in headless Chromium
(Playwright), waits for the page to render, and stores the visible text in results/cache_browser/.
verify.py then re-checks those quotes against the rendered text.

Usage: python agent/verify_browser.py && python agent/verify.py --pass final
       python agent/verify_browser.py --extras && python agent/verify_extras.py
"""
import asyncio, json, re
from pathlib import Path
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parent.parent
BCACHE = ROOT / "results" / "cache_browser"


def key(url):
    return BCACHE / (re.sub(r"[^a-zA-Z0-9]+", "_", url)[:180] + ".txt")


async def render(ctx, sem, url, out):
    async with sem:
        page = await ctx.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            try:
                await page.wait_for_load_state("networkidle", timeout=12000)
            except Exception:
                pass
            await page.wait_for_timeout(1200)
            text = await page.evaluate("document.body ? document.body.innerText : ''")
            key(url).write_text(text, encoding="utf-8")
            out[url] = len(text)
        except Exception as e:
            out[url] = f"error: {type(e).__name__}"
        finally:
            await page.close()


async def main():
    import sys
    if "--extras" in sys.argv:  # enrichment-field evidence
        v = json.loads((ROOT / "results" / "verify_extras.json").read_text(encoding="utf-8"))
        qs = [q for c in v.values() for q in c["quotes"].values()]
    else:
        v = json.loads((ROOT / "results" / "verify_final.json").read_text(encoding="utf-8"))
        qs = [q for c in v.values() for q in c["quotes"]]
    urls = sorted({q["url"] for q in qs if q["status"] != "verified" and q["url"].startswith("http")})
    BCACHE.mkdir(parents=True, exist_ok=True)
    todo = [u for u in urls if not key(u).exists()]
    print(f"{len(urls)} cited URLs not confirmed by plain fetch; rendering {len(todo)} in headless Chromium", flush=True)
    out = {}
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        ctx = await browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36")
        sem = asyncio.Semaphore(6)
        await asyncio.gather(*(render(ctx, sem, u, out) for u in todo))
        await browser.close()
    ok = sum(1 for x in out.values() if isinstance(x, int) and x > 400)
    print(f"rendered {ok}/{len(todo)} with readable text", flush=True)
    (ROOT / "results" / "browser_render_log.json").write_text(json.dumps(out, indent=1), encoding="utf-8")


if __name__ == "__main__":
    asyncio.run(main())
