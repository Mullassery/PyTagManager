/* PyTagManager Web SDK v0.1.0
 * Declarative event collection only. It does not execute remote JavaScript or
 * send events directly to vendor destinations. A server/PyTagShield boundary
 * validates and forwards eligible events.
 */
(function (root, factory) {
  if (typeof module === "object" && module.exports) {
    module.exports = factory();
  } else {
    root.PyTagManager = factory();
  }
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  var VERSION = "0.1.0";
  var SDK_NAME = "pytagmanager-web";
  var SCHEMA_VERSION = "1.0";
  var MAX_EVENT_BYTES = 32768;
  var MAX_PROPERTIES = 100;
  var MAX_PROPERTY_DEPTH = 5;
  var MAX_PROPERTY_STRING = 2048;
  var MAX_ARRAY_ITEMS = 100;
  var MAX_OBJECT_KEYS = 50;
  var MAX_CONSENT_PURPOSES = 32;
  var MAX_QUEUE = 100;
  var MAX_SEEN_IDS = 1000;
  var PLATFORMS = { web: true, android: true, ios: true, server: true };
  var CONSENT_SOURCES = { sdk: true, host: true, server: true, unknown: true };
  var CONSENT_PROVENANCE = {
    explicit: true,
    default: true,
    stored: true,
    unknown: true,
  };
  var EVENT_NAME_RE = /^[A-Za-z][A-Za-z0-9_.-]{0,79}$/;
  var PROPERTY_KEY_RE = /^[A-Za-z][A-Za-z0-9_.-]{0,63}$/;
  var PURPOSE_RE = /^[a-z][a-z0-9_-]{0,63}$/;
  var EVENT_ID_RE =
    /^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$/;
  var CONTAINER_RE = /^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$/;
  var CONFIG_VERSION_RE = /^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$/;
  var SDK_VERSION_RE = /^[0-9]+\.[0-9]+\.[0-9]+(?:[-+][A-Za-z0-9.-]+)?$/;
  var APP_VERSION_RE = /^[A-Za-z0-9][A-Za-z0-9_.+-]{0,63}$/;
  var TIMESTAMP_RE =
    /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,3}))?Z$/;
  var SAFE_ID_RE = /^[^\u0000-\u001f\u007f]+$/;
  var CONTROL_RE = /[\u0000-\u001f\u007f]/;
  var HASH_MARKERS = { hash: true, hashed: true, sha256: true, sha512: true, hmac: true, digest: true };
  var SENSITIVE_TOKENS = {
    password: true,
    passwd: true,
    passphrase: true,
    secret: true,
    token: true,
    apikey: true,
    credential: true,
    credentials: true,
    cvv: true,
    cvc: true,
    pin: true,
    ssn: true,
    socialsecurity: true,
    email: true,
    phone: true,
    phonenumber: true,
    address: true,
    street: true,
    postalcode: true,
    zip: true,
    iban: true,
    accountnumber: true,
    routingnumber: true,
    taxid: true,
    nationalid: true,
    passport: true,
    dob: true,
    birthdate: true,
    ip: true,
    ipaddress: true,
    latitude: true,
    longitude: true,
    geolocation: true,
    cardnumber: true,
    creditcard: true,
    creditcardnumber: true,
    securitycode: true,
    routing: true,
  };
  var SENSITIVE_PHRASES = {
    creditcard: true,
    creditcardnumber: true,
    cardnumber: true,
    securitycode: true,
    socialsecurity: true,
    socialsecuritynumber: true,
    phonenumber: true,
    postalcode: true,
    ipaddress: true,
    dateofbirth: true,
    bankaccount: true,
    accountnumber: true,
    routingnumber: true,
    nationalid: true,
    taxid: true,
    passportnumber: true,
  };

  function EventValidationError(issues) {
    this.name = "EventValidationError";
    this.issues = issues || [];
    this.message = this.issues
      .map(function (issue) {
        return issue.field + ": " + issue.message;
      })
      .join("; ") || "invalid event";
    if (Error.captureStackTrace) Error.captureStackTrace(this, EventValidationError);
  }
  EventValidationError.prototype = Object.create(Error.prototype);
  EventValidationError.prototype.constructor = EventValidationError;

  function isPlainObject(value) {
    return (
      value !== null &&
      typeof value === "object" &&
      !Array.isArray(value) &&
      Object.prototype.toString.call(value) === "[object Object]"
    );
  }

  function utf8Length(value) {
    if (typeof TextEncoder !== "undefined") {
      return new TextEncoder().encode(value).length;
    }
    return unescape(encodeURIComponent(value)).length;
  }

  function canonicalize(value) {
    if (value === null || typeof value !== "object") return JSON.stringify(value);
    if (Array.isArray(value)) {
      return "[" + value.map(canonicalize).join(",") + "]";
    }
    return (
      "{" +
      Object.keys(value)
        .sort()
        .map(function (key) {
          return JSON.stringify(key) + ":" + canonicalize(value[key]);
        })
        .join(",") +
      "}"
    );
  }

  function hasControl(value, allowWhitespace) {
    for (var i = 0; i < value.length; i += 1) {
      var code = value.charCodeAt(i);
      if (allowWhitespace && (code === 9 || code === 10 || code === 13)) continue;
      if (code < 32 || code === 127) return true;
    }
    return false;
  }

  function isSensitiveProperty(key) {
    var tokens = String(key).toLowerCase().match(/[a-z0-9]+/g) || [];
    if (!tokens.length) return false;
    var normalized = tokens.join("");
    var hashed = HASH_MARKERS[tokens[0]] || HASH_MARKERS[tokens[tokens.length - 1]];
    var phrase = false;
    Object.keys(SENSITIVE_PHRASES).some(function (candidate) {
      if (normalized.indexOf(candidate) !== -1) {
        phrase = true;
        return true;
      }
      return false;
    });
    if (phrase) return !hashed;
    var sensitive = tokens.some(function (token) {
      return SENSITIVE_TOKENS[token];
    });
    return sensitive && !hashed;
  }

  function parseTimestamp(value) {
    if (typeof value !== "string" || !TIMESTAMP_RE.test(value)) return null;
    var time = Date.parse(value);
    return isNaN(time) ? null : new Date(time);
  }

  function formatTimestamp(value) {
    return new Date(value).toISOString();
  }

  function nowIso() {
    return new Date().toISOString();
  }

  function randomId() {
    var cryptoObject = typeof globalThis !== "undefined" ? globalThis.crypto : null;
    if (cryptoObject && typeof cryptoObject.randomUUID === "function") {
      return cryptoObject.randomUUID();
    }
    var bytes = new Uint8Array(16);
    if (cryptoObject && typeof cryptoObject.getRandomValues === "function") {
      cryptoObject.getRandomValues(bytes);
    } else {
      for (var i = 0; i < bytes.length; i += 1) bytes[i] = Math.floor(Math.random() * 256);
    }
    bytes[6] = (bytes[6] & 0x0f) | 0x40;
    bytes[8] = (bytes[8] & 0x3f) | 0x80;
    var hex = Array.prototype.map
      .call(bytes, function (byte) {
        return byte.toString(16).padStart(2, "0");
      })
      .join("");
    return (
      hex.slice(0, 8) +
      "-" +
      hex.slice(8, 12) +
      "-" +
      hex.slice(12, 16) +
      "-" +
      hex.slice(16, 20) +
      "-" +
      hex.slice(20)
    );
  }

  function issue(code, field, message) {
    return { code: code, field: field, message: message };
  }

  function checkString(value, field, issues, pattern, maxLength, allowWhitespace, required) {
    if (value === undefined || value === null) {
      if (required !== false) issues.push(issue("invalid_type", field, "must be a string"));
      return false;
    }
    if (typeof value !== "string") {
      issues.push(issue("invalid_type", field, "must be a string"));
      return false;
    }
    if (required !== false && !value) {
      issues.push(issue("required", field, "must not be empty"));
      return false;
    }
    if (value.length > maxLength) {
      issues.push(issue("too_long", field, "must be at most " + maxLength + " characters"));
      return false;
    }
    if (hasControl(value, allowWhitespace !== false)) {
      issues.push(issue("invalid_characters", field, "must not contain control characters"));
      return false;
    }
    if (pattern && !pattern.test(value)) {
      issues.push(issue("invalid_format", field, "has an invalid format"));
      return false;
    }
    return true;
  }

  function validatePropertyValue(value, field, issues, depth, seenDepth) {
    if (seenDepth > MAX_PROPERTY_DEPTH) {
      issues.push(issue("too_deep", field, "must not exceed " + MAX_PROPERTY_DEPTH + " nested levels"));
      return;
    }
    if (value === null || typeof value === "boolean") return;
    if (typeof value === "string") {
      if (value.length > MAX_PROPERTY_STRING) {
        issues.push(issue("too_long", field, "string values must be at most " + MAX_PROPERTY_STRING + " characters"));
      }
      if (hasControl(value, true)) {
        issues.push(issue("invalid_characters", field, "must not contain control characters"));
      }
      return;
    }
    if (typeof value === "number") {
      if (!isFinite(value)) issues.push(issue("invalid_type", field, "must be a finite number"));
      return;
    }
    if (Array.isArray(value)) {
      if (value.length > MAX_ARRAY_ITEMS) {
        issues.push(issue("too_many_items", field, "must have at most " + MAX_ARRAY_ITEMS + " items"));
      }
      value.forEach(function (item, index) {
        validatePropertyValue(item, field + "[" + index + "]", issues, depth, seenDepth + 1);
      });
      return;
    }
    if (isPlainObject(value)) {
      var keys = Object.keys(value);
      if (keys.length > MAX_OBJECT_KEYS) {
        issues.push(issue("too_many_keys", field, "must have at most " + MAX_OBJECT_KEYS + " keys"));
      }
      keys.forEach(function (key) {
        var child = field ? field + "." + key : key;
        if (!PROPERTY_KEY_RE.test(key)) {
          issues.push(issue("invalid_key", child, "property keys must match ^[A-Za-z][A-Za-z0-9_.-]{0,63}$"));
        } else if (isSensitiveProperty(key)) {
          issues.push(issue("sensitive_property", child, "sensitive property names are prohibited by the v1 contract"));
        }
        validatePropertyValue(value[key], child, issues, depth, seenDepth + 1);
      });
      return;
    }
    issues.push(issue("invalid_type", field, "must be a JSON string, number, boolean, null, array, or object"));
  }

  function validateEvent(raw, options) {
    options = options || {};
    var issues = [];
    if (!isPlainObject(raw)) return [issue("invalid_type", "$", "event must be a JSON object")];
    var serialized;
    try {
      serialized = canonicalize(raw);
      if (utf8Length(serialized) > (options.maxBytes || MAX_EVENT_BYTES)) {
        issues.push(issue("too_large", "$", "event must be at most " + (options.maxBytes || MAX_EVENT_BYTES) + " bytes"));
      }
    } catch (error) {
      issues.push(issue("invalid_json", "$", "event must be JSON-serializable"));
    }
    var allowed = {
      schema_version: true,
      event_id: true,
      event_name: true,
      timestamp: true,
      source: true,
      container_id: true,
      config_version: true,
      subject: true,
      consent: true,
      correlation: true,
      properties: true,
    };
    Object.keys(raw).forEach(function (key) {
      if (!allowed[key]) issues.push(issue("unknown_field", "$", "contains unknown field: " + key));
    });
    ["schema_version", "event_id", "event_name", "timestamp", "source", "container_id", "properties"].forEach(function (key) {
      if (!(key in raw)) issues.push(issue("required", key, "is required"));
    });
    if ("schema_version" in raw && raw.schema_version !== SCHEMA_VERSION) {
      issues.push(issue("unsupported_schema", "schema_version", "must be '1.0'"));
    }
    if ("event_id" in raw) checkString(raw.event_id, "event_id", issues, EVENT_ID_RE, 36, false);
    if ("event_name" in raw) checkString(raw.event_name, "event_name", issues, EVENT_NAME_RE, 80, false);
    if ("timestamp" in raw) {
      var parsed = parseTimestamp(raw.timestamp);
      if (!parsed) {
        issues.push(issue("invalid_timestamp", "timestamp", "must be an RFC 3339 UTC timestamp ending in Z"));
      } else if (options.maxSkewSeconds !== null && options.maxSkewSeconds !== undefined) {
        var now = options.now ? new Date(options.now) : new Date();
        if (Math.abs(now.getTime() - parsed.getTime()) > options.maxSkewSeconds * 1000) {
          issues.push(issue("timestamp_skew", "timestamp", "is outside the allowed clock-skew window"));
        }
      }
    }
    if ("source" in raw) {
      var source = raw.source;
      if (!isPlainObject(source)) {
        issues.push(issue("invalid_type", "source", "must be an object"));
      } else {
        var sourceAllowed = { platform: true, sdk_name: true, sdk_version: true, app_version: true };
        Object.keys(source).forEach(function (key) {
          if (!sourceAllowed[key]) issues.push(issue("unknown_field", "source", "contains unknown field: " + key));
        });
        ["platform", "sdk_name", "sdk_version"].forEach(function (key) {
          if (!(key in source)) issues.push(issue("required", "source." + key, "is required"));
        });
        if (!PLATFORMS[source.platform]) {
          issues.push(issue("invalid_platform", "source.platform", "must be web, android, ios, or server"));
        }
        checkString(source.sdk_name, "source.sdk_name", issues, /^[A-Za-z][A-Za-z0-9_.-]{0,63}$/, 64, false);
        checkString(source.sdk_version, "source.sdk_version", issues, SDK_VERSION_RE, 32, false);
        if ("app_version" in source) checkString(source.app_version, "source.app_version", issues, APP_VERSION_RE, 64, false);
      }
    }
    if ("container_id" in raw) checkString(raw.container_id, "container_id", issues, CONTAINER_RE, 128, false);
    if ("config_version" in raw && raw.config_version !== null) {
      checkString(raw.config_version, "config_version", issues, CONFIG_VERSION_RE, 128, false);
    }
    if ("subject" in raw && raw.subject !== null) {
      if (!isPlainObject(raw.subject)) {
        issues.push(issue("invalid_type", "subject", "must be an object"));
      } else {
        Object.keys(raw.subject).forEach(function (key) {
          if (key !== "id" && key !== "type") issues.push(issue("unknown_field", "subject", "contains unknown field: " + key));
        });
        if (!("id" in raw.subject)) issues.push(issue("required", "subject.id", "is required"));
        if (!("type" in raw.subject)) issues.push(issue("required", "subject.type", "is required"));
        checkString(raw.subject.id, "subject.id", issues, SAFE_ID_RE, 128, true);
        if (raw.subject.type !== "user" && raw.subject.type !== "anonymous") {
          issues.push(issue("invalid_subject_type", "subject.type", "must be 'user' or 'anonymous'"));
        }
      }
    }
    if ("consent" in raw && raw.consent !== null) {
      var consent = raw.consent;
      if (!isPlainObject(consent)) {
        issues.push(issue("invalid_type", "consent", "must be an object"));
      } else {
        Object.keys(consent).forEach(function (key) {
          if (!{ purposes: 1, source: 1, provenance: 1, updated_at: 1 }[key]) {
            issues.push(issue("unknown_field", "consent", "contains unknown field: " + key));
          }
        });
        ["purposes", "source", "provenance"].forEach(function (key) {
          if (!(key in consent)) issues.push(issue("required", "consent." + key, "is required"));
        });
        if (!isPlainObject(consent.purposes) || !Object.keys(consent.purposes || {}).length) {
          issues.push(issue("invalid_consent", "consent.purposes", "must be a non-empty object mapping purposes to booleans"));
        } else {
          var purposeKeys = Object.keys(consent.purposes);
          if (purposeKeys.length > MAX_CONSENT_PURPOSES) {
            issues.push(issue("too_many_purposes", "consent.purposes", "must have at most " + MAX_CONSENT_PURPOSES + " purposes"));
          }
          purposeKeys.forEach(function (purpose) {
            if (!PURPOSE_RE.test(purpose)) {
              issues.push(issue("invalid_purpose", "consent.purposes." + purpose, "has an invalid format"));
            }
            if (typeof consent.purposes[purpose] !== "boolean") {
              issues.push(issue("invalid_consent", "consent.purposes." + purpose, "must be true or false"));
            }
          });
        }
        if (!CONSENT_SOURCES[consent.source]) {
          issues.push(issue("invalid_consent_source", "consent.source", "has an invalid value"));
        }
        if (!CONSENT_PROVENANCE[consent.provenance]) {
          issues.push(issue("invalid_consent_provenance", "consent.provenance", "has an invalid value"));
        }
        if (consent.updated_at !== undefined && consent.updated_at !== null && !parseTimestamp(consent.updated_at)) {
          issues.push(issue("invalid_timestamp", "consent.updated_at", "must be an RFC 3339 UTC timestamp ending in Z"));
        }
      }
    }
    if ("correlation" in raw && raw.correlation !== null) {
      if (!isPlainObject(raw.correlation)) {
        issues.push(issue("invalid_type", "correlation", "must be an object"));
      } else {
        Object.keys(raw.correlation).forEach(function (key) {
          if (key !== "correlation_id" && key !== "session_id") {
            issues.push(issue("unknown_field", "correlation", "contains unknown field: " + key));
          }
        });
        ["correlation_id", "session_id"].forEach(function (key) {
          if (key in raw.correlation) checkString(raw.correlation[key], "correlation." + key, issues, null, 128, true);
        });
      }
    }
    if ("properties" in raw) {
      if (!isPlainObject(raw.properties)) {
        issues.push(issue("invalid_type", "properties", "must be an object"));
      } else {
        var propertyKeys = Object.keys(raw.properties);
        if (propertyKeys.length > MAX_PROPERTIES) {
          issues.push(issue("too_many_properties", "properties", "must have at most " + MAX_PROPERTIES + " keys"));
        }
        propertyKeys.forEach(function (key) {
          var child = "properties." + key;
          if (!PROPERTY_KEY_RE.test(key)) {
            issues.push(issue("invalid_key", child, "property keys must match ^[A-Za-z][A-Za-z0-9_.-]{0,63}$"));
          } else if (isSensitiveProperty(key)) {
            issues.push(issue("sensitive_property", child, "sensitive property names are prohibited by the v1 contract"));
          }
          validatePropertyValue(raw.properties[key], child, issues, 0, 0);
        });
      }
    }
    return issues;
  }

  function normalizeConsent(consent, defaultSource, defaultProvenance) {
    var purposes = {};
    Object.keys(consent || {}).forEach(function (key) {
      purposes[key] = consent[key] === true;
    });
    return {
      purposes: purposes,
      source: defaultSource || "sdk",
      provenance: defaultProvenance || "default",
      updated_at: nowIso(),
    };
  }

  function buildEvent(options) {
    options = options || {};
    var event = {
      schema_version: SCHEMA_VERSION,
      event_id: options.eventId || randomId(),
      event_name: options.eventName,
      timestamp: formatTimestamp(options.timestamp || new Date()),
      source: {
        platform: options.platform || "web",
        sdk_name: options.sdkName || SDK_NAME,
        sdk_version: options.sdkVersion || VERSION,
      },
      container_id: options.containerId,
      properties: options.properties || {},
    };
    if (options.appVersion) event.source.app_version = options.appVersion;
    if (options.configVersion) event.config_version = options.configVersion;
    if (options.subject) event.subject = options.subject;
    if (options.consent) {
      event.consent = normalizeConsent(options.consent, options.consentSource, options.consentProvenance);
      if (options.consentUpdatedAt) event.consent.updated_at = options.consentUpdatedAt;
    }
    if (options.correlation) event.correlation = options.correlation;
    var issues = validateEvent(event, { maxSkewSeconds: null });
    if (issues.length) throw new EventValidationError(issues);
    return event;
  }

  function isLoopbackHost(hostname) {
    return (
      hostname === "localhost" ||
      hostname === "127.0.0.1" ||
      hostname === "::1" ||
      hostname === "[::1]"
    );
  }

  function validateEndpoint(value, allowInsecure) {
    var parsed;
    try {
      parsed = new URL(value);
    } catch (error) {
      throw new Error("endpoint must be an absolute URL");
    }
    if (parsed.username || parsed.password) throw new Error("endpoint must not contain credentials");
    if (parsed.protocol === "https:") return parsed.toString();
    if (parsed.protocol === "http:" && allowInsecure && isLoopbackHost(parsed.hostname)) {
      return parsed.toString();
    }
    throw new Error("endpoint must use HTTPS (HTTP is allowed only for loopback with allowInsecure)");
  }

  function semverTuple(value) {
    var match = /^(\d+)\.(\d+)\.(\d+)/.exec(String(value));
    return match ? [Number(match[1]), Number(match[2]), Number(match[3])] : [0, 0, 0];
  }

  function semverLess(a, b) {
    var left = semverTuple(a);
    var right = semverTuple(b);
    for (var i = 0; i < 3; i += 1) {
      if (left[i] < right[i]) return true;
      if (left[i] > right[i]) return false;
    }
    return false;
  }

  async function sha256Hex(value) {
    var cryptoObject = typeof globalThis !== "undefined" ? globalThis.crypto : null;
    if (!cryptoObject || !cryptoObject.subtle) return null;
    var encoded = new TextEncoder().encode(value);
    var digest = await cryptoObject.subtle.digest("SHA-256", encoded);
    return Array.prototype.map
      .call(new Uint8Array(digest), function (byte) {
        return byte.toString(16).padStart(2, "0");
      })
      .join("");
  }

  async function verifyConfigIntegrity(config) {
    if (!config || !config.integrity || config.integrity.algorithm !== "sha256") return false;
    var unsigned = {};
    Object.keys(config).forEach(function (key) {
      if (key !== "integrity") unsigned[key] = config[key];
    });
    var digest = await sha256Hex(canonicalize(unsigned));
    return digest !== null && digest === config.integrity.digest;
  }

  function validatePublishedConfig(config, containerId) {
    if (!isPlainObject(config)) return "configuration must be an object";
    if (config.schema_version !== "1.0") return "unsupported configuration schema_version";
    if (config.kind !== "pytagmanager.container") return "invalid configuration kind";
    if (config.container_id !== containerId) return "configuration container_id does not match";
    if (!CONFIG_VERSION_RE.test(config.config_version || "")) return "invalid config_version";
    if (!Array.isArray(config.events)) return "events must be an array";
    if (!isPlainObject(config.compatibility)) return "compatibility is required";
    if (!Array.isArray(config.tags) || !Array.isArray(config.destinations)) {
      return "tags and destinations must be arrays";
    }
    return null;
  }

  function Client(options) {
    options = options || {};
    if (!options.containerId || !CONTAINER_RE.test(options.containerId)) {
      throw new Error("containerId is required and must be a valid container identifier");
    }
    if (!options.endpoint) throw new Error("endpoint is required");
    this.options = options;
    this.containerId = options.containerId;
    this.endpoint = validateEndpoint(options.endpoint, options.allowInsecure === true);
    this.configUrl = options.configUrl
      ? validateEndpoint(options.configUrl, options.allowInsecure === true)
      : null;
    this.sdkVersion = options.sdkVersion || VERSION;
    this.sdkName = options.sdkName || SDK_NAME;
    this.debug = options.debug === true;
    this.batchSize = Math.max(1, Math.min(Number(options.batchSize) || 10, 100));
    this.flushIntervalMs = Math.max(1000, Number(options.flushIntervalMs) || 5000);
    this.maxQueue = Math.max(1, Math.min(Number(options.maxQueue) || MAX_QUEUE, 1000));
    this.maxRetries = Math.max(0, Number(options.maxRetries) || 3);
    this.retryBaseMs = Math.max(100, Number(options.retryBaseMs) || 500);
    this.requestTimeoutMs = Math.max(1000, Number(options.requestTimeoutMs) || 10000);
    this.persistQueue = options.persistQueue === true;
    this.verifyIntegrity = options.verifyIntegrity !== false;
    this.fetchImpl = options.fetch || (typeof fetch !== "undefined" ? fetch : null);
    this.storage = options.storage === undefined ? safeStorage() : options.storage;
    this.config = null;
    this.configError = null;
    this.configLoaded = false;
    this.configSource = "none";
    this.queue = [];
    this.seenIds = [];
    this.diagnostics = {
      queued: 0,
      sent: 0,
      dropped: 0,
      blockedConsent: 0,
      blockedAllowlist: 0,
      duplicates: 0,
      retries: 0,
      configLoaded: false,
      configFailures: 0,
      lastError: null,
    };
    this._listeners = {};
    this._started = false;
    this._flushing = null;
    this._retryAttempt = 0;
    this._retryAt = 0;
    this._retryTimer = null;
    this._timer = null;
    this._routeStarted = false;
    this._consent = normalizeConsent(
      Object.assign(
        {},
        (options.config && options.config.consent_defaults) || {},
        options.consent || {}
      ),
      options.consent ? "host" : "sdk",
      options.consent ? "explicit" : "default"
    );
    this._queueKey = "ptm_queue_v1_" + this.containerId;
    this._configKey = "ptm_config_v1_" + this.containerId;
    this.ready = this._initialize();
  }

  Client.prototype._initialize = async function () {
    if (this.persistQueue) this._restoreQueue();
    if (this.options.config) {
      this._applyConfig(this.options.config);
    }
    if (this.configUrl) {
      await this._fetchConfig();
    } else if (!this.config) {
      this.configError = "no configUrl or config supplied";
      this.diagnostics.configFailures += 1;
    }
    this._startTimer();
    this._started = true;
    return this.config;
  };

  Client.prototype._emit = function (name, detail) {
    (this._listeners[name] || []).forEach(function (listener) {
      try {
        listener(detail);
      } catch (error) {
        /* listener failures must not break collection */
      }
    });
  };

  Client.prototype.on = function (name, listener) {
    if (typeof listener !== "function") throw new Error("listener must be a function");
    (this._listeners[name] = this._listeners[name] || []).push(listener);
    return this;
  };

  Client.prototype._log = function (message, detail) {
    if (!this.debug) return;
    if (typeof console !== "undefined" && console.debug) {
      console.debug("[PyTagManager] " + message, detail || "");
    }
  };

  Client.prototype._storageGet = function (key) {
    if (!this.storage) return null;
    try {
      return this.storage.getItem(key);
    } catch (error) {
      return null;
    }
  };

  Client.prototype._storageSet = function (key, value) {
    if (!this.storage) return;
    try {
      this.storage.setItem(key, value);
    } catch (error) {
      /* quota/privacy modes are non-fatal */
    }
  };

  Client.prototype._restoreQueue = function () {
    var raw = this._storageGet(this._queueKey);
    if (!raw) return;
    try {
      var stored = JSON.parse(raw);
      if (!Array.isArray(stored)) return;
      var cutoff = Date.now() - 24 * 60 * 60 * 1000;
      var restored = [];
      stored.forEach(function (event) {
        if (!isPlainObject(event)) return;
        var timestamp = parseTimestamp(event.timestamp);
        if (!timestamp || timestamp.getTime() < cutoff) return;
        if (validateEvent(event, { maxSkewSeconds: null }).length) return;
        restored.push(event);
      });
      this.queue = restored.slice(-this.maxQueue);
      this.diagnostics.queued = this.queue.length;
    } catch (error) {
      this._storageSet(this._queueKey, "[]");
    }
  };

  Client.prototype._persistQueue = function () {
    if (!this.persistQueue) return;
    this._storageSet(this._queueKey, JSON.stringify(this.queue.slice(-this.maxQueue)));
  };

  Client.prototype._cacheConfig = function (config) {
    if (!this.storage) return;
    this._storageSet(
      this._configKey,
      JSON.stringify({ fetchedAt: Date.now(), etag: this._etag || null, config: config })
    );
  };

  Client.prototype._readCachedConfig = function () {
    var raw = this._storageGet(this._configKey);
    if (!raw) return null;
    try {
      var value = JSON.parse(raw);
      if (!isPlainObject(value) || !isPlainObject(value.config)) return null;
      if (validatePublishedConfig(value.config, this.containerId)) return null;
      return value;
    } catch (error) {
      return null;
    }
  };

  Client.prototype._applyConfig = function (config) {
    var error = validatePublishedConfig(config, this.containerId);
    if (error) throw new Error(error);
    var minVersion =
      config.compatibility && config.compatibility.min_sdk
        ? config.compatibility.min_sdk.web
        : null;
    if (minVersion && semverLess(this.sdkVersion, minVersion)) {
      throw new Error(
        "SDK version " + this.sdkVersion + " is below container minimum " + minVersion
      );
    }
    this.config = config;
    this.configError = null;
    this.configLoaded = true;
    this.diagnostics.configLoaded = true;
    if (config.consent_defaults && !this.options.consent) {
      this._consent = normalizeConsent(config.consent_defaults, "sdk", "default");
    }
    this._recheckQueue();
    this._log("configuration loaded", { config_version: config.config_version });
    this._emit("config", {
      container_id: config.container_id,
      config_version: config.config_version,
    });
    return this.config;
  };

  Client.prototype._fetchConfig = async function () {
    if (!this.fetchImpl) {
      this.configError = "fetch is unavailable";
      return null;
    }
    var cached = this._readCachedConfig();
    if (cached && cached.config) {
      try {
        if (this.verifyIntegrity) {
          var cachedValid = await verifyConfigIntegrity(cached.config);
          if (!cachedValid) throw new Error("cached configuration integrity check failed");
        }
        this.configSource = "cache";
        this._applyConfig(cached.config);
      } catch (error) {
        this._log("ignoring cached configuration", { reason: error.message });
      }
    }
    var headers = { Accept: "application/json" };
    if (cached && cached.etag) headers["If-None-Match"] = cached.etag;
    var controller =
      typeof AbortController !== "undefined" ? new AbortController() : null;
    var timeout = setTimeout(function () {
      if (controller) controller.abort();
    }, this.requestTimeoutMs);
    try {
      var response = await this.fetchImpl(this.configUrl, {
        method: "GET",
        headers: headers,
        cache: "no-cache",
        credentials: "omit",
        signal: controller ? controller.signal : undefined,
      });
      if (response.status === 304 && cached) {
        this._etag = cached.etag || null;
        this.configSource = "cache";
        this._applyConfig(cached.config);
        return this.config;
      }
      if (!response.ok) throw new Error("configuration HTTP " + response.status);
      var config = await response.json();
      if (config && config.kind === "pytagmanager.environment") {
        if (!config.config_url) throw new Error("environment pointer is missing config_url");
        var resolved = new URL(config.config_url, this.configUrl).toString();
        var configResponse = await this.fetchImpl(resolved, {
          method: "GET",
          headers: { Accept: "application/json" },
          cache: "no-cache",
          credentials: "omit",
        });
        if (!configResponse.ok) {
          throw new Error("configuration HTTP " + configResponse.status);
        }
        config = await configResponse.json();
        this._etag =
          configResponse.headers && configResponse.headers.get
            ? configResponse.headers.get("etag")
            : null;
      } else {
        this._etag = response.headers && response.headers.get ? response.headers.get("etag") : null;
      }
      if (this.verifyIntegrity) {
        var valid = await verifyConfigIntegrity(config);
        if (!valid) throw new Error("configuration integrity check failed");
      }
      this.configSource = "network";
      this._applyConfig(config);
      this._cacheConfig(config);
      return this.config;
    } catch (error) {
      this.diagnostics.configFailures += 1;
      this.configError = error.message;
      this.diagnostics.lastError = "config_fetch_failed";
      this._log("configuration fetch failed", { reason: error.message });
      this._emit("error", { code: "config_fetch_failed", message: error.message });
      if (cached && cached.config && !this.config) {
        try {
          this._applyConfig(cached.config);
        } catch (cachedError) {
          /* keep the original error */
        }
      }
      return this.config;
    } finally {
      clearTimeout(timeout);
    }
  };

  Client.prototype._eventRule = function (name) {
    if (!this.config || !Array.isArray(this.config.events)) return null;
    for (var i = 0; i < this.config.events.length; i += 1) {
      if (this.config.events[i] && this.config.events[i].name === name) return this.config.events[i];
    }
    return null;
  };

  Client.prototype._consentAllows = function (purposes) {
    if (!purposes || !purposes.length) return true;
    for (var i = 0; i < purposes.length; i += 1) {
      if (this._consent.purposes[purposes[i]] !== true) return false;
    }
    return true;
  };

  Client.prototype._allowed = function (event) {
    if (!this.config) return false;
    var rule = this._eventRule(event.event_name);
    if (!rule) {
      this.diagnostics.blockedAllowlist += 1;
      this._emit("blocked", { event_id: event.event_id, reason: "event_not_allowed" });
      return false;
    }
    var purposes = Array.isArray(rule.purposes) ? rule.purposes : [];
    if (!this._consentAllows(purposes)) {
      this.diagnostics.blockedConsent += 1;
      this._emit("blocked", { event_id: event.event_id, reason: "consent_denied" });
      return false;
    }
    return true;
  };

  Client.prototype._recheckQueue = function () {
    if (!this.config) return;
    var kept = [];
    for (var i = 0; i < this.queue.length; i += 1) {
      if (this._allowed(this.queue[i])) kept.push(this.queue[i]);
    }
    if (kept.length !== this.queue.length) this.diagnostics.dropped += this.queue.length - kept.length;
    this.queue = kept;
    this._persistQueue();
  };

  Client.prototype._remember = function (eventId) {
    if (this.seenIds.indexOf(eventId) !== -1) return false;
    this.seenIds.push(eventId);
    if (this.seenIds.length > MAX_SEEN_IDS) this.seenIds.splice(0, this.seenIds.length - MAX_SEEN_IDS);
    return true;
  };

  Client.prototype._createEvent = function (eventName, properties, options) {
    options = options || {};
    if (!properties) properties = {};
    if (!isPlainObject(properties)) throw new Error("properties must be an object");
    var event = buildEvent({
      eventId: options.eventId,
      eventName: eventName,
      timestamp: options.timestamp,
      platform: "web",
      sdkName: this.sdkName,
      sdkVersion: this.sdkVersion,
      containerId: this.containerId,
      configVersion: this.config ? this.config.config_version : null,
      properties: properties,
      consent: this._consent.purposes,
      consentSource: this._consent.source,
      consentProvenance: this._consent.provenance,
      consentUpdatedAt: this._consent.updated_at,
      subject: options.subject,
      correlation: options.correlation || this.options.correlation,
    });
    if (!this._remember(event.event_id)) {
      this.diagnostics.duplicates += 1;
      return null;
    }
    return event;
  };

  Client.prototype.track = function (eventName, properties, options) {
    if (!this.config && this.configError) {
      this.diagnostics.lastError = "config_unavailable";
      this._emit("error", { code: "config_unavailable" });
      return null;
    }
    var event;
    try {
      event = this._createEvent(eventName, properties, options);
    } catch (error) {
      this.diagnostics.lastError = "invalid_event";
      this._emit("error", { code: "invalid_event", issues: error.issues || [] });
      if (this.options.throwOnInvalid) throw error;
      return null;
    }
    if (!event) return null;
    if (this.config && !this._allowed(event)) {
      this.diagnostics.dropped += 1;
      return null;
    }
    this.queue.push(event);
    if (this.queue.length > this.maxQueue) {
      var removed = this.queue.splice(0, this.queue.length - this.maxQueue);
      this.diagnostics.dropped += removed.length;
    }
    this.diagnostics.queued = this.queue.length;
    this._persistQueue();
    this._log("event queued", { event_name: event.event_name, event_id: event.event_id });
    if (this.queue.length >= this.batchSize) this.flush();
    return event.event_id;
  };

  Client.prototype.pageView = function (properties, options) {
    var current = {};
    if (typeof location !== "undefined") {
      current.page_path = location.pathname || "/";
      current.page_url = location.href;
      current.referrer = typeof document !== "undefined" ? document.referrer || "" : "";
    }
    if (typeof document !== "undefined" && document.title) current.page_title = document.title;
    Object.keys(properties || {}).forEach(function (key) {
      current[key] = properties[key];
    });
    return this.track("page_view", current, options);
  };

  Client.prototype.setConsent = function (purposes, options) {
    options = options || {};
    if (!isPlainObject(purposes)) throw new Error("purposes must be an object");
    Object.keys(purposes).forEach(function (purpose) {
      if (!PURPOSE_RE.test(purpose)) throw new Error("invalid consent purpose: " + purpose);
      this._consent.purposes[purpose] = purposes[purpose] === true;
    }, this);
    this._consent.source = options.source || "host";
    this._consent.provenance = options.provenance || "explicit";
    this._consent.updated_at = nowIso();
    this._recheckQueue();
    this._persistQueue();
    this._log("consent updated", { purposes: Object.keys(purposes) });
    return this;
  };

  Client.prototype.getConsent = function () {
    return JSON.parse(JSON.stringify(this._consent));
  };

  Client.prototype.startAutoPageViews = function () {
    if (this._routeStarted) return this;
    this._routeStarted = true;
    var self = this;
    var lastPath = typeof location !== "undefined" ? location.pathname : "";
    function onRoute() {
      if (typeof location !== "undefined" && location.pathname === lastPath) return;
      lastPath = typeof location !== "undefined" ? location.pathname : "";
      self.pageView();
    }
    this._onPopState = onRoute;
    if (typeof window !== "undefined" && window.addEventListener) {
      window.addEventListener("popstate", onRoute);
    }
    if (typeof history !== "undefined" && history.pushState) {
      this._originalPushState = history.pushState;
      this._originalReplaceState = history.replaceState;
      history.pushState = function () {
        var result = self._originalPushState.apply(history, arguments);
        onRoute();
        return result;
      };
      history.replaceState = function () {
        var result = self._originalReplaceState.apply(history, arguments);
        onRoute();
        return result;
      };
    }
    this.pageView();
    return this;
  };

  Client.prototype.stopAutoPageViews = function () {
    if (!this._routeStarted) return this;
    this._routeStarted = false;
    if (typeof window !== "undefined" && window.removeEventListener && this._onPopState) {
      window.removeEventListener("popstate", this._onPopState);
    }
    if (typeof history !== "undefined" && this._originalPushState) {
      history.pushState = this._originalPushState;
      history.replaceState = this._originalReplaceState;
    }
    return this;
  };

  Client.prototype._startTimer = function () {
    var self = this;
    if (this._timer) return;
    this._timer = setInterval(function () {
      self.flush();
    }, this.flushIntervalMs);
    if (this._timer && typeof this._timer.unref === "function") this._timer.unref();
    if (typeof window !== "undefined" && window.addEventListener) {
      this._onPageHide = function () {
        self.flush({ keepalive: true });
      };
      window.addEventListener("pagehide", this._onPageHide);
      this._onVisibility = function () {
        if (document.visibilityState === "hidden") self.flush({ keepalive: true });
      };
      document.addEventListener("visibilitychange", this._onVisibility);
    }
  };

  Client.prototype._retryDelay = function (attempt, retryAfter) {
    if (retryAfter && typeof retryAfter === "string") {
      var seconds = Number(retryAfter);
      if (isFinite(seconds)) return Math.min(30000, Math.max(1000, seconds * 1000));
      var date = Date.parse(retryAfter);
      if (!isNaN(date)) return Math.min(30000, Math.max(1000, date - Date.now()));
    }
    var base = this.retryBaseMs * Math.pow(2, attempt);
    var jitter = Math.random() * Math.min(1000, base);
    return Math.min(30000, base + jitter);
  };

  Client.prototype.flush = function (options) {
    options = options || {};
    var self = this;
    if (this._flushing) return this._flushing;
    if (!this.config) {
      return Promise.resolve({ sent: 0, pending: this.queue.length, reason: "config_not_loaded" });
    }
    if (this._retryAt && Date.now() < this._retryAt) {
      return Promise.resolve({
        sent: 0,
        pending: this.queue.length,
        retry_in_ms: this._retryAt - Date.now(),
      });
    }
    this._recheckQueue();
    var batch = this.queue.slice(0, this.batchSize);
    if (!batch.length) {
      return Promise.resolve({ sent: 0, pending: 0 });
    }
    var attempt = this._retryAttempt;
    this._flushing = this._sendBatch(batch, attempt, options).finally(function () {
      self._flushing = null;
    });
    return this._flushing;
  };

  Client.prototype._sendBatch = async function (batch, attempt, options) {
    var self = this;
    var payload = { schema_version: SCHEMA_VERSION, events: batch };
    var controller = typeof AbortController !== "undefined" ? new AbortController() : null;
    var timeout = setTimeout(function () {
      if (controller) controller.abort();
    }, this.requestTimeoutMs);
    try {
      var response = await this.fetchImpl(this.endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify(payload),
        credentials: "omit",
        keepalive: options.keepalive === true,
        signal: controller ? controller.signal : undefined,
      });
      clearTimeout(timeout);
      if (response.status >= 200 && response.status < 300) {
        var ids = {};
        batch.forEach(function (event) {
          ids[event.event_id] = true;
        });
        this.queue = this.queue.filter(function (event) {
          return !ids[event.event_id];
        });
        this.diagnostics.sent += batch.length;
        this.diagnostics.queued = this.queue.length;
        this.diagnostics.lastError = null;
        this._retryAttempt = 0;
        this._retryAt = 0;
        this._persistQueue();
        this._log("batch delivered", { count: batch.length });
        this._emit("delivered", { count: batch.length });
        return { sent: batch.length, pending: this.queue.length };
      }
      var retryAfter = response.headers && response.headers.get ? response.headers.get("Retry-After") : null;
      var transient = response.status === 408 || response.status === 425 || response.status === 429 || response.status >= 500;
      if (transient && attempt < this.maxRetries) {
        this.diagnostics.retries += 1;
        this._retryAttempt = attempt + 1;
        this.diagnostics.lastError = "transient_http_" + response.status;
        var delay = this._retryDelay(attempt, retryAfter);
        this._retryAt = Date.now() + delay;
        if (this._retryTimer) clearTimeout(this._retryTimer);
        this._retryTimer = setTimeout(function () {
          self._retryAt = 0;
          self.flush();
        }, Math.ceil(delay));
        if (this._retryTimer && typeof this._retryTimer.unref === "function") this._retryTimer.unref();
        return { sent: 0, pending: this.queue.length, retry_in_ms: delay };
      }
      this.queue = this.queue.filter(function (event) {
        return !batch.some(function (candidate) {
          return candidate.event_id === event.event_id;
        });
      });
      this.diagnostics.dropped += batch.length;
      this.diagnostics.queued = this.queue.length;
      this.diagnostics.lastError = "delivery_rejected_" + response.status;
      this._retryAttempt = 0;
      this._retryAt = 0;
      this._persistQueue();
      this._emit("error", { code: "delivery_rejected", status: response.status });
      return { sent: 0, pending: this.queue.length, dropped: batch.length };
    } catch (error) {
      clearTimeout(timeout);
      if (attempt < this.maxRetries) {
        this.diagnostics.retries += 1;
        this._retryAttempt = attempt + 1;
        this.diagnostics.lastError = "network_error";
        var networkDelay = this._retryDelay(attempt, null);
        this._retryAt = Date.now() + networkDelay;
        if (this._retryTimer) clearTimeout(this._retryTimer);
        this._retryTimer = setTimeout(function () {
          self._retryAt = 0;
          self.flush();
        }, Math.ceil(networkDelay));
        if (this._retryTimer && typeof this._retryTimer.unref === "function") this._retryTimer.unref();
        return { sent: 0, pending: this.queue.length, retry_in_ms: networkDelay };
      }
      this.diagnostics.lastError = "network_error";
      this._retryAttempt = 0;
      this._retryAt = 0;
      this._emit("error", { code: "network_error", message: error.message });
      return { sent: 0, pending: this.queue.length, error: error.message };
    }
  };

  Client.prototype.getDiagnostics = function () {
    return JSON.parse(JSON.stringify(this.diagnostics));
  };

  Client.prototype.debugSnapshot = function () {
    return {
      sdk: this.sdkName,
      sdk_version: this.sdkVersion,
      schema_version: SCHEMA_VERSION,
      container_id: this.containerId,
      endpoint: this.endpoint,
      config_version: this.config ? this.config.config_version : null,
      config_source: this.configSource,
      config_error: this.configError,
      consent: JSON.parse(JSON.stringify(this._consent.purposes)),
      queued: this.queue.length,
      diagnostics: this.getDiagnostics(),
    };
  };

  Client.prototype.close = function () {
    this.stopAutoPageViews();
    if (this._timer) clearInterval(this._timer);
    this._timer = null;
    if (this._retryTimer) clearTimeout(this._retryTimer);
    this._retryTimer = null;
    if (typeof window !== "undefined" && window.removeEventListener) {
      if (this._onPageHide) window.removeEventListener("pagehide", this._onPageHide);
      if (this._onVisibility) document.removeEventListener("visibilitychange", this._onVisibility);
    }
    this._persistQueue();
  };

  function safeStorage() {
    try {
      if (typeof localStorage !== "undefined") {
        var key = "__ptm_test__";
        localStorage.setItem(key, "1");
        localStorage.removeItem(key);
        return localStorage;
      }
    } catch (error) {
      return null;
    }
    return null;
  }

  function init(options) {
    var client = new Client(options);
    if (options && options.autoPageViews) client.startAutoPageViews();
    return client;
  }

  return {
    VERSION: VERSION,
    SDK_NAME: SDK_NAME,
    SCHEMA_VERSION: SCHEMA_VERSION,
    EventValidationError: EventValidationError,
    init: init,
    buildEvent: buildEvent,
    validateEvent: validateEvent,
    isSensitiveProperty: isSensitiveProperty,
    canonicalize: canonicalize,
    verifyConfigIntegrity: verifyConfigIntegrity,
  };
});
