package com.pytagmanager.sdk

import org.json.JSONArray
import org.json.JSONObject
import java.time.Instant
import java.time.ZoneOffset
import java.time.format.DateTimeFormatter
import java.util.UUID

data class EventSource(
    val platform: String = "android",
    val sdkName: String = "pytagmanager-android",
    val sdkVersion: String = "0.1.0",
    val appVersion: String? = null,
) {
    fun toJson(): JSONObject = JSONObject().apply {
        put("platform", platform)
        put("sdk_name", sdkName)
        put("sdk_version", sdkVersion)
        if (appVersion != null) put("app_version", appVersion)
    }
}

data class Consent(
    val purposes: Map<String, Boolean>,
    val source: String = "sdk",
    val provenance: String = "explicit",
    val updatedAt: String? = null,
) {
    fun toJson(): JSONObject = JSONObject().apply {
        put("purposes", JSONObject(purposes))
        put("source", source)
        put("provenance", provenance)
        if (updatedAt != null) put("updated_at", updatedAt)
    }

    val grantedPurposes: Set<String>
        get() = purposes.filterValues { it }.keys
}

data class Event(
    val schemaVersion: String = "1.0",
    val eventId: String,
    val eventName: String,
    val timestamp: String,
    val source: EventSource,
    val containerId: String,
    val consent: Consent? = null,
    val subjectId: String? = null,
    val configVersion: String? = null,
    val properties: JSONObject = JSONObject(),
) {
    fun toJson(): JSONObject = JSONObject().apply {
        put("schema_version", schemaVersion)
        put("event_id", eventId)
        put("event_name", eventName)
        put("timestamp", timestamp)
        put("source", source.toJson())
        put("container_id", containerId)
        if (consent != null) put("consent", consent.toJson())
        if (subjectId != null) put("subject", JSONObject().put("id", subjectId).put("type", "user"))
        if (configVersion != null) put("config_version", configVersion)
        put("properties", properties)
    }

    fun validate(now: Instant = Instant.now()) {
        require(schemaVersion == "1.0") { "unsupported schema_version" }
        require(EVENT_ID.matches(eventId)) { "event_id must be a lowercase UUIDv4" }
        require(NAME.matches(eventName)) { "event_name is invalid" }
        require(CONTAINER.matches(containerId)) { "container_id is invalid" }
        val parsed = Instant.parse(timestamp)
        require(Math.abs(now.epochSecond - parsed.epochSecond) <= 86_400) {
            "timestamp is outside the 24-hour window"
        }
        require(source.platform in setOf("web", "android", "ios", "server")) {
            "source.platform is invalid"
        }
        require(NAME.matches(source.sdkName)) { "source.sdk_name is invalid" }
        require(VERSION.matches(source.sdkVersion)) { "source.sdk_version is invalid" }
        consent?.let {
            require(it.purposes.isNotEmpty() && it.purposes.size <= 32) {
                "consent.purposes must contain 1...32 entries"
            }
            require(it.source in setOf("sdk", "host", "server", "unknown")) {
                "consent.source is invalid"
            }
            require(it.provenance in setOf("explicit", "default", "stored", "unknown")) {
                "consent.provenance is invalid"
            }
            it.updatedAt?.let { value -> Instant.parse(value) }
        }
        rejectSensitive(properties, "$")
        require(toJson().toString().toByteArray(Charsets.UTF_8).size <= 32_768) {
            "event exceeds 32 KiB"
        }
    }

    companion object {
        private val EVENT_ID = Regex("^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
        private val NAME = Regex("^[A-Za-z][A-Za-z0-9_.-]{0,63}$")
        private val CONTAINER = Regex("^[A-Za-z][A-Za-z0-9_-]{2,63}$")
        private val VERSION = Regex("^[0-9]+\\.[0-9]+\\.[0-9]+(?:[-+][A-Za-z0-9.-]+)?$")
        private val SENSITIVE = listOf(
            "password", "passwd", "secret", "token", "api_key", "apikey",
            "private_key", "credit_card", "card_number", "cvv", "ssn",
            "social_security", "authorization",
        )

        fun create(
            eventName: String,
            containerId: String,
            source: EventSource = EventSource(),
            consent: Consent? = null,
            subjectId: String? = null,
            configVersion: String? = null,
            properties: JSONObject = JSONObject(),
            now: Instant = Instant.now(),
        ): Event = Event(
            eventId = UUID.randomUUID().toString(),
            eventName = eventName,
            timestamp = DateTimeFormatter.ofPattern("yyyy-MM-dd'T'HH:mm:ss.SSS'Z'")
                .withZone(ZoneOffset.UTC).format(now),
            source = source,
            containerId = containerId,
            consent = consent,
            subjectId = subjectId,
            configVersion = configVersion,
            properties = properties,
        )

        fun parse(json: JSONObject): Event {
            val allowed = setOf(
                "schema_version", "event_id", "event_name", "timestamp", "source",
                "container_id", "consent", "subject", "correlation", "config_version",
                "properties",
            )
            val unknown = json.keys().asSequence().toSet() - allowed
            require(unknown.isEmpty()) { "unknown field(s): ${unknown.sorted()}" }
            val sourceJson = json.getJSONObject("source")
            val source = EventSource(
                platform = sourceJson.getString("platform"),
                sdkName = sourceJson.getString("sdk_name"),
                sdkVersion = sourceJson.getString("sdk_version"),
                appVersion = sourceJson.optString("app_version").ifBlank { null },
            )
            val consentJson = json.optJSONObject("consent")
            val consent = consentJson?.let {
                val purposes = mutableMapOf<String, Boolean>()
                val values = it.getJSONObject("purposes")
                for (key in values.keys()) purposes[key] = values.getBoolean(key)
                Consent(
                    purposes = purposes,
                    source = it.getString("source"),
                    provenance = it.getString("provenance"),
                    updatedAt = if (it.isNull("updated_at")) null
                        else it.optString("updated_at").ifBlank { null },
                )
            }
            return Event(
                schemaVersion = json.getString("schema_version"),
                eventId = json.getString("event_id"),
                eventName = json.getString("event_name"),
                timestamp = json.getString("timestamp"),
                source = source,
                containerId = json.getString("container_id"),
                consent = consent,
                subjectId = json.optJSONObject("subject")?.optString("id")?.ifBlank { null },
                configVersion = if (json.isNull("config_version")) null
                    else json.optString("config_version").ifBlank { null },
                properties = json.optJSONObject("properties") ?: JSONObject(),
            )
        }

        private fun rejectSensitive(value: Any?, path: String) {
            when (value) {
                is JSONObject -> for (key in value.keys()) {
                    val lowered = key.lowercase()
                    require(SENSITIVE.none { lowered.contains(it) }) {
                        "sensitive property is not allowed: $path.$key"
                    }
                    rejectSensitive(value.opt(key), "$path.$key")
                }
                is JSONArray -> for (index in 0 until value.length()) {
                    rejectSensitive(value.opt(index), "$path[$index]")
                }
            }
        }
    }
}
