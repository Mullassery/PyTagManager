package com.pytagmanager.sdk

import org.json.JSONArray
import org.json.JSONObject
import java.security.MessageDigest

data class PublicConfigEvent(
    val name: String,
    val purposes: List<String>,
    val tagIds: List<String>,
)

data class PublicConfig(
    val schemaVersion: String,
    val kind: String,
    val containerId: String,
    val configVersion: String,
    val revisionNumber: Int,
    val eventSchemaVersion: String,
    val events: List<PublicConfigEvent>,
    val consentDefaults: Map<String, Boolean>,
    val raw: JSONObject,
) {
    fun event(name: String): PublicConfigEvent? = events.firstOrNull { it.name == name }
}

class ConfigException(message: String) : Exception(message)

object ConfigVerifier {
    fun canonicalJson(value: Any?): String = when (value) {
        null, JSONObject.NULL -> "null"
        is JSONObject -> value.keys().asSequence().sorted().joinToString(
            prefix = "{", postfix = "}", separator = ","
        ) { key -> quote(key) + ":" + canonicalJson(value.opt(key)) }
        is JSONArray -> (0 until value.length()).joinToString(
            prefix = "[", postfix = "]", separator = ","
        ) { index -> canonicalJson(value.opt(index)) }
        is String -> quote(value)
        is Boolean -> value.toString()
        is Number -> value.toString()
        else -> throw ConfigException("unsupported canonical JSON value")
    }

    private fun quote(value: String): String = buildString {
        append('"')
        for (character in value) {
            when (character) {
                '"' -> append("\\\"")
                '\\' -> append("\\\\")
                '\b' -> append("\\b")
                '\u000C' -> append("\\f")
                '\n' -> append("\\n")
                '\r' -> append("\\r")
                '\t' -> append("\\t")
                else -> if (character < ' ') append("\\u%04x".format(character.code))
                else append(character)
            }
        }
        append('"')
    }

    fun sha256(value: String): String = MessageDigest.getInstance("SHA-256")
        .digest(value.toByteArray(Charsets.UTF_8))
        .joinToString("") { "%02x".format(it) }

    fun verifyIntegrity(data: ByteArray): String {
        val document = try {
            JSONObject(data.toString(Charsets.UTF_8))
        } catch (error: Exception) {
            throw ConfigException("config must be a JSON object")
        }
        val integrity = document.optJSONObject("integrity")
            ?: throw ConfigException("config is missing integrity metadata")
        if (integrity.optString("algorithm") != "sha256") {
            throw ConfigException("unsupported integrity algorithm")
        }
        val expected = integrity.optString("digest")
        val unsigned = JSONObject(document.toString())
        unsigned.remove("integrity")
        val digest = sha256(canonicalJson(unsigned))
        if (digest != expected) throw ConfigException("config integrity digest does not match")
        return digest
    }

    fun decode(data: ByteArray): PublicConfig {
        val document = JSONObject(data.toString(Charsets.UTF_8))
        if (document.optString("schema_version") != "1.0" ||
            document.optString("kind") != "pytagmanager.container"
        ) {
            throw ConfigException("unsupported published configuration")
        }
        val events = mutableListOf<PublicConfigEvent>()
        val eventArray = document.optJSONArray("events") ?: JSONArray()
        for (index in 0 until eventArray.length()) {
            val item = eventArray.getJSONObject(index)
            events += PublicConfigEvent(
                name = item.getString("name"),
                purposes = item.optJSONArray("purposes")?.toStringList() ?: emptyList(),
                tagIds = item.optJSONArray("tag_ids")?.toStringList() ?: emptyList(),
            )
        }
        val defaults = mutableMapOf<String, Boolean>()
        document.optJSONObject("consent_defaults")?.let { values ->
            for (key in values.keys()) defaults[key] = values.getBoolean(key)
        }
        return PublicConfig(
            schemaVersion = document.getString("schema_version"),
            kind = document.getString("kind"),
            containerId = document.getString("container_id"),
            configVersion = document.getString("config_version"),
            revisionNumber = document.optInt("revision_number"),
            eventSchemaVersion = document.optString("event_schema_version"),
            events = events,
            consentDefaults = defaults,
            raw = document,
        )
    }

    private fun JSONArray.toStringList(): List<String> =
        (0 until length()).mapNotNull { index -> optString(index).ifBlank { null } }
}
