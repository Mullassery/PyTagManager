// Deliberately blocks the main thread for >100ms when it executes --
// used by perf_isolate.html to give isolation experiments (item 4) a
// real, deterministic TBT signal to detect the absence of.
(function () {
  var start = Date.now();
  while (Date.now() - start < 150) {
    // busy-wait
  }
})();
