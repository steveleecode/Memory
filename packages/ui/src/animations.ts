import { gsap } from "gsap";
import type { RefObject } from "react";
import { useLayoutEffect } from "react";

const DURATION = {
  quick: 0.16,
  panel: 0.24,
  stagger: 0.28,
};

export function prefersReducedMotion() {
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

export function pressElement(target: Element) {
  if (prefersReducedMotion()) return;
  gsap.fromTo(
    target,
    { scale: 0.985 },
    { scale: 1, duration: DURATION.quick, ease: "power2.out", overwrite: true },
  );
}

export function useEntranceMotion<T extends HTMLElement>(
  ref: RefObject<T | null>,
  variant: "panel" | "list" = "panel",
  dependencies: readonly unknown[] = [],
) {
  useLayoutEffect(() => {
    const element = ref.current;
    if (!element || prefersReducedMotion()) {
      return;
    }
    const context = gsap.context(() => {
      if (variant === "list") {
        gsap.fromTo(
          element.querySelectorAll("[data-animate-item]"),
          { autoAlpha: 0, y: 10 },
          {
            autoAlpha: 1,
            y: 0,
            clearProps: "transform,opacity,visibility",
            duration: DURATION.stagger,
            ease: "power2.out",
            stagger: 0.035,
          },
        );
        return;
      }
      gsap.fromTo(
        element,
        { autoAlpha: 0, y: 14, scale: 0.992 },
        {
          autoAlpha: 1,
          y: 0,
          scale: 1,
          clearProps: "transform,opacity,visibility",
          duration: DURATION.panel,
          ease: "power3.out",
        },
      );
    }, element);
    return () => {
      context.revert();
    };
    // The callers provide stable animation reset keys; including the ref and variant would
    // restart entrance motion for unrelated renders.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, dependencies);
}
