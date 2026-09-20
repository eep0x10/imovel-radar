import { animate } from "./vendor/anime.esm.min.js";
const reduced = matchMedia("(prefers-reduced-motion: reduce)");
const active = new Set();
export function clearRadarMotion() {
  for (const animation of active) animation.revert();
  active.clear();
}
export function animateRadar(root) {
  if (reduced.matches) return;
  const cards = [...root.querySelectorAll(".property")];
  if (!cards.length) return;
  const animation = animate(cards, {
    opacity: [0.65, 1],
    duration: 180,
    ease: "outQuad",
    onComplete: (self) => {
      self.revert();
      active.delete(self);
    },
  });
  active.add(animation);
}
reduced.addEventListener("change", clearRadarMotion);
window.addEventListener("pagehide", clearRadarMotion);
