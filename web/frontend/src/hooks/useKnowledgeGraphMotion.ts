"use client";

import { useLayoutEffect, useRef, type RefObject } from "react";
import type { KnowledgeGraphLayout } from "@/lib/knowledgeGraph";

type Pose = { x: number; y: number; opacity: number };

export function graphCurve(a: { x: number; y: number }, b: { x: number; y: number }): string {
  return `M ${a.x} ${a.y} L ${b.x} ${b.y}`;
}

/** Interpolate SVG attributes directly: no React tree updates on animation frames. */
export default function useKnowledgeGraphMotion(svg: RefObject<SVGSVGElement | null>, layout: KnowledgeGraphLayout) {
  const current = useRef(new Map<string, Pose>());
  useLayoutEffect(() => {
    const element = svg.current;
    if (!element) return;
    const groups = new Map(Array.from(element.querySelectorAll<SVGGElement>("[data-graph-node]"))
      .map((node) => [node.dataset.graphNode!, node]));
    const paths = Array.from(element.querySelectorAll<SVGPathElement>("[data-graph-edge]"));
    const targets = new Map(layout.nodes.map((node) => [node.id, {
      x: node.x, y: node.y, opacity: node.hidden ? 0 : 1,
    }]));
    const starts = new Map(layout.nodes.map((node) => [node.id, current.current.get(node.id) ?? targets.get(node.id)!]));
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const duration = current.current.size && !reduced ? 380 : 0;
    const began = performance.now();
    let frame = 0;
    const paint = (now: number) => {
      const fraction = duration ? Math.min(1, (now - began) / duration) : 1;
      const t = 1 - Math.pow(1 - fraction, 3);
      for (const node of layout.nodes) {
        const from = starts.get(node.id)!;
        const to = targets.get(node.id)!;
        const pose = { x: from.x + (to.x - from.x) * t, y: from.y + (to.y - from.y) * t,
          opacity: from.opacity + (to.opacity - from.opacity) * t };
        current.current.set(node.id, pose);
        const group = groups.get(node.id);
        const zoom = 0.94 + pose.opacity * 0.06;
        group?.setAttribute("transform", `translate(${pose.x - node.width / 2} ${pose.y - node.height / 2}) translate(${node.width / 2} ${node.height / 2}) scale(${zoom}) translate(${-node.width / 2} ${-node.height / 2})`);
        if (group) group.style.opacity = String(pose.opacity);
      }
      for (const path of paths) {
        const source = current.current.get(path.dataset.graphSource!);
        const target = current.current.get(path.dataset.graphTarget!);
        if (source && target) path.setAttribute("d", graphCurve(source, target));
      }
      if (fraction < 1) frame = requestAnimationFrame(paint);
      else current.current = targets;
    };
    paint(began);
    return () => cancelAnimationFrame(frame);
  }, [layout, svg]);
}
