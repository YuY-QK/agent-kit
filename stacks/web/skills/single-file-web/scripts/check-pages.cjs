#!/usr/bin/env node
// Check web pages without looking at screenshots: opens each page at several widths and
// colour schemes and prints text findings only.
//
// Usage:
//   node check-pages.cjs <url-or-file>... [options]
//
// Options:
//   --views 1100x800:light,375x800:dark   viewports and colour schemes to check (this is the default)
//   --each "<selector>"                    also click every element matching the selector
//                                          (for example tabs) and check the page after each click
//   --min-target 24                        smallest allowed size of a tap target, in CSS pixels
//   --max 10                               findings listed per check before summarising
//
// Checks: console errors and failed requests, horizontal scrolling, elements outside the
// viewport, truncated text, tap targets that are too small, and controls without an
// accessible name. Exits with 1 when anything is found, so it can run in CI.
//
// Needs Playwright: npm install --save-dev playwright && npx playwright install chromium

"use strict";

const path = require("path");
const fs = require("fs");

function loadPlaywright() {
  for (const name of ["playwright", "playwright-core"]) {
    // look in the current project first, then next to this script
    try { return require(require.resolve(name, { paths: [process.cwd()] })); } catch (e) { /* try the next one */ }
    try { return require(name); } catch (e) { /* try the next one */ }
  }
  console.error("Playwright is not installed. Run: npm install --save-dev playwright && npx playwright install chromium");
  process.exit(2);
}

function parseArgs(argv) {
  const opts = { targets: [], views: "1100x800:light,375x800:dark", each: "", minTarget: 24, max: 10 };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === "--views") opts.views = argv[++i];
    else if (a === "--each") opts.each = argv[++i];
    else if (a === "--min-target") opts.minTarget = Number(argv[++i]);
    else if (a === "--max") opts.max = Number(argv[++i]);
    else if (a === "-h" || a === "--help") { printHelp(); process.exit(0); }
    else if (a.startsWith("--")) { console.error("Unknown option: " + a); process.exit(2); }
    else opts.targets.push(a);
  }
  if (!opts.targets.length) { printHelp(); process.exit(2); }
  opts.views = opts.views.split(",").map((v) => {
    const m = /^(\d+)x(\d+)(?::(light|dark))?$/.exec(v.trim());
    if (!m) { console.error("Bad --views entry: " + v); process.exit(2); }
    return { width: +m[1], height: +m[2], scheme: m[3] || "light" };
  });
  return opts;
}

function printHelp() {
  const text = fs.readFileSync(__filename, "utf8").split("\n");
  const end = text.findIndex((l, i) => i > 0 && !l.startsWith("//"));
  console.log(text.slice(1, end).map((l) => l.replace(/^\/\/ ?/, "")).join("\n"));
}

function toUrl(target) {
  if (/^[a-z]+:\/\//i.test(target)) return target;
  const file = path.resolve(target);
  if (!fs.existsSync(file)) { console.error("Not found: " + target); process.exit(2); }
  return "file://" + file;
}

// Runs inside the page. Returns findings grouped by check.
function inspect(minTarget) {
  const vw = window.innerWidth;
  const out = { scroll: [], offscreen: [], truncated: [], small: [], unnamed: [] };

  function describe(el) {
    let s = el.tagName.toLowerCase();
    if (el.id) s += "#" + el.id;
    const cls = typeof el.className === "string" ? el.className.trim().split(/\s+/).filter(Boolean).slice(0, 2) : [];
    if (cls.length) s += "." + cls.join(".");
    const text = (el.innerText || el.getAttribute("aria-label") || el.value || "").trim().replace(/\s+/g, " ");
    if (text) s += ' "' + (text.length > 40 ? text.slice(0, 40) + "…" : text) + '"';
    return s;
  }
  function visible(el) {
    const cs = getComputedStyle(el);
    if (cs.display === "none" || cs.visibility === "hidden" || +cs.opacity === 0) return false;
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  }
  // inside a horizontally scrollable container, overflow is intended
  function inScroller(el) {
    for (let p = el.parentElement; p && p !== document.body; p = p.parentElement) {
      const ox = getComputedStyle(p).overflowX;
      if (ox === "auto" || ox === "scroll" || ox === "hidden" || ox === "clip") return true;
    }
    return false;
  }
  function accessibleName(el) {
    const label = el.getAttribute("aria-label") || el.getAttribute("title");
    if (label && label.trim()) return label.trim();
    const by = el.getAttribute("aria-labelledby");
    if (by) {
      const t = by.split(/\s+/).map((id) => (document.getElementById(id) || {}).textContent || "").join(" ").trim();
      if (t) return t;
    }
    if (el.tagName === "INPUT" || el.tagName === "SELECT" || el.tagName === "TEXTAREA") {
      if (["button", "submit", "reset"].includes(el.type) && el.value) return el.value;
      if (el.id) { const l = document.querySelector('label[for="' + CSS.escape(el.id) + '"]'); if (l && l.textContent.trim()) return l.textContent.trim(); }
      const wrap = el.closest("label"); if (wrap && wrap.textContent.trim()) return wrap.textContent.trim();
      if (el.placeholder) return el.placeholder;
      return "";
    }
    const text = (el.innerText || el.textContent || "").trim();
    if (text) return text;
    const img = el.querySelector("img[alt], svg[aria-label], [aria-label]");
    if (img) return img.getAttribute("alt") || img.getAttribute("aria-label") || "";
    return "";
  }

  const doc = document.documentElement;
  if (doc.scrollWidth > vw + 1) out.scroll.push("page is " + doc.scrollWidth + "px wide in a " + vw + "px viewport");

  const all = Array.from(document.body.querySelectorAll("*"));
  for (const el of all) {
    if (!visible(el)) continue;
    const cs = getComputedStyle(el);
    const r = el.getBoundingClientRect();
    if ((r.right > vw + 1 || r.left < -1) && cs.position !== "fixed" && !inScroller(el)) {
      // report only the outermost overflowing element
      const parent = el.parentElement;
      const pr = parent ? parent.getBoundingClientRect() : null;
      if (!pr || (pr.right <= vw + 1 && pr.left >= -1)) out.offscreen.push(describe(el) + " spans " + Math.round(r.left) + "–" + Math.round(r.right) + "px");
    }
    const clips = cs.overflowX !== "visible" || cs.overflowY !== "visible" || cs.textOverflow === "ellipsis" || cs.webkitLineClamp !== "none";
    const scrollable = ["auto", "scroll"].includes(cs.overflowX) || ["auto", "scroll"].includes(cs.overflowY);
    if (clips && !scrollable && (el.innerText || "").trim() && el.children.length === 0) {
      if (el.scrollWidth > el.clientWidth + 1 || el.scrollHeight > el.clientHeight + 1) out.truncated.push(describe(el));
    }
  }

  const controls = document.querySelectorAll('a[href], button, input:not([type="hidden"]), select, textarea, summary, [role="button"], [role="link"], [role="tab"], [onclick], [tabindex]:not([tabindex="-1"])');
  for (const el of controls) {
    if (!visible(el)) continue;
    const r = el.getBoundingClientRect();
    // links inside running text are exempt from the size rule
    const inlineLink = el.tagName === "A" && getComputedStyle(el).display === "inline" && el.parentElement &&
      (el.parentElement.textContent || "").trim().length > (el.textContent || "").trim().length + 10;
    if (!inlineLink && (r.width < minTarget || r.height < minTarget)) out.small.push(describe(el) + " is " + Math.round(r.width) + "×" + Math.round(r.height) + "px");
    if (!accessibleName(el)) out.unnamed.push(describe(el));
  }
  return out;
}

const LABELS = {
  console: "console errors / failed requests",
  scroll: "horizontal scrolling",
  offscreen: "elements outside the viewport",
  truncated: "truncated text",
  small: "tap targets smaller than the minimum",
  unnamed: "controls without an accessible name",
};

async function checkState(page, opts, errors) {
  const found = await page.evaluate(inspect, opts.minTarget);
  found.console = errors.splice(0);
  return found;
}

function report(found, opts) {
  let count = 0;
  const lines = [];
  for (const key of Object.keys(LABELS)) {
    const list = Array.from(new Set(found[key] || []));
    if (!list.length) continue;
    count += list.length;
    lines.push("  ✗ " + LABELS[key] + " (" + list.length + ")");
    list.slice(0, opts.max).forEach((x) => lines.push("      " + x));
    if (list.length > opts.max) lines.push("      … and " + (list.length - opts.max) + " more");
  }
  return { count, lines };
}

(async () => {
  const opts = parseArgs(process.argv.slice(2));
  const { chromium } = loadPlaywright();
  const browser = await chromium.launch();
  let total = 0;
  try {
    for (const target of opts.targets) {
      const url = toUrl(target);
      for (const view of opts.views) {
        const context = await browser.newContext({ viewport: { width: view.width, height: view.height }, colorScheme: view.scheme });
        const page = await context.newPage();
        const errors = [];
        page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
        page.on("pageerror", (e) => errors.push(String(e.message || e)));
        page.on("requestfailed", (r) => errors.push("request failed: " + r.url() + " (" + ((r.failure() || {}).errorText || "") + ")"));
        await page.goto(url, { waitUntil: "load" });
        await page.waitForLoadState("networkidle", { timeout: 5000 }).catch(() => {});
        await page.waitForTimeout(300);

        const states = [{ name: "", found: await checkState(page, opts, errors) }];
        if (opts.each) {
          const n = await page.locator(opts.each).count();
          for (let i = 0; i < n; i++) {
            const item = page.locator(opts.each).nth(i);
            const name = ((await item.innerText().catch(() => "")) || "#" + (i + 1)).trim().replace(/\s+/g, " ").slice(0, 30);
            await item.click().catch((e) => errors.push("could not click " + opts.each + " #" + (i + 1) + ": " + e.message.split("\n")[0]));
            await page.waitForTimeout(300);
            states.push({ name: name, found: await checkState(page, opts, errors) });
          }
        }
        // after a click, report only what wasn't already found on the initial page
        const seen = {};
        for (const key of Object.keys(LABELS)) seen[key] = new Set(states[0].found[key] || []);
        for (const st of states) {
          if (st.name) for (const key of Object.keys(LABELS)) st.found[key] = (st.found[key] || []).filter((x) => !seen[key].has(x));
          const head = target + " @ " + view.width + "px " + view.scheme + (st.name ? " · new after clicking “" + st.name + "”" : "");
          const r = report(st.found, opts);
          total += r.count;
          console.log((r.count ? "✗ " : "✓ ") + head + (r.count ? "" : ": no problems found"));
          r.lines.forEach((l) => console.log(l));
        }
        await context.close();
      }
    }
  } finally {
    await browser.close();
  }
  console.log(total ? "\n" + total + " problem(s) found." : "\nAll checks passed.");
  process.exit(total ? 1 : 0);
})();
