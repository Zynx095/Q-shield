// Scroll-reveal controller (src/lib/reveal.js), run against a fake document, window and IntersectionObserver.
import test from "node:test";
import assert from "node:assert/strict";

import { createRevealer } from "../src/lib/reveal.js";

function fakeEl(top) {
  const attrs = new Map([["data-reveal", ""]]);
  return {
    hasAttribute: (n) => attrs.has(n),
    getAttribute: (n) => (attrs.has(n) ? attrs.get(n) : null),
    setAttribute: (n, v) => attrs.set(n, String(v)),
    removeAttribute: (n) => attrs.delete(n),
    getBoundingClientRect: () => ({ top }),
  };
}

function fakeDoc(els) {
  const cls = new Set();
  return {
    cls,
    documentElement: { classList: { toggle: (c, on) => (on ? cls.add(c) : cls.delete(c)) } },
    querySelectorAll(sel) {
      if (sel === "[data-reveal]:not([data-revealed])") return els.filter((e) => e.hasAttribute("data-reveal") && !e.hasAttribute("data-revealed"));
      if (sel === "[data-revealed]") return els.filter((e) => e.hasAttribute("data-revealed"));
      throw new Error(`unexpected selector ${sel}`);
    },
  };
}

function fakeWin({ io = true, reduced = false } = {}) {
  const timers = [], observers = [];
  class IO {
    constructor(cb, opts) { this.cb = cb; this.opts = opts; this.watched = new Set(); observers.push(this); }
    observe(el) { this.watched.add(el); }
    unobserve(el) { this.watched.delete(el); }
    disconnect() { this.watched.clear(); this.dead = true; }
    fire(els) { this.cb(els.map((target) => ({ target, isIntersecting: true }))); }
  }
  return {
    innerHeight: 800, timers, observers,
    IntersectionObserver: io ? IO : undefined,
    matchMedia: () => ({ matches: reduced, addEventListener() {} }),
    setTimeout: (fn, ms) => { timers.push({ fn, ms }); return timers.length; },
    clearTimeout: (id) => { if (timers[id - 1]) timers[id - 1].cleared = true; },
  };
}

const steps = (els) => els.map((e) => e.getAttribute("data-revealed"));

test("reveal: nothing is ever hidden without IntersectionObserver or under reduced motion", () => {
  for (const opts of [{ io: false }, { reduced: true }]) {
    const els = [fakeEl(0), fakeEl(2000)];
    const doc = fakeDoc(els), win = fakeWin(opts);
    const r = createRevealer({ doc, win });
    assert.ok(!doc.cls.has("reveal-ready"), "the hidden start state is never enabled");
    r.scan();
    assert.deepEqual(steps(els), ["0", "0"], "every section is shown at once, off-screen ones too");
    assert.equal(win.observers.length, 0);
  }
});

test("reveal: sections entering together are staggered at most four deep, and each is revealed once", () => {
  const els = [0, 100, 200, 300, 400].map(fakeEl);
  const doc = fakeDoc(els), win = fakeWin();
  const r = createRevealer({ doc, win });
  assert.ok(doc.cls.has("reveal-ready"));
  r.scan();
  const [io] = win.observers;
  assert.equal(io.opts.threshold, 0, "a section taller than the screen must still be able to reveal");
  assert.equal(io.opts.rootMargin, "0px 0px -8% 0px");
  assert.equal(io.watched.size, 5);
  assert.deepEqual(steps(els), [null, null, null, null, null], "nothing is shown before it is on screen");
  io.fire(els);
  assert.deepEqual(steps(els), ["0", "1", "2", "3", "3"]);
  assert.equal(io.watched.size, 0, "revealed sections are no longer observed");
  r.scan();                                           // the 2-second refresh
  assert.equal(io.watched.size, 0, "a refresh never re-arms a revealed section");
  assert.equal(win.observers.length, 1);
});

test("reveal: the safety net shows anything on or above the screen even if the observer never fires", () => {
  const els = [fakeEl(-300), fakeEl(500), fakeEl(1600)];
  const doc = fakeDoc(els), win = fakeWin();
  createRevealer({ doc, win }).scan();
  assert.equal(win.timers.length, 1);
  assert.equal(win.timers[0].ms, 1200);
  win.timers[0].fn();
  assert.deepEqual(steps(els), ["0", "0", null], "below the fold stays for the observer");
  assert.ok(win.observers[0].watched.has(els[2]));
});

test("reveal: a new page forgets what was shown, so it gets its own entrance", () => {
  const els = [fakeEl(0), fakeEl(100)];
  const doc = fakeDoc(els), win = fakeWin();
  const r = createRevealer({ doc, win });
  r.scan();
  win.observers[0].fire(els);
  assert.deepEqual(steps(els), ["0", "1"]);
  r.reset();
  assert.deepEqual(steps(els), [null, null]);
  assert.ok(win.observers[0].dead && win.timers[0].cleared);
  r.scan();
  assert.equal(win.observers.length, 2, "a fresh observer for the new page");
  assert.equal(win.observers[1].watched.size, 2);
});
