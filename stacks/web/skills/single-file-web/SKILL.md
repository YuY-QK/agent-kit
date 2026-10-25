---
name: single-file-web
description: Build or change single-file web pages that need no build tools and open directly in a browser — demos, clickable prototypes, small tools. Use it for one-HTML-file pages; don't use it for web apps that need a framework and a build pipeline.
---

# Single-file web pages

Produce a web page that runs completely from one HTML file, looks consistent with its siblings and is easy to move into an app later.

## File conventions

- One HTML file with inline styles and scripts; no npm or build tools — double-click to open in a browser.
- Avoid external resources where possible; web fonts are fine with fallback fonts declared. Any library you must reference uses a CDN URL with a pinned version.
- If the project already has similar pages, read one completely first and reuse its colour variables, fonts, layout and interaction patterns so the pages look like one series.

## Structure

- Write business or algorithm logic as pure functions that never touch the DOM, in a separate `<script id="logic">` — for example “input → list of states for each step”. The UI only renders state and forwards actions, so the logic can be tested on its own and reused in an app.
- Keep state in one object and derive the view from it, instead of storing copies in several DOM nodes.
- In-page storage (localStorage) holds only small things such as preferences; wrap reads and writes in try/catch so the page still works when storage is unavailable.

## Look and usability

- Define colours as CSS variables and support both light and dark themes (following the system, and compatible with a manual toggle if there is one).
- No horizontal scrolling at phone width, with side margins; touch targets are large enough.
- Animations respect `prefers-reduced-motion`; colour is never the only carrier of information.
- UI text uses the language the project specifies; if it doesn't, use the documents language from the global rules.

## Verification

- Extract the pure logic and test it with Node: check every step's state and the final result for typical inputs and many random inputs.
- Check in a browser at light, dark, phone width and desktop width; fix any console errors.
- Report which checks were done and which weren't.
