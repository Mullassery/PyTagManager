/*
 * PyTagManager performance measurement agent (Phase 1.95, docs/VISION.md
 * §16). Injected via Playwright's add_init_script -- like
 * observability/agent.js, it must run before the page's own scripts so
 * PerformanceObserver entries fired during initial load (LCP, paint,
 * long tasks) aren't missed.
 *
 * Deliberately a separate file/namespace (window.__ptm_perf) from
 * observability/agent.js's window.__ptm, not merged into it: performance
 * measurement is architecturally a different concern from tracking
 * observability (VISION.md §16 calls this out explicitly as "the least
 * existing overlap" pillar), and mixing the two would make it harder to
 * later use one without the other.
 *
 * Every metric here comes from the standard Performance Timeline API
 * (PerformanceObserver + performance.getEntriesByType) -- no Lighthouse,
 * no CDP tracing. This is a real trade-off, not a limitation hidden from
 * the reader: it's a subset of what Lighthouse measures (no Speed Index,
 * no lab-simulated CPU/network throttling baked into the metric itself),
 * but every number it does report is a real browser-native measurement,
 * not an approximation.
 */
(function () {
  "use strict";

  if (window.__ptm_perf_installed) return;
  window.__ptm_perf_installed = true;

  var state = {
    lcp: null,
    cls: 0,
    fcp: null,
    longTasks: [],
    interactions: [],
  };

  function safeObserve(type, callback, options) {
    try {
      var observer = new PerformanceObserver(callback);
      observer.observe(Object.assign({ type: type, buffered: true }, options || {}));
      return observer;
    } catch (e) {
      return null; // entry type unsupported in this browser -- degrade silently, not fatally
    }
  }

  safeObserve("largest-contentful-paint", function (list) {
    var entries = list.getEntries();
    if (!entries.length) return;
    var last = entries[entries.length - 1];
    state.lcp = { startTime: last.startTime, size: last.size || 0, url: last.url || null };
  });

  safeObserve("layout-shift", function (list) {
    list.getEntries().forEach(function (entry) {
      if (!entry.hadRecentInput) state.cls += entry.value;
    });
  });

  safeObserve("paint", function (list) {
    list.getEntries().forEach(function (entry) {
      if (entry.name === "first-contentful-paint") state.fcp = entry.startTime;
    });
  });

  safeObserve("longtask", function (list) {
    list.getEntries().forEach(function (entry) {
      state.longTasks.push({
        startTime: entry.startTime,
        duration: entry.duration,
        attribution: (entry.attribution || []).map(function (a) {
          return a.name;
        }),
      });
    });
  });

  // Event Timing API -- the browser-native basis for INP. durationThreshold
  // keeps volume bounded (only interactions slow enough to matter).
  safeObserve(
    "event",
    function (list) {
      list.getEntries().forEach(function (entry) {
        state.interactions.push({ name: entry.name, duration: entry.duration, startTime: entry.startTime });
      });
    },
    { durationThreshold: 16 }
  );

  window.__ptm_perf = {
    getSnapshot: function () {
      var nav = performance.getEntriesByType("navigation")[0] || {};
      var resources = performance.getEntriesByType("resource");
      var tbt = state.longTasks.reduce(function (sum, t) {
        return sum + Math.max(0, t.duration - 50);
      }, 0);
      var inp = state.interactions.reduce(function (max, i) {
        return Math.max(max, i.duration);
      }, 0);
      var transferSize = resources.reduce(function (sum, r) {
        return sum + (r.transferSize || 0);
      }, 0);
      return {
        lcpMs: state.lcp ? state.lcp.startTime : null,
        lcpUrl: state.lcp ? state.lcp.url : null,
        cls: state.cls,
        fcpMs: state.fcp,
        tbtMs: tbt,
        inpMs: state.interactions.length ? inp : null,
        domContentLoadedMs: nav.domContentLoadedEventEnd || null,
        loadEventMs: nav.loadEventEnd || null,
        transferBytes: transferSize + (nav.transferSize || 0),
        requestCount: resources.length,
        longTaskCount: state.longTasks.length,
      };
    },
  };
})();
