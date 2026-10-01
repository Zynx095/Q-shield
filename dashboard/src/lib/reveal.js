// Scroll reveal: page sections marked `data-reveal` fade and rise once, the first time they enter the viewport.
// The hidden start state applies only while <html> has the `reveal-ready` class this controller adds (see
// components.css), so without JavaScript, without IntersectionObserver or under reduced motion nothing is ever hidden.
// A revealed element carries data-revealed="<stagger step 0-3>"; the morph renderer keeps that attribute, so the
// 2-second refresh never replays an entrance.

const MAX_STEP = 3;            // stagger at most four deep (0, 60, 120, 180 ms)
const FALLBACK_MS = 1200;      // safety net: anything on or above the screen is shown by then, observer or not
const PENDING = "[data-reveal]:not([data-revealed])";

export function createRevealer({ doc = globalThis.document, win = globalThis.window } = {}) {
  const IO = win && win.IntersectionObserver;
  const reduce = win && win.matchMedia ? win.matchMedia("(prefers-reduced-motion: reduce)") : { matches: false };
  const animated = () => !!IO && !reduce.matches;
  let io = null;
  let fallback = 0;

  const mark = (el, step) => {
    if (!el.hasAttribute("data-revealed")) el.setAttribute("data-revealed", String(Math.min(step, MAX_STEP)));
  };

  function onEntries(entries) {
    let step = 0;
    for (const e of entries) {
      if (!e.isIntersecting) continue;
      mark(e.target, step++);
      io.unobserve(e.target);
    }
  }

  function sweep() {
    fallback = 0;
    const h = win.innerHeight || 0;
    for (const el of doc.querySelectorAll(PENDING)) {
      if (el.getBoundingClientRect().top < h) { mark(el, 0); if (io) io.unobserve(el); }
    }
  }

  const sync = () => doc.documentElement.classList.toggle("reveal-ready", animated());
  sync();
  if (reduce.addEventListener) reduce.addEventListener("change", () => { sync(); scan(); });

  /** After every render: start watching sections that have not been shown yet. */
  function scan() {
    const pending = doc.querySelectorAll(PENDING);
    if (!pending.length) return;
    if (!animated()) { for (const el of pending) mark(el, 0); return; }
    // threshold 0 (any part above the bottom 8% of the screen), so a section taller than the viewport still reveals
    if (!io) io = new IO(onEntries, { rootMargin: "0px 0px -8% 0px", threshold: 0 });
    for (const el of pending) io.observe(el);       // observing an element twice is a no-op
    if (!fallback) fallback = win.setTimeout(sweep, FALLBACK_MS);
  }

  /** A new page: forget what was shown so it gets its own entrance (hidden instantly, revealed by the next scan). */
  function reset() {
    if (io) { io.disconnect(); io = null; }
    if (fallback) { win.clearTimeout(fallback); fallback = 0; }
    if (!animated()) return;
    for (const el of doc.querySelectorAll("[data-revealed]")) el.removeAttribute("data-revealed");
  }

  return { scan, reset };
}
