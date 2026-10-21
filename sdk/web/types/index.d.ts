export interface ConsentPurposes {
  [purpose: string]: boolean;
}

export interface EventSource {
  platform: "web" | "android" | "ios" | "server";
  sdk_name: string;
  sdk_version: string;
  app_version?: string;
}

export interface ConsentState {
  purposes: ConsentPurposes;
  source: "sdk" | "host" | "server" | "unknown";
  provenance: "explicit" | "default" | "stored" | "unknown";
  updated_at: string;
}

export interface EventDocument {
  schema_version: "1.0";
  event_id: string;
  event_name: string;
  timestamp: string;
  source: EventSource;
  container_id: string;
  config_version?: string | null;
  subject?: { id: string; type: "user" | "anonymous" };
  consent?: ConsentState;
  correlation?: { correlation_id?: string; session_id?: string };
  properties: Record<string, unknown>;
}

export interface ValidationIssue {
  code: string;
  field: string;
  message: string;
}

export interface PublishedEventRule {
  name: string;
  purposes: string[];
  tag_ids: string[];
}

export interface PublishedConfig {
  schema_version: "1.0";
  kind: "pytagmanager.container";
  container_id: string;
  config_version: string;
  revision_number: number;
  events: PublishedEventRule[];
  consent_defaults?: ConsentPurposes;
  compatibility: {
    event_contract: "1.0";
    min_sdk: { web: string; android: string; ios: string };
  };
  integrity?: { algorithm: "sha256"; digest: string };
  [key: string]: unknown;
}

export interface InitOptions {
  containerId: string;
  endpoint: string;
  configUrl?: string;
  config?: PublishedConfig;
  sdkVersion?: string;
  sdkName?: string;
  consent?: ConsentPurposes;
  batchSize?: number;
  flushIntervalMs?: number;
  maxQueue?: number;
  maxRetries?: number;
  retryBaseMs?: number;
  requestTimeoutMs?: number;
  persistQueue?: boolean;
  verifyIntegrity?: boolean;
  autoPageViews?: boolean;
  throwOnInvalid?: boolean;
  debug?: boolean;
  allowInsecure?: boolean;
  fetch?: typeof fetch;
  storage?: Pick<Storage, "getItem" | "setItem" | "removeItem"> | null;
  correlation?: { correlation_id?: string; session_id?: string };
}

export interface FlushResult {
  sent: number;
  pending: number;
  dropped?: number;
  retry_in_ms?: number;
  reason?: string;
  error?: string;
}

export interface Diagnostics {
  queued: number;
  sent: number;
  dropped: number;
  blockedConsent: number;
  blockedAllowlist: number;
  duplicates: number;
  retries: number;
  configLoaded: boolean;
  configFailures: number;
  lastError: string | null;
}

export interface DebugSnapshot {
  sdk: string;
  sdk_version: string;
  schema_version: string;
  container_id: string;
  endpoint: string;
  config_version: string | null;
  config_source: "none" | "network" | "cache";
  config_error: string | null;
  consent: Record<string, boolean>;
  queued: number;
  diagnostics: Diagnostics;
}

export interface TrackOptions {
  eventId?: string;
  timestamp?: string | Date;
  subject?: { id: string; type: "user" | "anonymous" };
  correlation?: { correlation_id?: string; session_id?: string };
}

export class EventValidationError extends Error {
  issues: ValidationIssue[];
}

export declare class Client {
  readonly containerId: string;
  readonly ready: Promise<PublishedConfig | null>;
  config: PublishedConfig | null;
  configError: string | null;
  configLoaded: boolean;
  track(eventName: string, properties?: Record<string, unknown>, options?: TrackOptions): string | null;
  pageView(properties?: Record<string, unknown>, options?: TrackOptions): string | null;
  setConsent(purposes: ConsentPurposes, options?: { source?: string; provenance?: string }): this;
  getConsent(): ConsentState;
  startAutoPageViews(): this;
  stopAutoPageViews(): this;
  flush(options?: { keepalive?: boolean }): Promise<FlushResult>;
  getDiagnostics(): Diagnostics;
  debugSnapshot(): DebugSnapshot;
  on(name: "config" | "error" | "blocked" | "delivered", listener: (detail: unknown) => void): this;
  close(): void;
}

export declare const VERSION: string;
export declare const SDK_NAME: string;
export declare const SCHEMA_VERSION: "1.0";
export declare function init(options: InitOptions): Client;
export declare function buildEvent(options: Record<string, unknown>): EventDocument;
export declare function validateEvent(document: unknown, options?: { now?: string | Date; maxSkewSeconds?: number | null; maxBytes?: number }): ValidationIssue[];
export declare function isSensitiveProperty(key: string): boolean;
export declare function canonicalize(value: unknown): string;
export declare function verifyConfigIntegrity(config: PublishedConfig): Promise<boolean>;
