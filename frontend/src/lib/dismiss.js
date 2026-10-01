// Close-on-outside for popup menus (the list, reader and attachment right-click
// menus): `<div use:dismiss={close}>`, or `use:dismiss={{ close, ignore: [btn] }}`
// when a toggle button opens the menu - a press on it is left to its own click
// handler, or the menu would close on pointerdown and reopen on click.
//
// A window "click" listener isn't enough, which is why menus used to hang
// around until you clicked the mail list: plenty of buttons stop their click
// from bubbling, and a click inside an email body lands in its iframe and never
// reaches this window at all. So this listens in the CAPTURE phase (it runs
// before any handler can stop the event) and to more than clicks: a right-click
// elsewhere, Escape, the mouse wheel (the menu would float over the wrong row),
// the window losing focus, and presses/Escape forwarded out of email iframes
// (see forwardFramePointer). Not "scroll": a background refresh re-anchoring
// the list fires those too, and would snap the menu shut mid-read.

export const FRAME_POINTER = "raplmail:frame-pointer";

/** Report pointer presses (and Escape) inside an email iframe's document to
 *  this window, so menus open in the app close when you click into the email. */
export function forwardFramePointer(doc) {
  const fire = () => window.dispatchEvent(new Event(FRAME_POINTER));
  try {
    doc.addEventListener("pointerdown", fire, true);
    doc.addEventListener("keydown", (e) => { if (e.key === "Escape") fire(); }, true);
  } catch {}
}

export function dismiss(node, arg) {
  let close, ignore;
  const set = (a) => {
    close = typeof a === "function" ? a : a?.close;
    ignore = typeof a === "function" ? [] : (a?.ignore || []);
  };
  set(arg);
  const shut = () => close?.();
  const outside = (e) => {
    if (node.contains(e.target) || ignore.some((el) => el?.contains?.(e.target))) return;
    shut();
  };
  const key = (e) => {
    if (e.key !== "Escape") return;
    // Escape closes the menu and nothing else (not the reader, not a search).
    e.stopPropagation();
    shut();
  };
  const opts = { capture: true, passive: true };
  window.addEventListener("pointerdown", outside, true);
  window.addEventListener("contextmenu", outside, true);
  window.addEventListener("keydown", key, true);
  window.addEventListener("wheel", outside, opts);
  window.addEventListener("blur", shut);
  window.addEventListener("resize", shut);
  window.addEventListener(FRAME_POINTER, shut);
  return {
    update(a) { set(a); },
    destroy() {
      window.removeEventListener("pointerdown", outside, true);
      window.removeEventListener("contextmenu", outside, true);
      window.removeEventListener("keydown", key, true);
      window.removeEventListener("wheel", outside, opts);
      window.removeEventListener("blur", shut);
      window.removeEventListener("resize", shut);
      window.removeEventListener(FRAME_POINTER, shut);
    },
  };
}
