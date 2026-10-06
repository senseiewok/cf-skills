# Measuring layout shift instead of guessing

Cumulative Layout Shift (CLS) is the Core Web Vital that small static sites most often fail, and the two usual causes are visible in a build: fonts that swap after first paint (text reflows) and content injected after load (a banner, a counter, a late image without dimensions). Do not guess which one you have: observe it.

## 1. A short Playwright script

Python shown; the Node binding has the same calls. Run it against your own site only, one page at a time, and respect your own `robots.txt`. Only Chromium reports `layout-shift` entries.

```python
"""Observe layout shifts on one page under a slow CPU and network. Usage: python observe_shift.py https://your-site.example/"""
import sys
from playwright.sync_api import sync_playwright

OBSERVE = """
window.__shifts = [];
new PerformanceObserver(list => {
  for (const e of list.getEntries()) {
    if (e.hadRecentInput) continue;                       // shifts right after a tap or key are excluded by the metric
    window.__shifts.push({
      value: e.value, t: Math.round(e.startTime),
      sources: (e.sources || []).map(s => s.node && s.node.outerHTML ? s.node.outerHTML.slice(0, 100) : String(s.node)),
    });
  }
}).observe({type: 'layout-shift', buffered: true});
"""

url = sys.argv[1]
with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 390, "height": 844})          # a phone; most shift happens here
    cdp = page.context.new_cdp_session(page)
    cdp.send("Emulation.setCPUThrottlingRate", {"rate": 4})                  # a slow phone CPU
    cdp.send("Network.enable")
    cdp.send("Network.emulateNetworkConditions", {                           # roughly "slow 4G"
        "offline": False, "latency": 150,
        "downloadThroughput": 1_600_000 / 8, "uploadThroughput": 750_000 / 8})
    page.add_init_script(OBSERVE)                                            # installed before any page script runs
    page.goto(url, wait_until="networkidle")
    page.wait_for_timeout(3000)                                              # let late content and font swaps happen
    shifts = page.evaluate("window.__shifts")
    browser.close()

total = sum(s["value"] for s in shifts)
print(f"OBSERVED {len(shifts)} layout shifts, summed value {total:.3f}, on {url} at 390x844, CPU x4, slow 4G")
for s in shifts:
    print(f"  t={s['t']}ms value={s['value']:.3f} sources={s['sources']}")
```

## 2. Reading the output

- `sources` names the elements that moved. A text block moving at the moment a font arrives is a font swap; a block moving when a banner or counter appears is late-injected content; an image moving is a missing `width`/`height`.
- The summed value is an **upper bound** on CLS, not CLS itself: the metric groups shifts into session windows (at most five seconds, gaps under one second) and reports the largest window. For a short static page the two usually coincide; say "summed layout shift" unless you computed the windows.
- Run three times. A single run under throttling is noisy; report the range, not one number.
- Record route, viewport, throttling, the commit or build you tested, and the date. Keep the raw output local; publish only the observation.

## 3. Fixes, in the order they usually pay off

1. `width` and `height` on every `<img>` (the checker's SEO034).
2. `<link rel="preload" as="font" type="font/woff2" crossorigin>` for the one font the first paint needs, with `font-display: swap` or `optional` in `@font-face`, and a fallback font sized to match (`size-adjust`, `ascent-override`) so the swap moves nothing (SEO038).
3. Reserve space for anything that appears after load: a banner gets its height in CSS whether or not it is shown; a counter gets a minimum width.
4. `<link rel="modulepreload">` for the module that renders above the fold (SEO037).
5. Then measure again. A fix you did not re-measure is a hypothesis.

## 4. What this does not measure

Largest Contentful Paint and Interaction to Next Paint need their own observers (`largest-contentful-paint`, `event`), and field data from real visitors differs from any lab run. Say which you measured.
