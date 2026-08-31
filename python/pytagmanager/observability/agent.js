/*
 * PyTagManager browser-side observability agent.
 *
 * Injected via Playwright's add_init_script (session.py) so it runs before
 * any page script -- critical for the dataLayer wrap below to see every
 * push, including the site's own GTM snippet's first ones.
 *
 * This agent OBSERVES. It never sends analytics of its own and never writes
 * to the site's real dataLayer beyond wrapping .push() to see what's already
 * being pushed (the original push behavior is always preserved and called).
 * The same wrap-not-replace discipline applies to fetch/XHR/console.error
 * below -- every wrapped function still calls through to the original and
 * returns/throws exactly what it would have unwrapped.
 * All telemetry goes out through one channel, window.__ptm_emit (a Python
 * callback bound via page.expose_function before this script runs), as
 * structured events -- never raw page content, form values, or credentials.
 */
(function () {
  "use strict";

  if (window.__ptm_installed) return;
  window.__ptm_installed = true;

  var MUTATION_DEBOUNCE_MS = 150;
  var INTERESTING_TAGS = { button: 1, a: 1, form: 1, input: 1, select: 1, textarea: 1 };

  function safeEmit(type, name, payload, selector) {
    try {
      if (typeof window.__ptm_emit !== "function") return;
      window.__ptm_emit({
        type: type,
        name: name || "",
        payload: payload || {},
        selector: selector || null,
        page_url: location.href,
        ts: Date.now() / 1000,
      });
    } catch (e) {
      // Never let a telemetry failure break the page being observed.
    }
  }

  // ---- Stable-selector generation (mirrors the Rust DOM graph's priority:
  // data-testid / other data-* / aria-label / id, falling back to a
  // positional CSS path) so runtime elements can be matched against
  // recommend_for_graph()'s statically-generated selectors. ----
  function describeSelector(el) {
    if (!el || !el.getAttribute) return null;
    var testId = el.getAttribute("data-testid");
    if (testId) return '[data-testid="' + testId + '"]';
    var attrs = el.attributes || [];
    for (var i = 0; i < attrs.length; i++) {
      if (attrs[i].name.indexOf("data-") === 0 && attrs[i].value) {
        return "[" + attrs[i].name + '="' + attrs[i].value + '"]';
      }
    }
    var ariaLabel = el.getAttribute("aria-label");
    if (ariaLabel) return '[aria-label="' + ariaLabel + '"]';
    if (el.id) return "#" + el.id;
    return cssPath(el);
  }

  function cssPath(el) {
    var parts = [];
    var node = el;
    var depth = 0;
    while (node && node.nodeType === 1 && depth < 6) {
      var part = node.tagName.toLowerCase();
      var parent = node.parentElement;
      if (parent) {
        var siblings = Array.prototype.filter.call(parent.children, function (c) {
          return c.tagName === node.tagName;
        });
        if (siblings.length > 1) {
          part += ":nth-of-type(" + (siblings.indexOf(node) + 1) + ")";
        }
      }
      parts.unshift(part);
      node = parent;
      depth++;
    }
    return parts.join(" > ");
  }

  // ---- User interaction observation (click / submit / change) ----
  ["click", "submit", "change"].forEach(function (type) {
    document.addEventListener(
      type,
      function (e) {
        var el = e.target;
        if (!el || !el.tagName) return;
        safeEmit(type, "", { tag: el.tagName.toLowerCase() }, describeSelector(el));
      },
      true
    );
  });

  // ---- JavaScript error observation ----
  window.addEventListener("error", function (e) {
    safeEmit("js_error", "", {
      message: e.message || "",
      filename: e.filename || "",
      lineno: e.lineno || 0,
    });
  });

  window.addEventListener("unhandledrejection", function (e) {
    var reason = e.reason;
    safeEmit("js_error", "unhandled_rejection", {
      message: (reason && (reason.message || String(reason))) || "",
    });
  });

  // console.error is a distinct signal from window.onerror: a caught
  // exception logged via console.error() never reaches window.onerror,
  // but often marks exactly the kind of "app swallowed an error and moved
  // on silently" failure that correlates with missing tracking events.
  if (window.console && typeof console.error === "function") {
    var originalConsoleError = console.error.bind(console);
    console.error = function () {
      try {
        var message = Array.prototype.slice
          .call(arguments)
          .map(function (a) {
            return typeof a === "string" ? a : (a && a.message) || String(a);
          })
          .join(" ");
        safeEmit("js_error", "console", { message: message.slice(0, 500) });
      } catch (e) {}
      return originalConsoleError.apply(console, arguments);
    };
  }

  // ---- SPA navigation observation ----
  function wrapHistoryMethod(name) {
    var original = history[name];
    history[name] = function () {
      var result = original.apply(history, arguments);
      safeEmit("route_change", name.toLowerCase(), { url: location.href });
      return result;
    };
  }
  wrapHistoryMethod("pushState");
  wrapHistoryMethod("replaceState");
  window.addEventListener("popstate", function () {
    safeEmit("route_change", "popstate", { url: location.href });
  });

  // ---- Application API observation (fetch/XHR) ----
  // Distinct from the GA4/GTM network sniffing done on the Python side
  // (session.py watches outgoing requests at the browser-network layer for
  // known analytics endpoints); this observes application-level API calls
  // so diagnostics can correlate "an app API call succeeded" with "did a
  // tracking event follow" -- e.g. a /cart API succeeding with no
  // corresponding add_to_cart dataLayer event. Analytics endpoints
  // themselves are excluded here to avoid double-observing the same
  // request from two layers.
  function isAnalyticsUrl(url) {
    return /google-analytics\.com|googletagmanager\.com|analytics\.google\.com/.test(url || "");
  }

  if (window.fetch) {
    var originalFetch = window.fetch.bind(window);
    window.fetch = function (input, init) {
      var url = typeof input === "string" ? input : (input && input.url) || "";
      var method = (init && init.method) || (input && input.method) || "GET";
      var startedAt = Date.now();
      var promise = originalFetch(input, init);
      if (!isAnalyticsUrl(url)) {
        // Observe via a side-channel .then()/.catch() rather than
        // returning a chained promise -- the caller's promise identity,
        // timing, and resolution value must be completely unaffected.
        promise.then(
          function (response) {
            safeEmit("api_call", "", {
              url: url,
              method: method,
              status: response.status,
              ok: response.ok,
              duration_ms: Date.now() - startedAt,
            });
          },
          function (error) {
            safeEmit("api_call", "", {
              url: url,
              method: method,
              error: String((error && error.message) || error),
              duration_ms: Date.now() - startedAt,
            });
          }
        );
      }
      return promise;
    };
  }

  if (window.XMLHttpRequest) {
    var originalOpen = XMLHttpRequest.prototype.open;
    var originalSend = XMLHttpRequest.prototype.send;
    XMLHttpRequest.prototype.open = function (method, url) {
      this.__ptm_method = method;
      this.__ptm_url = url;
      return originalOpen.apply(this, arguments);
    };
    XMLHttpRequest.prototype.send = function () {
      var xhr = this;
      var startedAt = Date.now();
      if (!isAnalyticsUrl(xhr.__ptm_url || "")) {
        xhr.addEventListener("loadend", function () {
          safeEmit("api_call", "", {
            url: xhr.__ptm_url || "",
            method: xhr.__ptm_method || "GET",
            status: xhr.status,
            duration_ms: Date.now() - startedAt,
          });
        });
      }
      return originalSend.apply(this, arguments);
    };
  }

  // ---- dataLayer observation (wrap, never replace) ----
  function normalizeDataLayerItem(item) {
    if (item && typeof item === "object") {
      if (typeof item.event === "string") {
        if (item.event.indexOf("gtm.") === 0) {
          return { kind: "gtm_event", name: item.event, payload: item };
        }
        return { kind: "datalayer_push", name: item.event, payload: item };
      }
      // gtag()-style pushes are array-like `arguments` objects:
      // gtag('event', name, params) / gtag('consent', 'default'|'update', params)
      if (typeof item.length === "number" && typeof item[0] === "string") {
        var arr = Array.prototype.slice.call(item);
        if (arr[0] === "consent") {
          return { kind: "consent_change", name: arr[1] || "", payload: arr[2] || {} };
        }
        if (arr[0] === "event") {
          return { kind: "datalayer_push", name: arr[1] || "", payload: arr[2] || {} };
        }
        return { kind: "gtm_event", name: String(arr[0]), payload: { args: arr.slice(1) } };
      }
    }
    return null;
  }

  function wrapDataLayer() {
    window.dataLayer = window.dataLayer || [];
    var dl = window.dataLayer;
    var originalPush = dl.push.bind(dl);
    dl.push = function () {
      var args = Array.prototype.slice.call(arguments);
      for (var i = 0; i < args.length; i++) {
        var normalized = normalizeDataLayerItem(args[i]);
        if (normalized) {
          safeEmit(normalized.kind, normalized.name, normalized.payload, null);
        }
      }
      return originalPush.apply(dl, args);
    };
  }
  wrapDataLayer();

  // ---- Consent state read (common CMP dataLayer shape; best-effort only) ----
  // Actual consent events are captured above via normalizeDataLayerItem when
  // gtag('consent', ...) or a dataLayer.push({event: 'consent...'}) fires.
  // No independent CMP API integration -- CMPs vary too widely to hard-code.

  // ---- MutationObserver: targeted, controllable, deduped, debounced ----
  var mutationObserver = null;
  var pendingMutations = [];
  var flushTimer = null;
  var seenMutationKeys = {};
  var visibilityObserver = null;
  var seenVisibleSelectors = {};

  function isInteresting(node) {
    return !!(node && node.tagName && INTERESTING_TAGS[node.tagName.toLowerCase()]);
  }

  function mutationKey(kind, node) {
    return kind + ":" + (describeSelector(node) || "");
  }

  function flushMutations() {
    flushTimer = null;
    var batch = pendingMutations;
    pendingMutations = [];
    batch.forEach(function (m) {
      safeEmit(m.type, "", { tag: m.tag }, m.selector);
    });
  }

  function queueMutation(kind, node) {
    if (!isInteresting(node)) return;
    var key = mutationKey(kind, node);
    if (seenMutationKeys[key]) return;
    seenMutationKeys[key] = true;
    pendingMutations.push({
      type: kind === "add" ? "dom_insert" : "dom_remove",
      tag: node.tagName.toLowerCase(),
      selector: describeSelector(node),
    });
    if (flushTimer) clearTimeout(flushTimer);
    flushTimer = setTimeout(flushMutations, MUTATION_DEBOUNCE_MS);
  }

  window.__ptm = {
    // selectors: array of CSS selectors to scope observation to (default:
    // document.body, still filtered to INTERESTING_TAGS to bound volume).
    // watchAttributes: only set true when attribute changes matter -- off
    // by default per the "don't observe the entire DOM indefinitely
    // without controls" requirement.
    startMutationObserver: function (selectors, watchAttributes) {
      this.stopMutationObserver();
      var targets = [];
      (selectors && selectors.length ? selectors : ["body"]).forEach(function (sel) {
        try {
          document.querySelectorAll(sel).forEach(function (t) {
            targets.push(t);
          });
        } catch (e) {}
      });
      if (targets.length === 0) targets = [document.body];

      seenMutationKeys = {};
      mutationObserver = new MutationObserver(function (mutations) {
        mutations.forEach(function (m) {
          if (m.type === "childList") {
            m.addedNodes.forEach(function (n) {
              queueMutation("add", n);
            });
            m.removedNodes.forEach(function (n) {
              queueMutation("remove", n);
            });
          }
        });
      });
      targets.forEach(function (target) {
        mutationObserver.observe(target, {
          childList: true,
          subtree: true,
          attributes: !!watchAttributes,
        });
      });
    },
    stopMutationObserver: function () {
      if (mutationObserver) {
        mutationObserver.disconnect();
        mutationObserver = null;
      }
      if (flushTimer) {
        clearTimeout(flushTimer);
        flushTimer = null;
      }
      pendingMutations = [];
    },

    // Opt-in impression/viewability tracking: only watches the selectors
    // it's given (never the whole page), and only emits once per element
    // per session -- mirrors the MutationObserver's start/stop/dedup
    // control surface.
    startVisibilityObserver: function (selectors, threshold) {
      this.stopVisibilityObserver();
      if (typeof IntersectionObserver === "undefined" || !selectors || !selectors.length) return;
      seenVisibleSelectors = {};
      visibilityObserver = new IntersectionObserver(
        function (entries) {
          entries.forEach(function (entry) {
            if (!entry.isIntersecting) return;
            var selector = describeSelector(entry.target);
            var key = selector || "";
            if (seenVisibleSelectors[key]) return;
            seenVisibleSelectors[key] = true;
            safeEmit(
              "visibility",
              "visible",
              { tag: entry.target.tagName ? entry.target.tagName.toLowerCase() : "" },
              selector
            );
          });
        },
        { threshold: typeof threshold === "number" ? threshold : 0.5 }
      );
      selectors.forEach(function (sel) {
        try {
          document.querySelectorAll(sel).forEach(function (el) {
            visibilityObserver.observe(el);
          });
        } catch (e) {}
      });
    },
    stopVisibilityObserver: function () {
      if (visibilityObserver) {
        visibilityObserver.disconnect();
        visibilityObserver = null;
      }
      seenVisibleSelectors = {};
    },
  };
})();
