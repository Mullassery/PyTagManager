"use strict";

const assert = require("node:assert/strict");
const crypto = require("node:crypto");
const fs = require("node:fs");
const http = require("node:http");
const path = require("node:path");
const test = require("node:test");

const sdk = require("../src/pytagmanager.js");

const ROOT = path.resolve(__dirname, "../../..");
const FIXTURES = path.join(ROOT, "schemas/events/v1/fixtures");

function readJson(file) {
  return JSON.parse(fs.readFileSync(file, "utf8"));
}

function memoryStorage() {
  const values = new Map();
  return {
    getItem(key) {
      return values.has(key) ? values.get(key) : null;
    },
    setItem(key, value) {
      values.set(key, String(value));
    },
    removeItem(key) {
      values.delete(key);
    },
  };
}

function digest(value) {
  return crypto.createHash("sha256").update(value).digest("hex");
}

function seal(config) {
  const unsigned = {};
  Object.keys(config).forEach((key) => {
    if (key !== "integrity") unsigned[key] = config[key];
  });
  config.integrity = {
    algorithm: "sha256",
    digest: digest(sdk.canonicalize(unsigned)),
  };
  return config;
}

function baseConfig(overrides) {
  return Object.assign(
    {
      schema_version: "1.0",
      kind: "pytagmanager.container",
      container_id: "GTM-TEST123",
      config_version: "11111111-2222-4333-8444-555555555555",
      revision_number: 3,
      environment: { name: "Production", protected: false },
      published_at: "2026-10-20T12:00:00.000Z",
      event_schema_version: "1.0",
      events: [
        {
          name: "page_view",
          purposes: ["analytics"],
          tag_ids: [],
        },
        {
          name: "add_to_cart",
          purposes: ["analytics"],
          tag_ids: [],
        },
      ],
      tags: [],
      destinations: [],
      features: {
        client_side_execution: false,
        event_collection: true,
        server_side_forwarding: true,
      },
      compatibility: {
        event_contract: "1.0",
        min_sdk: { web: "0.1.0", android: "0.1.0", ios: "0.1.0" },
      },
      cache: { max_age_seconds: 31536000, immutable: true },
      consent_defaults: { analytics: false },
    },
    overrides || {}
  );
}

function startServer(handler) {
  return new Promise((resolve) => {
    const requests = [];
    const server = http.createServer((request, response) => {
      let body = "";
      request.on("data", (chunk) => {
        body += chunk;
      });
      request.on("end", () => {
        requests.push({ method: request.method, url: request.url, headers: request.headers, body });
        handler(request, response, body, requests.length);
      });
    });
    server.listen(0, "127.0.0.1", () => {
      const { port } = server.address();
      resolve({
        url: `http://127.0.0.1:${port}`,
        requests,
        close: () => new Promise((done) => server.close(done)),
      });
    });
  });
}

function wait(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function clientOptions(server, extra) {
  return Object.assign(
    {
      containerId: "GTM-TEST123",
      endpoint: `${server.url}/api/v1/events`,
      configUrl: `${server.url}/config.json`,
      allowInsecure: true,
      storage: memoryStorage(),
      consent: { analytics: true },
      batchSize: 10,
      flushIntervalMs: 60000,
      maxRetries: 1,
      retryBaseMs: 100,
    },
    extra || {}
  );
}

test("shared valid fixtures validate in the Web SDK", () => {
  for (const name of fs.readdirSync(path.join(FIXTURES, "valid"))) {
    const document = readJson(path.join(FIXTURES, "valid", name));
    assert.deepEqual(sdk.validateEvent(document, { now: "2026-10-20T12:05:00.000Z", maxSkewSeconds: 3600 }), [], name);
  }
});

test("shared invalid fixtures are rejected in the Web SDK", () => {
  for (const name of fs.readdirSync(path.join(FIXTURES, "invalid"))) {
    const document = readJson(path.join(FIXTURES, "invalid", name));
    assert.ok(sdk.validateEvent(document, { maxSkewSeconds: null }).length > 0, name);
  }
  assert.equal(sdk.isSensitiveProperty("user_email"), true);
  assert.equal(sdk.isSensitiveProperty("email_sha256"), false);
});

test("loads config, tracks a page view, and flushes a batch", async () => {
  const config = seal(baseConfig());
  const server = await startServer((request, response) => {
    if (request.url === "/config.json") {
      response.writeHead(200, { "Content-Type": "application/json" });
      response.end(JSON.stringify(config));
      return;
    }
    response.writeHead(202, { "Content-Type": "application/json" });
    response.end(JSON.stringify({ status: "accepted" }));
  });
  const client = sdk.init(clientOptions(server));
  await client.ready;
  assert.equal(client.config.config_version, config.config_version);
  const eventId = client.pageView({ page_path: "/pricing" });
  assert.match(eventId, /^[0-9a-f-]{36}$/);
  const result = await client.flush();
  assert.equal(result.sent, 1);
  const delivery = server.requests.find((item) => item.url === "/api/v1/events");
  const payload = JSON.parse(delivery.body);
  assert.equal(payload.schema_version, "1.0");
  assert.equal(payload.events[0].event_name, "page_view");
  assert.equal(payload.events[0].container_id, "GTM-TEST123");
  assert.equal(payload.events[0].consent.purposes.analytics, true);
  assert.equal(payload.events[0].config_version, config.config_version);
  client.close();
  await server.close();
});

test("denied consent blocks collection before a network call", async () => {
  const config = seal(baseConfig());
  const server = await startServer((request, response) => {
    if (request.url === "/config.json") {
      response.writeHead(200, { "Content-Type": "application/json" });
      response.end(JSON.stringify(config));
      return;
    }
    response.writeHead(202);
    response.end("{}");
  });
  const client = sdk.init(clientOptions(server, { consent: { analytics: false } }));
  await client.ready;
  assert.equal(client.track("add_to_cart", { value: 10 }), null);
  assert.equal(client.flush.bind(client) instanceof Function, true);
  assert.equal((await client.flush()).sent, 0);
  assert.equal(client.getDiagnostics().blockedConsent, 1);
  assert.equal(server.requests.filter((item) => item.url === "/api/v1/events").length, 0);
  client.close();
  await server.close();
});

test("sensitive and malformed properties are rejected", async () => {
  const config = seal(baseConfig());
  const server = await startServer((request, response) => {
    if (request.url === "/config.json") {
      response.writeHead(200, { "Content-Type": "application/json" });
      response.end(JSON.stringify(config));
      return;
    }
    response.writeHead(202);
    response.end("{}");
  });
  const client = sdk.init(clientOptions(server));
  await client.ready;
  assert.equal(client.track("add_to_cart", { user_email: "a@b.c" }), null);
  assert.equal(client.track("Bad Event", { value: 1 }), null);
  assert.equal(client.getDiagnostics().lastError, "invalid_event");
  client.close();
  await server.close();
});

test("event ids deduplicate within a client session", async () => {
  const config = seal(baseConfig());
  const server = await startServer((request, response) => {
    if (request.url === "/config.json") {
      response.writeHead(200, { "Content-Type": "application/json" });
      response.end(JSON.stringify(config));
      return;
    }
    response.writeHead(202);
    response.end("{}");
  });
  const client = sdk.init(clientOptions(server));
  await client.ready;
  const id = "22222222-3333-4444-8555-666666666666";
  assert.equal(client.track("add_to_cart", { value: 1 }, { eventId: id }), id);
  assert.equal(client.track("add_to_cart", { value: 2 }, { eventId: id }), null);
  assert.equal(client.getDiagnostics().duplicates, 1);
  client.close();
  await server.close();
});

test("retries a transient failure and then delivers", async () => {
  const config = seal(baseConfig());
  let failures = 1;
  const server = await startServer((request, response) => {
    if (request.url === "/config.json") {
      response.writeHead(200, { "Content-Type": "application/json" });
      response.end(JSON.stringify(config));
      return;
    }
    if (failures > 0) {
      failures -= 1;
      response.writeHead(503);
      response.end("{}");
      return;
    }
    response.writeHead(202);
    response.end("{}");
  });
  const client = sdk.init(clientOptions(server));
  await client.ready;
  client.track("add_to_cart", { value: 1 });
  const first = await client.flush();
  assert.equal(first.sent, 0);
  assert.ok(first.retry_in_ms >= 100);
  await wait(400);
  assert.ok(client.getDiagnostics().delivered >= 1 || client.getDiagnostics().sent >= 1);
  client.close();
  await server.close();
});

test("fetches a mutable environment pointer and verifies the immutable config", async () => {
  const config = seal(baseConfig());
  const server = await startServer((request, response) => {
    if (request.url === "/latest.json") {
      response.writeHead(200, { "Content-Type": "application/json" });
      response.end(
        JSON.stringify({
          schema_version: "1.0",
          kind: "pytagmanager.environment",
          container_id: "GTM-TEST123",
          config_version: config.config_version,
          config_url: "/revisions/config.json",
        })
      );
      return;
    }
    if (request.url === "/revisions/config.json") {
      response.writeHead(200, { "Content-Type": "application/json" });
      response.end(JSON.stringify(config));
      return;
    }
    response.writeHead(404);
    response.end();
  });
  const client = sdk.init(
    clientOptions(server, { configUrl: `${server.url}/latest.json` })
  );
  await client.ready;
  assert.equal(client.config.config_version, config.config_version);
  assert.equal(client.configError, null);
  client.close();
  await server.close();
});

test("tampered configuration is rejected and cached fallback remains bounded", async () => {
  const config = seal(baseConfig());
  config.events[0].name = "tampered";
  const server = await startServer((request, response) => {
    if (request.url === "/config.json") {
      response.writeHead(200, { "Content-Type": "application/json" });
      response.end(JSON.stringify(config));
      return;
    }
    response.writeHead(202);
    response.end("{}");
  });
  const client = sdk.init(clientOptions(server));
  await client.ready;
  assert.equal(client.config, null);
  assert.match(client.configError, /integrity/);
  assert.equal(client.track("page_view", {}), null);
  client.close();
  await server.close();
});

test("SPA route changes produce page views without duplicate paths", async () => {
  const config = seal(baseConfig());
  const server = await startServer((request, response) => {
    if (request.url === "/config.json") {
      response.writeHead(200, { "Content-Type": "application/json" });
      response.end(JSON.stringify(config));
      return;
    }
    response.writeHead(202);
    response.end("{}");
  });
  const listeners = {};
  global.window = {
    addEventListener(name, handler) {
      listeners[name] = handler;
    },
    removeEventListener(name) {
      delete listeners[name];
    },
  };
  global.document = { title: "Test", referrer: "", visibilityState: "visible", addEventListener() {}, removeEventListener() {} };
  global.location = { pathname: "/a", href: "http://localhost/a" };
  let currentPath = "/a";
  global.history = {
    pushState(_state, _title, next) {
      currentPath = next;
      global.location.pathname = next;
    },
    replaceState(_state, _title, next) {
      currentPath = next;
      global.location.pathname = next;
    },
  };
  const client = sdk.init(clientOptions(server, { consent: { analytics: true } }));
  await client.ready;
  client.startAutoPageViews();
  assert.equal(client.queue.length, 1);
  global.history.pushState({}, "", "/b");
  assert.equal(client.queue.length, 2);
  global.history.pushState({}, "", "/b");
  assert.equal(client.queue.length, 2);
  client.close();
  await server.close();
  delete global.window;
  delete global.document;
  delete global.location;
  delete global.history;
});

test("debugSnapshot is safe and exposes configuration provenance", async () => {
  const config = seal(baseConfig());
  const server = await startServer((request, response) => {
    response.writeHead(200, { "Content-Type": "application/json" });
    response.end(JSON.stringify(config));
  });
  const client = sdk.init(clientOptions(server));
  await client.ready;
  client.track("add_to_cart", { value: 19.99, currency: "USD" });
  const snapshot = client.debugSnapshot();
  assert.equal(snapshot.config_source, "network");
  assert.equal(snapshot.config_version, config.config_version);
  assert.equal(snapshot.queued, 1);
  assert.deepEqual(snapshot.consent, { analytics: true });
  assert.equal(snapshot.diagnostics.queued, 1);
  assert.equal(JSON.stringify(snapshot).includes("19.99"), false);
  assert.equal(JSON.stringify(snapshot).includes("USD"), false);
  client.close();
  await server.close();
});
