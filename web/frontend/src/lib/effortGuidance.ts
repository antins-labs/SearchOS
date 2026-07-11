import type { EffortLevel } from "./types";

export const EFFORT_GUIDANCE: Record<EffortLevel, { title: string; summary: string }> = {
  low: {
    title: "Simple",
    summary: "Quick facts, narrow checks, and small lists.",
  },
  medium: {
    title: "Standard",
    summary: "Comparisons, short enumerations, and everyday research.",
  },
  high: {
    title: "Complex",
    summary: "Multi-hop questions, broad coverage, and harder sources.",
  },
  max: {
    title: "Exhaustive",
    summary: "Large tables, difficult sources, and recall-first deep research.",
  },
};
