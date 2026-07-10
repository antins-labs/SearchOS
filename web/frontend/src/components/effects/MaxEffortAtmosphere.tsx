"use client";

import { useEffect, type CSSProperties } from "react";

const PULSES = [
  { x: 7, delay: -0.4, duration: 5.8, height: 72 },
  { x: 14, delay: -3.2, duration: 7.1, height: 42 },
  { x: 23, delay: -1.7, duration: 6.4, height: 58 },
  { x: 34, delay: -5.1, duration: 8.2, height: 36 },
  { x: 46, delay: -2.4, duration: 6.8, height: 80 },
  { x: 58, delay: -6.3, duration: 8.6, height: 44 },
  { x: 69, delay: -0.9, duration: 6.1, height: 64 },
  { x: 79, delay: -4.6, duration: 7.7, height: 38 },
  { x: 88, delay: -2.8, duration: 6.9, height: 54 },
  { x: 95, delay: -5.7, duration: 8.4, height: 70 },
];

export default function MaxEffortAtmosphere({ active }: { active: boolean }) {
  useEffect(() => {
    if (active) document.documentElement.dataset.effort = "max";
    else delete document.documentElement.dataset.effort;
    return () => { delete document.documentElement.dataset.effort; };
  }, [active]);

  if (!active) return null;

  return (
    <div className="max-effort-atmosphere" aria-hidden="true">
      <div className="max-effort-frame" />
      <div className="max-effort-visor" />
      <div className="max-effort-ripples">
        <span />
        <span />
        <span />
      </div>
      <div className="max-effort-scan" />
      <div className="max-effort-rail max-effort-rail-left" />
      <div className="max-effort-rail max-effort-rail-right" />
      <div className="max-effort-telemetry max-effort-telemetry-left">
        {[18, 31, 24, 42, 28].map((width) => <span key={width} style={{ width }} />)}
      </div>
      <div className="max-effort-telemetry max-effort-telemetry-right">
        {[36, 22, 44, 27, 34].map((width) => <span key={width} style={{ width }} />)}
      </div>
      <div className="max-effort-console">
        <span />
        <span />
        <span />
      </div>
      <div className="max-effort-completion-flash" />
      <span className="max-effort-corner max-effort-corner-tl" />
      <span className="max-effort-corner max-effort-corner-tr" />
      <span className="max-effort-corner max-effort-corner-bl" />
      <span className="max-effort-corner max-effort-corner-br" />
      {PULSES.map((pulse) => (
        <span
          key={pulse.x}
          className="max-effort-pulse"
          style={{
            "--pulse-x": `${pulse.x}%`,
            "--pulse-delay": `${pulse.delay}s`,
            "--pulse-duration": `${pulse.duration}s`,
            "--pulse-height": `${pulse.height}px`,
          } as CSSProperties}
        />
      ))}
    </div>
  );
}
