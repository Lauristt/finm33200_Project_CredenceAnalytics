"use client";

import { useEffect, useState, useRef } from "react";
import { motion } from "framer-motion";
import { getBandColor, getVerdict, type Claim } from "@/lib/types";

interface SummaryBarProps {
  claims: Claim[];
}

function easeOut(t: number): number {
  return 1 - (1 - t) * (1 - t);
}

export function SummaryBar({ claims }: SummaryBarProps) {
  const overall = Math.round(
    claims.reduce((s, c) => s + c.confidence, 0) / claims.length
  );

  const bands = [
    { color: "#2F7D5B", count: claims.filter((c) => c.confidence >= 80).length },
    { color: "#B8923A", count: claims.filter((c) => c.confidence >= 60 && c.confidence < 80).length },
    { color: "#C2602E", count: claims.filter((c) => c.confidence >= 40 && c.confidence < 60).length },
    { color: "#A4332B", count: claims.filter((c) => c.confidence < 40).length },
  ].filter((b) => b.count > 0);

  const total = claims.length;

  /* Count-up animation */
  const [displayScore, setDisplayScore] = useState(0);
  const raf = useRef<number | null>(null);
  useEffect(() => {
    const start = performance.now();
    const duration = 800;
    const animate = (now: number) => {
      const elapsed = Math.min((now - start) / duration, 1);
      setDisplayScore(Math.round(easeOut(elapsed) * overall));
      if (elapsed < 1) raf.current = requestAnimationFrame(animate);
    };
    raf.current = requestAnimationFrame(animate);
    return () => { if (raf.current) cancelAnimationFrame(raf.current); };
  }, [overall]);

  const verdict = getVerdict(overall);
  const overallColor = getBandColor(
    overall >= 80 ? "green" : overall >= 60 ? "amber" : overall >= 40 ? "orange" : "red"
  );

  return (
    <div
      className="rounded-lg bg-white flex items-center gap-5 px-6"
      style={{ border: "1px solid var(--border)", height: 64 }}
    >
      {/* Overall score */}
      <div
        className="mono flex-shrink-0"
        style={{ fontSize: 36, lineHeight: 1, color: overallColor, fontWeight: 500 }}
        aria-label={`Overall confidence: ${overall}%`}
      >
        {displayScore}
        <span style={{ fontSize: 18, marginLeft: 2 }}>%</span>
      </div>

      {/* Stacked bar */}
      <div className="flex-1 flex flex-col gap-1.5">
        <div
          className="flex rounded-full overflow-hidden"
          style={{ height: 4, background: "#EAEAE5" }}
          role="img"
          aria-label="Confidence distribution by band"
        >
          {bands.map((band, i) => (
            <motion.div
              key={band.color}
              initial={{ width: 0 }}
              animate={{ width: `${(band.count / total) * 100}%` }}
              transition={{ duration: 0.4, delay: i * 0.08, ease: "easeOut" }}
              style={{ background: band.color, height: "100%" }}
            />
          ))}
        </div>
        <div className="flex gap-4">
          {[
            { color: "#2F7D5B", label: "High confidence" },
            { color: "#B8923A", label: "Moderate" },
            { color: "#C2602E", label: "Low" },
            { color: "#A4332B", label: "Disputed" },
          ].map(({ color, label }) => {
            const c = claims.filter((cl) => {
              if (color === "#2F7D5B") return cl.confidence >= 80;
              if (color === "#B8923A") return cl.confidence >= 60 && cl.confidence < 80;
              if (color === "#C2602E") return cl.confidence >= 40 && cl.confidence < 60;
              return cl.confidence < 40;
            }).length;
            if (c === 0) return null;
            return (
              <span key={color} className="flex items-center gap-1" style={{ fontSize: 11, color: "#6b7280" }}>
                <span style={{ width: 6, height: 6, borderRadius: "50%", background: color, display: "inline-block" }} />
                <span className="mono">{c}</span> {label}
              </span>
            );
          })}
        </div>
      </div>

      {/* Verdict */}
      <div
        className="flex-shrink-0 label-caps"
        style={{ color: "#6b7280", textAlign: "right" }}
      >
        {verdict}
      </div>
    </div>
  );
}
