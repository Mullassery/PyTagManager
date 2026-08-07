# PyTagManager Architecture & Roadmap

PyTagManager's long-term vision is an AI-native analytics implementation
platform, described in full in Appendix A (web-focused) and Appendix B
(universal cross-platform) below. **v1 implements a small, real vertical
slice of that vision** — everything else is roadmap, not vaporware claimed
as done.

## What v1 actually implements

| Capability | Status | Where |
|---|---|---|
| Website crawling (link/sitemap/robots.txt discovery, BFS, dedup) | **Implemented** | `src/crawler/` (Rust) |
| Semantic DOM graph (static HTML structure, selectors, ARIA) | **Implemented** | `src/dom/` (Rust) |
| Selector resilience (data-testid / data-* / aria-label / id priority) | **Implemented** | `src/dom/selectors.rs` |
| Rule-based tracking recommendations (keyword-driven, deterministic) | **Implemented** | `python/pytagmanager/recommend/heuristics.py` |
| GTM JSON export | **Implemented** | `python/pytagmanager/export/gtm.py` |
| CLI (`pytagmanager crawl ...`) | **Implemented** | `python/pytagmanager/cli.py` |
| AI business intent classification (LLM-backed, e.g. Claude) | Interface stub only, not implemented | `python/pytagmanager/intent/base.py` |
| Visual understanding (screenshots, computer vision) | Not started | — |
| Runtime behavior capture (real browser, clicks/hovers/network) | Not started | — |
| XDM-native event modeling (Adobe) | Not started | — |
| Enterprise audit engine (GTM/Adobe/Tealium/Segment/Snowplow import + gap analysis) | Not started | — |
| Version control / change detection across crawls | Not started | — |
| Non-GTM exporters (Adobe Tags, GA4, Segment, Snowplow, Tealium, RudderStack) | Not started | — |
| Any non-web platform (Android, iOS, kiosk, desktop, IoT, AR/VR, wearables, voice) | Not started | — |

Notably: v1's DOM graph is built from **static HTML only**. Fields the
original spec calls for that require a real browser renderer — bounding
box, z-index, visibility state, scroll position, shadow DOM, iframe
context — are not derivable from a static parse and are out of scope until
a Python-side Playwright layer (Phase 3/4 in Appendix A) hands rendered
HTML back through `parse_html()`, which is already designed to accept it.

v1's "AI explainability" is a rule-based stand-in: every recommendation
carries a `rationale` string naming exactly which signals fired (text,
class, id, aria-label). This gives the same *shape* of output the AI
intent classifier will eventually produce, so swapping in a real
classifier later doesn't require changing callers — see
`pytagmanager.intent.base.IntentClassifier`.

## Extension points for future work

- **New exporter**: implement the `Exporter` protocol in
  `python/pytagmanager/export/base.py`, following the pattern in `gtm.py`.
- **AI intent classification**: implement `IntentClassifier` in
  `python/pytagmanager/intent/base.py` (a `ClaudeIntentClassifier` stub
  already exists, targeting the Anthropic API per the project's stated
  provider preference — it currently raises `NotImplementedError`).
- **Browser rendering / runtime behavior**: a Python layer using Playwright
  can call `pytagmanager._core.parse_html(rendered_html, url)` directly to
  get a semantic graph from rendered (not just static) HTML, and layer
  runtime observation (clicks, network calls, data layer pushes) on top.
- **Other platforms** (mobile/kiosk/desktop/etc.): entirely new discovery
  engines, out of scope for the Rust/Python web core built here.

---

## Appendix A: original web-focused spec (10 phases)

AI-Powered Intelligent Web Tracking Discovery & Tag Generation Platform

### Objective

Build an enterprise-grade AI-powered platform that automatically discovers, classifies, documents, audits, and exports website tracking implementations for modern analytics platforms.

The platform should eliminate the need for marketers or analysts to manually inspect the DOM, identify CSS selectors, write JavaScript triggers, or configure hundreds of tracking rules manually.

Instead of asking a user what should be tracked, the platform should intelligently discover everything that is meaningful on a website and generate production-ready tracking specifications.

The system should be designed to support websites ranging from a few pages to enterprise websites containing hundreds of thousands of pages.

### Core Philosophy

Traditional Tag Managers work like this: Developer builds website → Analyst opens browser → Inspects DOM → Finds CSS Selector → Creates Trigger → Creates Variables → Creates Tags → Publishes.

The proposed system inverts this: Website → AI discovers website → AI understands user intent → AI understands business purpose → AI recommends tracking → User reviews → One-click export.

The human becomes the reviewer rather than the implementer.

### High-Level Architecture

Website → Intelligent Crawler → (DOM Analysis Engine + JavaScript Runtime Engine) → Visual Understanding Engine → AI Intent Classification Engine → Tracking Recommendation Engine → (GTM / Adobe Tags / Segment / Snowplow Export)

### Phase 1 — Intelligent Website Discovery

The crawler should automatically discover every accessible page by combining multiple strategies: internal link crawling, XML sitemap parsing, robots.txt awareness, canonical URL handling, dynamic route discovery, SPA route detection, navigation menu traversal, footer link discovery, search-driven discovery, pagination traversal, faceted navigation handling, infinite scrolling support, authenticated session crawling (when credentials are provided), multi-language site discovery, mobile and desktop rendering, API-discovered routes (where applicable).

Each page should be assigned a unique identifier and revisited incrementally to detect changes over time.

### Phase 2 — Intelligent DOM Understanding

Rather than storing raw HTML, build a semantic graph representation of the page. Each node should include: HTML element type, parent-child relationships, XPath, CSS selector, stable selector candidates, visible text, hidden text, ARIA labels, ARIA roles, accessibility metadata, CSS classes, IDs, custom attributes, data attributes, inline styles, bounding box coordinates, z-index, visibility state, scroll position, shadow DOM relationships, iframe context, dynamic rendering state.

The graph should support semantic queries such as "Find every visible call-to-action button inside the Hero section" rather than merely "Find every `<button>` element."

### Phase 3 — Visual Understanding

Render every page in a real browser and capture full-page, above-the-fold, mobile, tablet, and desktop screenshots. Apply computer vision and multimodal AI to understand hero banners, navigation bars, product grids, pricing tables, promotional banners, popups, sticky elements, modals, carousels, accordions, search interfaces, forms, checkout flows, embedded media, cookie banners, live chat widgets. Correlate visual understanding with DOM structure to identify the true importance of page elements.

### Phase 4 — Runtime Behavior Analysis

Launch the website in a real browser (e.g., Chromium) and observe behavior during simulated user interactions: clicks, hover, keyboard navigation, scrolling, form completion, dropdown selection, search, product selection, filter/sort, checkout simulation, modal interactions, tab navigation, carousel interaction, video playback, file downloads.

Capture: JS event listeners, DOM mutations, network/AJAX/fetch/GraphQL/Beacon requests, existing data layer pushes, cookie creation, local/session storage usage, SPA route transitions, analytics library invocations.

### Phase 5 — AI Business Intent Detection

Infer the business purpose of every interactive element rather than merely identifying its HTML type. Examples: Primary/Secondary CTA, Product Purchase, Add to Cart, Checkout, Wishlist, Search, Newsletter Signup, Contact Form, Quote Request, Book Demo, Trial Signup, Login/Logout, Account Creation, Support Chat, Download PDF, Video Engagement, Product Comparison, Pricing Interaction, Social Sharing, Review Submission, Appointment Booking, Event Registration, Payment, Subscription, Feedback Collection.

Each recommendation should include a confidence score and rationale.

### Phase 6 — Tracking Recommendation Engine

For every identified interaction, generate: event name, trigger type, recommended selector, selector fallback hierarchy, event category, business objective, recommended parameters, custom dimensions, conversion flag, engagement flag, funnel stage, suggested audience impacts, confidence score. Selectors should prioritize resilience, favoring data-* attributes and ARIA labels over brittle positional selectors.

### Phase 7 — AI-Powered Data Layer Recommendations

Recommend a standardized data layer for every interaction (e.g. a `purchase` event with product_id, sku, category, quantity, price, currency, coupon, promotion, campaign, user_type, membership, inventory_status). Map discovered information to business concepts and highlight missing data developers should expose.

### Phase 8 — XDM-Native Event Modeling

Generate Adobe Experience Platform XDM-compatible schemas and mappings: eventType, commerce events, web events, product list items, experience events, identity fields, marketing campaign fields, commerce/product/cart objects, payment details, device information, page metadata. Where data is unavailable, identify required developer additions.

### Phase 9 — Enterprise Audit Engine

Import existing configurations from GTM, Adobe Experience Platform Tags (Launch), Tealium, Segment, Snowplow. Compare discovered interactions against implemented tracking to identify missing events, duplicates, broken selectors, obsolete rules, redundant variables, unused triggers, incorrect mappings, inconsistent naming, coverage gaps, dead tags, events firing multiple times, events never firing. Generate a gap analysis with remediation recommendations.

### Phase 10 — Version Control and Change Detection

Track website evolution over time by comparing crawls: new/removed pages, changed layouts, selector changes, added/removed CTAs, new forms, updated navigation, broken tracking, new JS behaviors. Provide version history and change reports for continuous monitoring.

### Export Formats

GTM (JSON, YAML), Adobe Experience Platform Tags (Launch), Adobe XDM mappings, Adobe Customer Journey Analytics event definitions, GA4 event configurations, Segment Tracking Plans, Snowplow schemas, Tealium iQ profiles, RudderStack, CSV, Excel, Markdown implementation guides, JSON APIs.

### AI Explainability

Every recommendation should answer: Why was this element selected? What business objective does it support? How confident is the AI? Which signals contributed? What alternatives were considered? What data is missing? What are the potential implementation risks?

### Long-Term Vision

An AI-native Analytics Implementation Assistant — "GitHub Copilot for Digital Analytics" — combining web crawling, browser automation, semantic DOM analysis, visual AI, runtime observation, business intent inference, standards-aware event modeling (including XDM), implementation auditing, and multi-platform export, dramatically reducing implementation effort and enabling continuous governance across enterprise-scale digital properties.

---

## Appendix B: universal cross-platform spec

AI-Powered Universal Digital Tracking Discovery & Analytics Platform

### Vision

An enterprise-grade, AI-native analytics implementation platform that automatically discovers, understands, recommends, audits, and generates analytics implementations across every major digital platform — Websites, PWAs, SPAs, Android, iOS, Tablet, Smart TV, Digital Kiosks, POS Systems, Desktop (Windows/macOS/Linux), Embedded IoT Interfaces, Automotive Infotainment, Mixed Reality (AR/VR), Wearables, Voice Interfaces.

The objective is to eliminate manual analytics implementation across all customer touchpoints by allowing AI to discover user journeys, business intent, and meaningful interactions automatically.

### Core Philosophy

Traditional analytics implementations require platform-specific expertise (Website → inspect DOM → write GTM tags; Android → instrument Firebase SDK; iOS → instrument Adobe SDK; Kiosk → custom SDK; Desktop → manual event logging). Instead: Application → AI explores → AI understands workflows → AI understands business intent → AI recommends tracking → Review → One-click export. The platform acts as an autonomous analytics architect.

### Universal Architecture

Digital Experience → (Website/PWA, Mobile Apps, Desktop Apps) → Universal Discovery Engine → (Visual AI, Runtime Analysis, Accessibility Engine) → Business Intent Classification Engine → Analytics Recommendation Engine → (GTM, Adobe Tags, Firebase, Custom SDK, ...).

### Android Discovery Engine

**Static analysis**: Activities, Fragments, Jetpack Compose screens, Navigation Graphs, XML Layouts, resources, view IDs, strings, drawables, Kotlin/Java code, SDK integrations, permissions, intent filters, accessibility labels, Material Design components — building a complete application graph.

**Runtime exploration**: automatically interact with buttons, cards, RecyclerViews, lists, bottom sheets, dialogs, FABs, search, nav drawer, bottom nav, tabs, date pickers, camera, QR scanner, maps, auth, payment, checkout, push notifications, deep links, offline mode. Capture view/fragment/activity transitions, navigation events, network calls, SDK events, local DB changes, SharedPreferences, secure storage, analytics SDK calls.

### iOS Discovery Engine

Support UIKit, SwiftUI, Storyboards, XIBs, Navigation/Tab Controllers, Collection/Table Views, custom views. Analyze view controllers, navigation hierarchy, accessibility identifiers, Swift/Obj-C source, storyboards, Auto Layout, resource bundles, localization. Runtime exploration: swipe, long press, pinch, zoom, scroll, context menus, Face ID, Touch ID, Apple Pay, camera, notifications, share sheets, Siri shortcuts.

### Mobile AI Journey Discovery

Rather than tracking screens individually, discover entire customer journeys (e.g. Home → Search → Product → Checkout → Payment → Success), identifying entry/exit points, conversion funnels, dead ends, rage taps, drop-off screens, frequently repeated actions, navigation loops.

### Gesture Intelligence

Track swipe left/right, pinch, rotate, double tap, long press, multi-touch, zoom, drag, pull-to-refresh; AI determines which gestures represent meaningful business events.

### Kiosk Discovery Engine

Understand large touch screens, touch-only interaction, idle mode, attract loops, auto reset, accessibility mode, session timeout, multi-language switching, barcode/QR scanning, NFC, card readers, printers, cameras, signature pads. Discover flows like Idle → Welcome → Language → Browse → Search → Select Product → Customize → Payment → Receipt → Exit → Reset. Monitor hardware: touch display, barcode scanner, RFID, NFC, receipt printer, camera, microphone, speaker, payment terminal, coin acceptor, cash drawer, weight sensors, thermal printer.

### Accessibility Intelligence

Across every platform, inspect VoiceOver, TalkBack, Switch Control, screen readers, keyboard navigation, high contrast, dynamic font sizes, focus order, semantic labels. Recommend analytics around accessibility usage where appropriate, respecting privacy.

### Business Intent Classification

Classify interactions into business concepts regardless of platform: Product Discovery, Lead Generation, Authentication, Purchase, Cart Management, Appointment Booking, Check-in, Boarding Pass, QR/Barcode Scan, Membership Enrollment, Loyalty Redemption, Donation, Survey Completion, Customer Support, Account Recovery, Feedback, Ticket Purchase, Wayfinding, Content Consumption, Media Playback, Search, Subscription, Kiosk Assistance, Queue Management. Each with confidence score and reasoning.

### Analytics Recommendation Engine

Generate consistent canonical event definitions independent of platform (e.g. `purchase_completed` with order_id, products, revenue, currency, payment_method, customer_type, platform), then map to platform-specific outputs:

- **Web**: GTM Containers, Adobe Tags Rules, Tealium, Segment, Snowplow
- **Android**: Kotlin analytics wrappers, Java SDK integration, Firebase Analytics, Adobe Experience Platform Mobile SDK, Amplitude, Mixpanel, Segment, RudderStack
- **iOS**: Swift analytics wrappers, Obj-C integration, Firebase Analytics, Adobe Experience Platform Mobile SDK, Mixpanel, Segment, Amplitude
- **Kiosk**: Embedded SDK integrations, offline event queues, local storage sync, edge analytics, batch upload configs, session reset logic

### AI Audit Engine

Import existing implementations and compare against discovered behavior to detect missing events, duplicate instrumentation, broken mappings, inconsistent naming, over/under-instrumentation, screens without analytics, untracked buttons, ignored gesture events, funnel gaps, checkout issues, SDK configuration problems, platform inconsistencies.

### Cross-Platform Event Governance

Maintain a canonical event model across all digital touchpoints — the same business event (e.g. `purchase_completed`) originating from web, Android, iOS, or a kiosk should map to a shared event definition and schema while generating platform-specific instrumentation automatically, enabling consistent reporting, customer journey analysis, audience building, and attribution across GA4, Adobe Experience Platform, Adobe Customer Journey Analytics, Firebase, Amplitude, Mixpanel, Segment, and Snowplow.

### Long-Term Vision

The universal AI implementation layer for digital analytics — autonomously discovering user experiences, understanding business intent, generating analytics specifications, auditing existing implementations, and maintaining governance across web, mobile, kiosk, desktop, IoT, and emerging interfaces. An intelligent orchestration and implementation assistant, not a replacement for existing analytics platforms — "GitHub Copilot for Digital Analytics Engineering."
