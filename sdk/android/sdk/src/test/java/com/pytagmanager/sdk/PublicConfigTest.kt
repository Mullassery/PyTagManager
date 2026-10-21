package com.pytagmanager.sdk

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertThrows
import org.junit.Assert.assertTrue
import org.junit.Test

class PublicConfigTest {
    private fun unsignedConfig(): JSONObject = JSONObject(
        """
        {
          "schema_version": "1.0",
          "kind": "pytagmanager.container",
          "container_id": "acme-android",
          "config_version": "2026-10-20T12:00:00Z",
          "revision_number": 7,
          "event_schema_version": "1.0",
          "events": [
            {"name": "purchase", "purposes": ["analytics"], "tag_ids": ["tag-1"]},
            {"name": "screen_view", "purposes": [], "tag_ids": []}
          ],
          "consent_defaults": {"analytics": false, "marketing": false}
        }
        """.trimIndent()
    )

    private fun signedConfig(): JSONObject {
        val document = unsignedConfig()
        val digest = ConfigVerifier.sha256(ConfigVerifier.canonicalJson(document))
        document.put(
            "integrity",
            JSONObject().put("algorithm", "sha256").put("digest", digest),
        )
        return document
    }

    @Test
    fun verifiesAndDecodesPublishedConfiguration() {
        val document = signedConfig()
        val expected = ConfigVerifier.sha256(ConfigVerifier.canonicalJson(unsignedConfig()))
        assertEquals(expected, ConfigVerifier.verifyIntegrity(document.toString().toByteArray()))

        val config = ConfigVerifier.decode(document.toString().toByteArray())
        assertEquals("acme-android", config.containerId)
        assertEquals(7, config.revisionNumber)
        assertEquals(listOf("analytics"), config.event("purchase")?.purposes)
        assertEquals(listOf("tag-1"), config.event("purchase")?.tagIds)
        assertEquals(false, config.consentDefaults["analytics"])
        assertTrue(config.raw.has("integrity"))
    }

    @Test
    fun rejectsTamperedConfiguration() {
        val document = signedConfig()
        document.getJSONArray("events").getJSONObject(0).put("purposes", listOf("marketing"))
        val error = assertThrows(ConfigException::class.java) {
            ConfigVerifier.verifyIntegrity(document.toString().toByteArray())
        }
        assertTrue(error.message!!.contains("digest"))
    }

    @Test
    fun rejectsMissingOrUnsupportedIntegrity() {
        assertThrows(ConfigException::class.java) {
            ConfigVerifier.verifyIntegrity(unsignedConfig().toString().toByteArray())
        }
        val unsupported = signedConfig()
        unsupported.getJSONObject("integrity").put("algorithm", "md5")
        assertThrows(ConfigException::class.java) {
            ConfigVerifier.verifyIntegrity(unsupported.toString().toByteArray())
        }
    }

    @Test
    fun rejectsUnsupportedDocumentKind() {
        val document = signedConfig().put("kind", "other.container")
        assertThrows(ConfigException::class.java) {
            ConfigVerifier.decode(document.toString().toByteArray())
        }
    }

    @Test
    fun canonicalJsonIsStableAcrossKeyOrder() {
        val first = JSONObject("""{"b":2,"a":{"d":4,"c":3}}""")
        val second = JSONObject("""{"a":{"c":3,"d":4},"b":2}""")
        assertEquals(ConfigVerifier.canonicalJson(first), ConfigVerifier.canonicalJson(second))
        assertEquals(
            ConfigVerifier.sha256(ConfigVerifier.canonicalJson(first)),
            ConfigVerifier.sha256(ConfigVerifier.canonicalJson(second)),
        )
    }
}
