package com.pytagmanager.sdk

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import java.io.File
import java.time.Instant

class EventQueueTest {
    @get:Rule
    val folder = TemporaryFolder()

    private fun event(name: String, now: Instant = Instant.now()): Event =
        Event.create(eventName = name, containerId = "acme-android", now = now)

    @Test
    fun persistsAcrossInstances() {
        val directory = folder.newFolder("queue")
        val first = EventQueue(directory)
        first.enqueue(event("screen_view"))
        first.enqueue(event("purchase"))

        val reloaded = EventQueue(directory)
        assertEquals(2, reloaded.count())
        assertEquals(listOf("screen_view", "purchase"), reloaded.load().map { it.eventName })
    }

    @Test
    fun evictsOldestEventsAtCapacity() {
        val queue = EventQueue(folder.newFolder("queue"), maxEvents = 2)
        queue.enqueue(event("one"))
        queue.enqueue(event("two"))
        queue.enqueue(event("three"))

        assertEquals(2, queue.count())
        assertEquals(listOf("two", "three"), queue.load().map { it.eventName })
    }

    @Test
    fun removesByEventIdAndPredicate() {
        val queue = EventQueue(folder.newFolder("queue"))
        val keep = event("keep")
        val drop = event("drop")
        queue.enqueue(keep)
        queue.enqueue(drop)

        queue.remove(setOf(drop.eventId))
        assertEquals(listOf("keep"), queue.load().map { it.eventName })

        queue.removeIf { it.eventName == "keep" }
        assertEquals(0, queue.count())
    }

    @Test
    fun treatsCorruptedStorageAsEmptyQueue() {
        val directory = folder.newFolder("queue")
        File(directory, "events.json").writeText("{not-json")
        val queue = EventQueue(directory)
        assertEquals(0, queue.count())
        queue.enqueue(event("recovered"))
        assertEquals(1, queue.count())
        assertTrue(File(directory, "events.json").isFile)
    }
}
