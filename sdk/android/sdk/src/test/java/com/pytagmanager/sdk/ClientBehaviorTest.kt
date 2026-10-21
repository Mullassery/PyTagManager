package com.pytagmanager.sdk

import org.json.JSONArray
import org.json.JSONObject
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertThrows
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import java.io.ByteArrayOutputStream
import java.io.InputStream
import java.io.OutputStream
import java.net.InetAddress
import java.net.ServerSocket
import java.net.Socket
import java.net.SocketException
import java.net.URL
import java.util.Collections

class ClientBehaviorTest {
    @get:Rule
    val folder = TemporaryFolder()

    private val server = TestServer()
    private val requests: List<String> get() = server.requests

    @Before
    fun startServer() {
        server.start()
    }

    @After
    fun stopServer() {
        server.stop()
    }

    private fun manager(
        configUrl: URL? = null,
        allowTrackingWithoutConfig: Boolean = true,
    ): PyTagManager = PyTagManager(
        "acme-android",
        URL("http://127.0.0.1:${server.port}/collect"),
        configUrl,
        folder.newFolder(),
        "0.1.0",
        null,
        allowTrackingWithoutConfig,
    )

    private fun configBytes(purposes: List<String> = listOf("analytics")): ByteArray {
        val document = JSONObject(
            """
            {
              "schema_version": "1.0",
              "kind": "pytagmanager.container",
              "container_id": "acme-android",
              "config_version": "2026-10-20T12:00:00Z",
              "revision_number": 3,
              "event_schema_version": "1.0",
              "events": [
                {"name": "purchase", "purposes": ${JSONArray(purposes)}, "tag_ids": []},
                {"name": "screen_view", "purposes": [], "tag_ids": []}
              ],
              "consent_defaults": {"analytics": false}
            }
            """.trimIndent()
        )
        val digest = ConfigVerifier.sha256(ConfigVerifier.canonicalJson(document))
        document.put(
            "integrity",
            JSONObject().put("algorithm", "sha256").put("digest", digest),
        )
        return document.toString().toByteArray(Charsets.UTF_8)
    }

    private fun awaitQueue(manager: PyTagManager, expected: Int, timeoutMs: Long = 5_000) {
        val deadline = System.currentTimeMillis() + timeoutMs
        while (System.currentTimeMillis() < deadline) {
            if (manager.snapshot().queueCount == expected) return
            Thread.sleep(25)
        }
        assertEquals(expected, manager.snapshot().queueCount)
    }

    @Test
    fun tracksAndFlushesBatchWithContractEnvelope() {
        val manager = manager()
        assertEquals(
            TrackOutcome.QUEUED,
            manager.track("purchase", JSONObject().put("value", 12)),
        )
        assertEquals(1, manager.snapshot().queueCount)

        val result = manager.flush()

        assertEquals(1, result.sent)
        assertEquals(0, result.remaining)
        assertEquals(200, result.httpStatus)
        assertEquals(0, manager.snapshot().queueCount)
        val batch = JSONObject(requests.single())
        assertEquals("1.0", batch.getString("schema_version"))
        val event = batch.getJSONArray("events").getJSONObject(0)
        assertEquals("purchase", event.getString("event_name"))
        assertEquals(12, event.getJSONObject("properties").getInt("value"))
        assertEquals("android", event.getJSONObject("source").getString("platform"))
        assertFalse(batch.has("destination"))
    }

    @Test
    fun retainsEventsReportedAsTransient() {
        var firstAttempt = true
        server.collectHandler = { body ->
            if (firstAttempt) {
                firstAttempt = false
                val eventId = JSONObject(body).getJSONArray("events")
                    .getJSONObject(0).getString("event_id")
                val result = JSONObject()
                    .put("event_id", eventId)
                    .put("status", "transient_error")
                val response = JSONObject().put("results", JSONArray().put(result))
                200 to response.toString()
            } else {
                200 to "{}"
            }
        }
        val manager = manager()
        manager.track("purchase")

        val first = manager.flush()
        assertEquals(0, first.sent)
        assertEquals(1, first.remaining)
        assertEquals(1, manager.snapshot().queueCount)

        val second = manager.flush()
        assertEquals(1, second.sent)
        assertEquals(0, second.remaining)
    }

    @Test
    fun retriesServerErrorsAndRetainsBatch() {
        var attempts = 0
        server.collectHandler = {
            attempts += 1
            503 to ""
        }
        val manager = manager()
        manager.track("purchase")

        val result = manager.flush(maxRetries = 2)

        assertEquals(2, attempts)
        assertEquals(503, result.httpStatus)
        assertEquals(0, result.sent)
        assertEquals(1, result.remaining)
        assertTrue(manager.snapshot().recentDiagnostics.any { it.code == "flush_failed" })
    }

    @Test
    fun autoFlushDeliversQueuedEvents() {
        val manager = manager()
        manager.track("purchase")
        manager.startAutoFlush(intervalSeconds = 1)
        try {
            awaitQueue(manager, 0)
            assertTrue(requests.isNotEmpty())
        } finally {
            manager.stopAutoFlush()
        }
    }

    @Test
    fun configSuppressesUnknownAndUnconsentedEvents() {
        server.configHandler = { 200 to String(configBytes(), Charsets.UTF_8) }
        val manager = manager(
            configUrl = URL("http://127.0.0.1:${server.port}/config.json"),
            allowTrackingWithoutConfig = false,
        )
        manager.configure()

        assertEquals(TrackOutcome.SUPPRESSED, manager.track("purchase"))
        assertEquals(TrackOutcome.SUPPRESSED, manager.track("unknown_event"))

        manager.setConsent(mapOf("analytics" to true))
        assertEquals(TrackOutcome.QUEUED, manager.track("purchase"))
        assertEquals(1, manager.snapshot().queueCount)
    }

    @Test
    fun consentWithdrawalPurgesUnsentEventsAndDiagnosticsStaySanitized() {
        server.configHandler = { 200 to String(configBytes(), Charsets.UTF_8) }
        val manager = manager(
            configUrl = URL("http://127.0.0.1:${server.port}/config.json"),
            allowTrackingWithoutConfig = false,
        )
        manager.configure()
        manager.setConsent(mapOf("analytics" to true))
        manager.track("purchase")
        assertEquals(1, manager.snapshot().queueCount)

        manager.setConsent(mapOf("analytics" to false))

        assertEquals(0, manager.snapshot().queueCount)
        assertTrue(manager.snapshot().recentDiagnostics.any { it.code == "consent_withdrawn" })

        manager.setConsent(mapOf("analytics" to true))
        assertEquals(
            TrackOutcome.INVALID,
            manager.track("purchase", JSONObject().put("password", "hunter2")),
        )
        val snapshot = manager.snapshot()
        assertTrue(snapshot.recentDiagnostics.any { it.code == "event_invalid" })
        assertFalse(snapshot.toString().contains("hunter2"))
        assertFalse(snapshot.toString().contains("properties"))
    }

    @Test
    fun configureFallsBackToVerifiedCache() {
        var available = true
        val body = String(configBytes(), Charsets.UTF_8)
        server.configHandler = { if (available) 200 to body else 503 to "" }
        val manager = manager(
            configUrl = URL("http://127.0.0.1:${server.port}/config.json"),
        )
        manager.configure()
        assertEquals("network", manager.snapshot().configSource)
        assertEquals("2026-10-20T12:00:00Z", manager.snapshot().configVersion)

        available = false
        manager.configure()

        assertEquals("cache", manager.snapshot().configSource)
        assertEquals("2026-10-20T12:00:00Z", manager.snapshot().configVersion)
        assertTrue(
            manager.snapshot().recentDiagnostics.any { it.code == "config_cache_fallback" }
        )
    }

    @Test
    fun configureFailsClosedOnInvalidIntegrity() {
        server.configHandler = {
            200 to """{"schema_version":"1.0","kind":"pytagmanager.container"}"""
        }
        val manager = manager(
            configUrl = URL("http://127.0.0.1:${server.port}/config.json"),
        )
        assertThrows(ConfigException::class.java) { manager.configure() }
        assertEquals("none", manager.snapshot().configSource)
        assertTrue(manager.snapshot().recentDiagnostics.any { it.code == "config_failed" })
    }

    @Test
    fun rejectsPlaintextRemoteEndpoints() {
        assertThrows(IllegalArgumentException::class.java) {
            PyTagManager(
                "acme-android",
                URL("http://events.example.com/collect"),
                null,
                folder.newFolder(),
                "0.1.0",
                null,
                true,
            )
        }
    }

    private class TestServer {
        val requests = Collections.synchronizedList(mutableListOf<String>())
        private val socket = ServerSocket(
            0,
            50,
            InetAddress.getByName("127.0.0.1"),
        )
        private var worker: Thread? = null

        @Volatile
        private var running = false

        @Volatile
        var collectHandler: (String) -> Pair<Int, String> = { 200 to "{}" }

        @Volatile
        var configHandler: () -> Pair<Int, String> = { 404 to "" }

        val port: Int get() = socket.localPort

        fun start() {
            running = true
            worker = Thread({ acceptLoop() }, "android-sdk-test-http").apply {
                isDaemon = true
                start()
            }
        }

        fun stop() {
            running = false
            try {
                socket.close()
            } catch (_: Exception) {
            }
            worker?.join(2_000)
            worker = null
        }

        private fun acceptLoop() {
            while (running) {
                try {
                    socket.accept().use { connection -> handle(connection) }
                } catch (_: SocketException) {
                    return
                } catch (_: Exception) {
                    if (!running) return
                }
            }
        }

        private fun handle(connection: Socket) {
            connection.soTimeout = 2_000
            val input = connection.getInputStream()
            val headers = readHeaders(input)
            val lines = headers.split("\r\n")
            val path = lines.first().split(" ").getOrNull(1).orEmpty()
            val length = lines.firstOrNull {
                it.startsWith("Content-Length:", ignoreCase = true)
            }?.substringAfter(":")?.trim()?.toIntOrNull() ?: 0
            val body = String(readExactly(input, length), Charsets.UTF_8)
            if (path == "/collect") requests += body
            val response = if (path == "/config.json") configHandler() else collectHandler(body)
            writeResponse(connection.getOutputStream(), response)
        }

        private fun readHeaders(input: InputStream): String {
            val buffer = ByteArrayOutputStream()
            var matched = 0
            while (matched < 4) {
                val byte = input.read()
                if (byte < 0) break
                buffer.write(byte)
                matched = when {
                    byte == '\r'.code && (matched == 0 || matched == 2) -> matched + 1
                    byte == '\n'.code && (matched == 1 || matched == 3) -> matched + 1
                    byte == '\r'.code -> 1
                    else -> 0
                }
            }
            return buffer.toString(Charsets.UTF_8.name())
        }

        private fun readExactly(input: InputStream, length: Int): ByteArray {
            val body = ByteArray(length)
            var offset = 0
            while (offset < length) {
                val read = input.read(body, offset, length - offset)
                if (read < 0) break
                offset += read
            }
            return body.copyOf(offset)
        }

        private fun writeResponse(output: OutputStream, response: Pair<Int, String>) {
            val body = response.second.toByteArray(Charsets.UTF_8)
            val reason = if (response.first == 200) "OK" else "Service Unavailable"
            val headers = "HTTP/1.1 ${response.first} $reason\r\n" +
                "Content-Type: application/json\r\n" +
                "Content-Length: ${body.size}\r\n" +
                "Connection: close\r\n\r\n"
            output.write(headers.toByteArray(Charsets.UTF_8))
            output.write(body)
            output.flush()
        }
    }
}
