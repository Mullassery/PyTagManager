# PyTagManager — Product Vision

## What PyTagManager is

PyTagManager is a **debugging and implementation-intelligence tool for Google
Tag Manager**. It helps a tagging engineer answer one practical question:

> Why is this tag, trigger, variable, event, or destination not behaving the
> way the website and the GTM container say it should?

It does this by combining three evidence sources:

1. **The live website.** MudFish-powered crawling/scraping across an authorized
   domain, including static HTML, loaded JavaScript, rendered DOM, dataLayer,
   network requests, consent state, storage and interaction behavior.
2. **The GTM configuration.** Imported GTM container snapshots (JSON or YAML),
   analyzed as tags, triggers, variables, conditions and references.
3. **Runtime evidence.** Browser-observed events, GTM preview/debug signals,
   analytics requests, console errors and before/after interaction state.

PyTagManager explains the mismatch in plain language, points at the specific
tag/trigger/variable or page-code evidence, and proposes a targeted fix. When
authorized source or container access exists, it can generate a patch or a
reviewable GTM import. It never claims a fix worked until the defined runtime
check passes.

## What it is not

- **Not a replacement for Google Tag Manager.** GTM remains the tag manager;
  PyTagManager inspects, explains, proposes and verifies changes.
- **Not a measurement, CDP or attribution platform.** It is not trying to own
  event collection, customer profiles or marketing reporting. The SDK and
  collection layer exist to test and debug first-party event flow, including
  the same-domain PyTagShield path.
- **Not a generic URL scraper or SEO crawler.** Crawling exists to find and
  understand tagging behavior, not to maximize page counts.
- **Not an automatic production editor.** A public URL does not grant
  permission to modify a site. Proposed changes require explicit approval.
- **Not a source of legal compliance claims.** Consent evidence is technical
  evidence, not a legal opinion.

## The core workflow

```
AUTHORIZED DOMAIN
  -> MudFish discovery: URLs, templates, rendered/static code
  -> GTM snapshot: tags, triggers, variables, references, consent settings
  -> Runtime observation: dataLayer, network, console, storage, interactions
  -> Deterministic diagnosis: what should happen vs. what happened
  -> Evidence-backed finding: cause, impact, confidence, proposed fix
  -> REVIEW / APPLY (source patch or GTM import)
  -> VERIFY in the browser
  -> REPORT resolved / partial / unresolved
```

Every finding distinguishes observation from inference. Severity and confidence
are separate. "Tag not found in HTML" is not the same as "tag did not fire";
"event sent" is not the same as "destination accepted it".

## GTM is the primary configuration model

The first-class objects are GTM's own:

- **Tags** — what is executed, which trigger fires it, what parameters it sends.
- **Triggers** — page, event, click, form, consent and custom conditions.
- **Variables** — dataLayer, URL, DOM, cookie, JavaScript and constant values.
- **References** — `{{Variable}}` use, trigger usage, tag ordering and pauses.

GTM container exports are JSON, and the same document is valid YAML. PyTagManager
accepts both, preserves unknown/unsupported GTM fields in evidence, and
distinguishes "representable in PyTagManager" from "verified equivalent in GTM".
Import is a draft operation; nothing is activated automatically.

## Website code and runtime are the other half of the diagnosis

Static container inspection cannot explain everything. A tag can be correct and
still fail because:

- the dataLayer push never happens;
- the push happens after the trigger;
- the variable reads the wrong path;
- consent blocks the trigger;
- a second direct implementation sends the same event;
- a script is blocked or errors before GTM initializes;
- a SPA route change does not re-evaluate the page trigger.

PyTagManager therefore inspects page and loaded-code content, not just the GTM
snapshot. MudFish provides domain-scale discovery; the browser agent provides
runtime evidence.

## Fixes without replacing GTM

PyTagManager's differentiator is targeted remediation:

- fix a wrong dataLayer path or event name in source;
- correct a trigger condition or a tag parameter;
- remove duplicate direct/GTM instrumentation;
- add missing consent checks;
- correct a variable extraction path;
- export a reviewable GTM container diff/import;
- generate a patch/PR where source access exists;
- verify the result and provide rollback.

Fixes are scoped and evidence-linked. Unrelated refactoring is out of scope.

## Secondary integration tooling

The event contract, Web/iOS/Android SDKs, CDN publication and collection
endpoint are **supporting tools for debugging event flow**, not the product's
measurement offering. They make it possible to:

- test the same event across browser, iOS and Android;
- observe client events and server-side events under one same-domain collection
  path;
- use `event_id` to suppress duplicate delivery before forwarding;
- route eligible events through PyTagShield policy to destinations such as Meta
  and Google;
- inspect sanitized diagnostics at each boundary.

PyTagShield remains optional. It owns server-side policy, minimization,
destination authorization and forwarding. PyTagManager owns tag/code diagnosis,
event schema compatibility, publication metadata and integration diagnostics.
Neither product requires replacing GTM.

## Product principles

1. **Evidence before conclusion.** Findings name the rule, evidence, expected
   behavior, observed behavior and confidence.
2. **Explain GTM in GTM terms.** Never rename away tags, triggers, variables or
   containers in a way that makes the diagnosis unusable to a GTM engineer.
3. **Preserve existing behavior.** The crawler, exporters, diagnostics and
   control plane are extended, not replaced.
4. **Fix narrowly, verify explicitly.** A change is not "resolved" until its
   stated verification passes.
5. **Treat websites and container exports as untrusted.** Isolate execution,
   enforce SSRF/redirect/payload limits, redact secrets and never execute
   arbitrary remote JavaScript in an SDK.
6. **Self-hostable and independently deployable.** No mandatory GTM, PyTagShield
   or vendor account.
7. **No invented compatibility.** GTM and PyTagShield behavior is labeled
   implemented, experimental, unverified or unsupported.

## Success criteria

A developer can:

1. point PyTagManager at an authorized domain and see pages, templates and
   tagging evidence;
2. import the GTM container snapshot and understand its tags, triggers,
   variables and unresolved references;
3. reproduce a missing/duplicate/incorrect event in a real browser;
4. receive a finding that explains the likely cause, impact and confidence;
5. generate a targeted source patch or GTM import without replacing GTM;
6. verify the fix and retain rollback evidence;
7. use the same `event_id` across client and server paths to identify duplicates
   and forward eligible events through PyTagShield policy.

Implement with incremental, testable phases. The current implementation and
verification status is tracked in
[`docs/architecture/multiplatform-extension.md`](architecture/multiplatform-extension.md)
and [`docs/ARCHITECTURE.md`](ARCHITECTURE.md). Do not claim an unexecuted test or
unverified integration passed.
