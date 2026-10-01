// Minimal DOM morphing: re-rendering a view patches the live DOM in place instead of replacing it.
// Keeping the same nodes is what preserves keyboard focus and scroll position across the 2-second refresh, and
// what lets CSS transitions animate real changes (a trust score moving, a recovery step completing).
// Children with `data-key` are matched by key; others by position and tag.

const keyOf = (n) => (n.nodeType === 1 ? n.getAttribute("data-key") : null);
const sameKind = (a, b) => a.nodeType === b.nodeType && (a.nodeType !== 1 || a.nodeName === b.nodeName);
// Attributes that imperative code owns and templates never set: kept, or every refresh would undo them.
// data-revealed: the scroll-reveal controller's "already shown" marker (lib/reveal.js).
const OWNED = new Set(["data-revealed"]);

function syncAttributes(from, to) {
  for (const { name, value } of Array.from(to.attributes)) {
    if (from.getAttribute(name) !== value) from.setAttribute(name, value);
  }
  for (const { name } of Array.from(from.attributes)) {
    if (!to.hasAttribute(name) && !OWNED.has(name)) from.removeAttribute(name);
  }
  // Form state lives in properties, not attributes; never clobber what the person is typing.
  if ((from.nodeName === "INPUT" || from.nodeName === "TEXTAREA") && from !== document.activeElement) {
    const v = to.getAttribute("value");
    if (v !== null && from.value !== v) from.value = v;
  }
}

function patch(from, to) {
  if (from.nodeType === 3 || from.nodeType === 8) {
    if (from.nodeValue !== to.nodeValue) from.nodeValue = to.nodeValue;
    return;
  }
  syncAttributes(from, to);
  if (from.hasAttribute("data-morph-skip")) return;      // subtree owned by imperative code
  morphChildren(from, to);
}

export function morphChildren(parent, next) {
  const newKids = Array.from(next.childNodes);
  const keyed = new Map();
  for (const n of Array.from(parent.childNodes)) {
    const k = keyOf(n);
    if (k !== null) keyed.set(k, n);
  }
  const used = new Set();
  for (let i = 0; i < newKids.length; i++) {
    const nn = newKids[i];
    const cur = parent.childNodes[i] || null;
    const k = keyOf(nn);
    let match = null;
    if (k !== null) {
      const m = keyed.get(k);
      if (m && !used.has(m) && sameKind(m, nn)) match = m;
    } else if (cur && !used.has(cur) && keyOf(cur) === null && sameKind(cur, nn)) {
      match = cur;
    }
    if (match) {
      used.add(match);
      if (match !== cur) parent.insertBefore(match, cur);
      patch(match, nn);
    } else {
      parent.insertBefore(nn, cur);
      used.add(nn);
    }
  }
  while (parent.childNodes.length > newKids.length) parent.removeChild(parent.lastChild);
}

/** Render a Safe HTML fragment into `container`, morphing what is already there. */
export function render(container, safe) {
  const tpl = document.createElement("template");
  tpl.innerHTML = String(safe);
  morphChildren(container, tpl.content);
}
