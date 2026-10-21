package com.pytagmanager.sdk

import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.net.HttpURLConnection
import java.net.URL
import java.time.Instant
import java.time.ZoneOffset
import java.time.format.DateTimeFormatter
import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors
import java.util.concurrent.ScheduledExecutorService
import java.util.concurrent.TimeUnit

enum class TrackOutcome { QUEUED, SUPPRESSED, INVALID }

data class Diagnostic(
    val timestamp: String,
    val code: String,
    val message: String,
    val metadata: Map<String, String> = emptyMap(),
)

data class DebugSnapshot(
    val containerId: String,
    val endpoint: String,
    val configVersion: String?,
    val configSource: String,
    val consentPurposes: Map<String, Boolean>,
    val queueCount: Int,
    val recentDiagnostics: List<Diagnostic>,
)

data class FlushResult(
    val sent: Int,
    val remaining: Int,
    val httpStatus: Int?,
    val error: String?,
)

class PyTagManager internal constructor(
    val containerId: String,
    private val endpoint: URL,
    private val configUrl: URL?,
    storageDirectory: File,
    private val sdkVersion: String,
    private val appVersion: String?,
    private val allowTrackingWithoutConfig: Boolean,
) {
    constructor(
        context: android.content.Context,
        containerId: String,
        endpoint: URL,
        configUrl: URL? = null,
        storageDirectory: File = File(context.filesDir, "pytagmanager"),
        sdkVersion: String = "0.1.0",
        appVersion: String? = context.packageManager
            .getPackageInfo(context.packageName, 0).versionName,
        allowTrackingWithoutConfig: Boolean = false,
    ) : this(
        containerId, endpoint, configUrl, storageDirectory,
        sdkVersion, appVersion, allowTrackingWithoutConfig,
    )

    constructor(
        context: android.content.Context,
        containerId: String,
        endpoint: URL,
        storageDirectory: File,
    ) : this(context, containerId, endpoint, null, storageDirectory)

    private val lock = Any()
    private val queue = EventQueue(storageDirectory)
    private val configCache = File(storageDirectory, "public-config.json")
    private val diagnostics = mutableListOf<Diagnostic>()
    private var config: PublicConfig? = null
    private var configSource = "none"
    private var consent: Consent? = null
    private var autoFlushExecutor: ScheduledExecutorService? = null

    init {
        require(endpoint.protocol == "https" || isLoopback(endpoint)) {
            "collection endpoint must use HTTPS except for loopback testing"
        }
    }

    fun setConsent(purposes: Map<String, Boolean>, source: String = "sdk",
                   provenance: String = "explicit") {
        val updated = Consent(
            purposes = purposes,
            source = source,
            provenance = provenance,
            updatedAt = DateTimeFormatter.ofPattern("yyyy-MM-dd'T'HH:mm:ss'Z'")
                .withZone(ZoneOffset.UTC).format(Instant.now()),
        )
        synchronized(lock) { consent = updated }
        val withdrawn = purposes.filterValues { !it }.keys
        if (withdrawn.isNotEmpty()) {
            queue.removeIf { event ->
                val granted = event.consent?.grantedPurposes ?: return@removeIf true
                granted.any { it in withdrawn }
            }
            record("consent_withdrawn", "Removed unsent events for withdrawn purposes.")
        }
    }

    @Throws(Exception::class)
    fun configure() {
        val url = configUrl ?: throw ConfigException("no config URL was supplied")
        try {
            val data = fetch(url)
            ConfigVerifier.verifyIntegrity(data)
            val loaded = ConfigVerifier.decode(data)
            configCache.parentFile?.mkdirs()
            configCache.writeBytes(data)
            synchronized(lock) {
                config = loaded
                configSource = "network"
            }
            record("config_loaded", "Loaded verified public configuration ${loaded.configVersion}.")
        } catch (error: Exception) {
            val cached = if (configCache.isFile) {
                try {
                    val data = configCache.readBytes()
                    ConfigVerifier.verifyIntegrity(data)
                    ConfigVerifier.decode(data)
                } catch (_: Exception) { null }
            } else null
            if (cached == null) {
                record("config_failed", "Remote config and cache were unavailable.")
                throw error
            }
            synchronized(lock) {
                config = cached
                configSource = "cache"
            }
            record("config_cache_fallback", "Remote config failed; using verified cache.")
        }
    }

    fun track(name: String, properties: JSONObject = JSONObject(),
              subjectId: String? = null): TrackOutcome {
        val activeConfig: PublicConfig?
        val activeConsent: Consent?
        synchronized(lock) {
            activeConfig = config
            activeConsent = consent
        }
        val eventConfig = activeConfig?.event(name)
        if (eventConfig != null && eventConfig.purposes.isNotEmpty()) {
            val granted = activeConsent?.grantedPurposes ?: emptySet()
            if (eventConfig.purposes.none { it in granted }) {
                record("event_suppressed", "Event $name lacks a granted purpose.")
                return TrackOutcome.SUPPRESSED
            }
        } else if (activeConfig != null && eventConfig == null && !allowTrackingWithoutConfig) {
            record("event_suppressed", "Event $name is not in the active configuration.")
            return TrackOutcome.SUPPRESSED
        }
        val event = Event.create(
            eventName = name,
            containerId = containerId,
            source = EventSource(appVersion = appVersion),
            consent = activeConsent,
            subjectId = subjectId,
            configVersion = activeConfig?.configVersion,
            properties = properties,
        )
        return try {
            event.validate()
            queue.enqueue(event)
            TrackOutcome.QUEUED
        } catch (error: Exception) {
            record("event_invalid", "Event $name failed local validation.")
            TrackOutcome.INVALID
        }
    }

    fun trackScreen(name: String, properties: JSONObject = JSONObject()): TrackOutcome {
        properties.put("screen_name", name)
        return track("screen_view", properties)
    }

    @Throws(Exception::class)
    fun flush(maxRetries: Int = 3): FlushResult {
        val events = queue.load().take(100)
        if (events.isEmpty()) return FlushResult(0, queue.count(), null, null)
        val batch = JSONObject().apply {
            put("schema_version", "1.0")
            val array = JSONArray()
            events.forEach { array.put(it.toJson()) }
            put("events", array)
        }
        var lastStatus: Int? = null
        var lastError: String? = null
        for (attempt in 0 until maxRetries.coerceAtLeast(1)) {
            try {
                val response = post(batch.toString().toByteArray(Charsets.UTF_8))
                lastStatus = response.status
                if (response.status in 200..299) {
                    val retained = transientIds(response.body)
                    val sentIds = events.map { it.eventId }.toSet()
                    queue.remove(sentIds - retained)
                    return FlushResult(events.size - retained.size, queue.count(),
                        response.status, null)
                }
                lastError = "HTTP ${response.status}"
                if (response.status != 429 && response.status < 500) break
            } catch (error: Exception) {
                lastError = error.message ?: error.javaClass.simpleName
            }
            if (attempt + 1 < maxRetries) Thread.sleep(250L shl attempt)
        }
        record("flush_failed", "Batch delivery did not complete.")
        return FlushResult(0, queue.count(), lastStatus, lastError)
    }

    @Synchronized
    fun startAutoFlush(intervalSeconds: Long = 15) {
        stopAutoFlush()
        val executor = Executors.newSingleThreadScheduledExecutor { runnable ->
            Thread(runnable, "pytagmanager-flush").apply { isDaemon = true }
        }
        executor.scheduleWithFixedDelay(
            {
                try {
                    flush()
                } catch (error: Exception) {
                    record("flush_failed", "Background delivery failed.")
                }
            },
            0,
            intervalSeconds.coerceAtLeast(1),
            TimeUnit.SECONDS,
        )
        autoFlushExecutor = executor
    }

    @Synchronized
    fun stopAutoFlush() {
        autoFlushExecutor?.shutdownNow()
        autoFlushExecutor = null
    }

    fun flushAsync(executor: ExecutorService, callback: (FlushResult) -> Unit) {
        executor.execute {
            callback(try {
                flush()
            } catch (error: Exception) {
                FlushResult(0, queue.count(), null, error.message)
            })
        }
    }

    fun snapshot(): DebugSnapshot {
        val activeConfig: PublicConfig?
        val activeConsent: Consent?
        val recent: List<Diagnostic>
        val source: String
        synchronized(lock) {
            activeConfig = config
            activeConsent = consent
            source = configSource
            recent = diagnostics.takeLast(20)
        }
        return DebugSnapshot(
            containerId = containerId,
            endpoint = endpoint.toString(),
            configVersion = activeConfig?.configVersion,
            configSource = source,
            consentPurposes = activeConsent?.purposes ?: emptyMap(),
            queueCount = queue.count(),
            recentDiagnostics = recent,
        )
    }

    private data class HttpResponse(val status: Int, val body: ByteArray)

    private fun fetch(url: URL): ByteArray {
        val connection = url.openConnection() as HttpURLConnection
        connection.connectTimeout = 5_000
        connection.readTimeout = 8_000
        connection.instanceFollowRedirects = false
        connection.setRequestProperty("Accept", "application/json")
        try {
            if (connection.responseCode !in 200..299) {
                throw ConfigException("config request failed with HTTP ${connection.responseCode}")
            }
            return connection.inputStream.use { it.readBytes() }
        } finally {
            connection.disconnect()
        }
    }

    private fun post(body: ByteArray): HttpResponse {
        val connection = endpoint.openConnection() as HttpURLConnection
        connection.connectTimeout = 5_000
        connection.readTimeout = 8_000
        connection.instanceFollowRedirects = false
        connection.requestMethod = "POST"
        connection.doOutput = true
        connection.setRequestProperty("Content-Type", "application/json")
        connection.setRequestProperty("Accept", "application/json")
        connection.setRequestProperty("User-Agent", "pytagmanager-android/$sdkVersion")
        connection.setFixedLengthStreamingMode(body.size)
        try {
            connection.outputStream.use { it.write(body) }
            val status = connection.responseCode
            val stream = if (status in 200..299) connection.inputStream else connection.errorStream
            val responseBody = stream?.use { it.readBytes() } ?: ByteArray(0)
            return HttpResponse(status, responseBody)
        } finally {
            connection.disconnect()
        }
    }

    private fun transientIds(body: ByteArray): Set<String> {
        if (body.isEmpty()) return emptySet()
        return try {
            val results = JSONObject(body.toString(Charsets.UTF_8)).optJSONArray("results")
                ?: return emptySet()
            val ids = mutableSetOf<String>()
            for (index in 0 until results.length()) {
                val item = results.getJSONObject(index)
                val status = item.optString("status")
                if (status == "transient_error" || status == "rate_limited") {
                    item.optString("event_id").ifBlank { null }?.let { ids += it }
                }
            }
            ids
        } catch (_: Exception) {
            emptySet()
        }
    }

    private fun record(code: String, message: String,
                       metadata: Map<String, String> = emptyMap()) {
        val diagnostic = Diagnostic(
            timestamp = Instant.now().toString(),
            code = code,
            message = message,
            metadata = metadata,
        )
        synchronized(lock) {
            diagnostics += diagnostic
            if (diagnostics.size > 100) diagnostics.subList(0, diagnostics.size - 100).clear()
        }
    }

    private fun isLoopback(url: URL): Boolean =
        url.host in setOf("127.0.0.1", "::1", "localhost")
}
