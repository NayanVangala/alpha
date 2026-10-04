// run: node --test tests/frontend/gazeKit.test.ts
import { test } from "node:test"
import assert from "node:assert/strict"
import { BiteLink } from "../../src/frontend/src/lib/gazeKit.ts"

test("a rising count picks the lit tile; no rise, brake, or a stale tile does not", () => {
  const b = new BiteLink(800)
  assert.equal(b.poll(3, false, 0), null)          // first poll only learns the count
  b.seeLit("Home", 100)
  assert.equal(b.poll(3, false, 200), null)        // no rise
  assert.equal(b.poll(4, false, 300), "Home")      // bite
  assert.equal(b.poll(4, false, 450), null)        // same count again: no double pick
  b.seeLit("Stop", 500)
  assert.equal(b.poll(5, true, 600), null)         // braking: the bite is not a pick
  assert.equal(b.poll(6, false, 2000), null)       // tile lit 1.5 s ago: too stale
})

test("the tile lit just before the gaze drifted still counts", () => {
  const b = new BiteLink(800)
  b.poll(1, false, 0)
  b.seeLit("Search", 1000)                          // then the clench shakes the face: nothing lit after
  assert.equal(b.poll(2, false, 1500), "Search")
})

test("a failed poll keeps the count, so a bite during the outage is still seen; a server restart resets", () => {
  const b = new BiteLink(800)
  b.poll(5, false, 0)
  b.seeLit("Read", 100)
  assert.equal(b.poll(-1, false, 200), null)
  assert.equal(b.poll(6, false, 300), "Read")
  assert.equal(b.poll(0, false, 400), null)         // counts restarted
  b.seeLit("Read", 450)
  assert.equal(b.poll(1, false, 500), "Read")
})
