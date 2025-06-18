import { clsx, type ClassValue } from "clsx";
import * as Color from "color-bits";

import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
export const getRGBA = (
  cssColor: React.CSSProperties["color"],
  fallback: string = "rgba(180, 180, 180)",
): string => {
  if (typeof window === "undefined") return fallback;
  if (!cssColor) return fallback;

  try {
    // Handle CSS variables
    if (typeof cssColor === "string" && cssColor.startsWith("var(")) {
      const element = document.createElement("div");
      element.style.color = cssColor;
      document.body.appendChild(element);
      const computedColor = window.getComputedStyle(element).color;
      document.body.removeChild(element);
      return Color.formatRGBA(Color.parse(computedColor));
    }

    return Color.formatRGBA(Color.parse(cssColor));
  } catch (e) {
    console.error("Color parsing failed:", e);
    return fallback;
  }
};
export const colorWithOpacity = (color: string, opacity: number): string => {
  if (!color.startsWith("rgb")) return color;
  return Color.formatRGBA(Color.alpha(Color.parse(color), opacity));
};
