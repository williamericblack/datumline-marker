/* The Evil Guy's Guide to History: the judging panel. All four are original drawings made
 * for TIDES (no existing characters, consoles or mascots). judge(id) returns avatar markup.
 * Mr. ASCII's text portrait is a placeholder until it is regenerated from William's photo.
 */
(function () {
  "use strict";
  const ASCII = [
    "   .-''''-.   ",
    "  /  .--.  \\  ",
    " |  ( oo )  | ",
    " |   '--'   | ",
    "  \\  \\__/  /  ",
    "   '-.__.-'   ",
    "  .-'|  |'-.  ",
    " /   |  |   \\ ",
    "|  [EVIL.EXE]|",
  ].join("\n");
  const ART = {
    ascii: `<pre class="ascii" aria-hidden="true">${ASCII.replace(/&/g, "&amp;").replace(/</g, "&lt;")}</pre>`,
    eyes: `<svg viewBox="0 0 100 100" aria-hidden="true"><defs><filter id="glow" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="4"/></filter></defs>
      <rect width="100" height="100" rx="14" fill="#07080b"/>
      <g fill="#ffd84a"><ellipse cx="32" cy="50" rx="13" ry="7" filter="url(#glow)" opacity=".9"/><ellipse cx="68" cy="50" rx="13" ry="7" filter="url(#glow)" opacity=".9"/>
      <path d="M20 50 Q32 40 44 50 Q32 56 20 50Z"/><path d="M56 50 Q68 40 80 50 Q68 56 56 50Z"/></g>
      <g fill="#07080b"><ellipse cx="32" cy="50" rx="2.2" ry="5"/><ellipse cx="68" cy="50" rx="2.2" ry="5"/></g></svg>`,
    squirrel: `<svg viewBox="0 0 100 100" aria-hidden="true"><rect width="100" height="100" rx="14" fill="#2b1d12"/>
      <g fill="#c8803f"><path d="M58 86 C96 84 100 40 80 20 C66 8 48 18 56 32 C64 44 82 52 66 74 Z"/>
      <ellipse cx="44" cy="68" rx="17" ry="19"/><circle cx="37" cy="42" r="13"/><path d="M39 31 L46 16 L49 33 Z"/>
      <ellipse cx="33" cy="88" rx="9" ry="4"/><ellipse cx="51" cy="88" rx="9" ry="4"/></g>
      <circle cx="32" cy="40" r="2.4" fill="#2b1d12"/><circle cx="26" cy="46" r="1.6" fill="#2b1d12"/>
      <g fill="#7a4a1f"><ellipse cx="30" cy="63" rx="6" ry="7"/></g><path d="M24 58 Q30 53 36 58Z" fill="#4a2c12"/></svg>`,
    handheld: `<svg viewBox="0 0 100 100" aria-hidden="true"><rect width="100" height="100" rx="14" fill="#1b1430"/>
      <rect x="8" y="26" width="84" height="50" rx="14" fill="#8c6fe0"/>
      <rect x="28" y="32" width="44" height="34" rx="4" fill="#0f1a24"/>
      <g fill="#7ef0c8"><rect x="38" y="42" width="5" height="7" rx="1"/><rect x="57" y="42" width="5" height="7" rx="1"/></g>
      <path d="M40 56 Q50 62 60 56" stroke="#7ef0c8" stroke-width="2.5" fill="none" stroke-linecap="round"/>
      <g fill="#2a1f4d"><circle cx="17" cy="44" r="4"/><circle cx="17" cy="58" r="4"/><circle cx="83" cy="44" r="4"/><circle cx="83" cy="58" r="4"/></g></svg>`,
  };
  window.TIDES_JUDGES = { art: id => `<span class="judge judge-${id}">${ART[id] || ""}</span>` };
})();
