package com.pytagmanager.sdk

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertThrows
import org.junit.Assert.assertTrue
import org.junit.Test
import java.time.Instant

class EventContractTest {
    private fun fixture(name: String): String =
        javaClass.classLoader!!.getResource("fixtures/$name")!!.readText()

    @Test
    fun parsesSharedAndroidFixture() {
        val event = Event.parse(JSONObject(fixture("android_custom.json")))
        event.validate(Instant.parse("2026-10-20T12:02:03Z"))
        assertEquals("add_to_cart", event.eventName)
        assertEquals("user-42", event.subjectId)
        assertNull(event.configVersion)
        assertEquals(true, event.consent?.purposes?.get("analytics"))
    }

    @Test(expected = IllegalArgumentException::class)
    fun rejectsUnknownTopLevelField() {
        Event.parse(JSONObject(fixture("unknown_top_level.json")))
    }

    @Test
    fun roundTripsContractFields() {
        val original = Event.parse(JSONObject(fixture("android_custom.json")))
        val copy = Event.parse(original.toJson())
        assertEquals(original, copy)
        assertEquals(original.toJson().toString(), copy.toJson().toString())
    }

    @Test
    fun createsUuidV4WithUtcTimestamp() {
        val event = Event.create(
            eventName = "purchase",
            containerId = "acme-android",
            now = Instant.parse("2026-10-20T12:01:02.123Z"),
        )
        assertEquals("2026-10-20T12:01:02.123Z", event.timestamp)
        assertTrue(
            Regex("^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
                .matches(event.eventId)
        )
        event.validate(Instant.parse("2026-10-20T12:01:03Z"))
    }

    @Test
    fun rejectsTimestampOutsideTwentyFourHours() {
        val event = Event.parse(JSONObject(fixture("android_custom.json")))
        assertThrows(IllegalArgumentException::class.java) {
            event.validate(Instant.parse("2026-10-23T12:02:03Z"))
        }
    }

    @Test
    fun rejectsSensitivePropertiesAtAnyDepth() {
        val properties = JSONObject()
            .put("checkout", JSONObject().put("auth_token", "not-allowed"))
        val event = Event.create(
            eventName = "purchase",
            containerId = "acme-android",
            properties = properties,
        )
        assertThrows(IllegalArgumentException::class.java) {
            event.validate(Instant.parse(event.timestamp))
        }
    }

    @Test
    fun rejectsOversizedEvents() {
        val event = Event.create(
            eventName = "purchase",
            containerId = "acme-android",
            properties = JSONObject().put("payload", "x".repeat(40_000)),
        )
        val error = assertThrows(IllegalArgumentException::class.java) {
            event.validate(Instant.parse(event.timestamp))
        }
        assertTrue(error.message!!.contains("32 KiB"))
    }

    @Test
    fun rejectsInvalidConsentSource() {
        val document = JSONObject(fixture("android_custom.json"))
        document.getJSONObject("consent").put("source", "client")
        val event = Event.parse(document)
        assertThrows(IllegalArgumentException::class.java) {
            event.validate(Instant.parse("2026-10-20T12:02:03Z"))
        }
    }

    @Test
    fun rejectsInvalidIdentityFields() {
        val document = JSONObject(fixture("android_custom.json"))
        document.put("event_id", "not-a-uuid")
        document.put("event_name", "1 invalid name")
        document.put("container_id", "x")
        val event = Event.parse(document)
        assertThrows(IllegalArgumentException::class.java) {
            event.validate(Instant.parse("2026-10-20T12:02:03Z"))
        }
    }

    @Test
    fun reportsAllWithdrawnPurposes() {
        val consent = Consent(
            purposes = mapOf("analytics" to true, "marketing" to false),
            source = "host",
            provenance = "explicit",
        )
        assertEquals(setOf("analytics"), consent.grantedPurposes)
        assertNotNull(consent.toJson().getJSONObject("purposes"))
    }
}
