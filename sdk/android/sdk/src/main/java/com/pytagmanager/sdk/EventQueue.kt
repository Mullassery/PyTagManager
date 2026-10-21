package com.pytagmanager.sdk

import org.json.JSONArray
import java.io.File

class EventQueue(
    private val directory: File,
    private val maxEvents: Int = 1_000,
) {
    private val file = File(directory, "events.json")
    private val lock = Any()

    fun load(): List<Event> = synchronized(lock) { loadLocked() }

    fun enqueue(event: Event): Int = synchronized(lock) {
        val events = loadLocked().toMutableList()
        events += event
        if (events.size > maxEvents) events.subList(0, events.size - maxEvents).clear()
        saveLocked(events)
        events.size
    }

    fun remove(ids: Set<String>) = synchronized(lock) {
        val events = loadLocked().filterNot { it.eventId in ids }
        saveLocked(events)
    }

    fun removeIf(predicate: (Event) -> Boolean) = synchronized(lock) {
        val events = loadLocked().filterNot(predicate)
        saveLocked(events)
    }

    fun count(): Int = synchronized(lock) { loadLocked().size }

    private fun loadLocked(): List<Event> {
        if (!file.isFile) return emptyList()
        return try {
            val array = JSONArray(file.readText(Charsets.UTF_8))
            (0 until array.length()).map { Event.parse(array.getJSONObject(it)) }
        } catch (_: Exception) {
            emptyList()
        }
    }

    private fun saveLocked(events: List<Event>) {
        directory.mkdirs()
        val array = JSONArray()
        events.forEach { array.put(it.toJson()) }
        val temporary = File(directory, "events.json.tmp")
        temporary.writeText(array.toString(), Charsets.UTF_8)
        if (!temporary.renameTo(file)) {
            file.writeText(array.toString(), Charsets.UTF_8)
            temporary.delete()
        }
    }
}
