"use client";

import { useState } from "react";
import { ChevronRight } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { getBand, getBandColor, type Claim, type EvidenceStance } from "@/lib/types";
import { CredibilityDots } from "./CredibilityDots";

interface ClaimCardProps {
  claim: Claim;
  highlighted?: boolean;
}

function stanceBarColor(stance: EvidenceStance): string {
  if (stance === "supporting") return "#2F7D5B";
  if (stance === "contradicting") return "#A4332B";
  return "#9ca3af";
}

export function ClaimCard({ claim, highlighted }: ClaimCardProps) {
  const band = getBand(claim.confidence);
  const color = getBandColor(band);
  const defaultExpanded = claim.confidence < 70;
  const [expanded, setExpanded] = useState(defaultExpanded);
  const [readMoreMap, setReadMoreMap] = useState<Record<string, boolean>>({});

  const bgOpacity = "14";
  const chipBg = color + bgOpacity;
  const chipBorder = color + "33";

  const evidenceSummary = [
    claim.supporting > 0 && `${claim.supporting} supporting`,
    claim.contradicting > 0 && `${claim.contradicting} contradicting`,
    claim.neutral > 0 && `${claim.neutral} context`,
  ]
    .filter(Boolean)
    .join(" · ");

  return (
    <div
      className="rounded-lg bg-white transition-colors"
      style={{
        border: `1px solid ${highlighted ? "#D8D8D2" : "var(--border)"}`,
      }}
      onMouseEnter={(e) => {
        (e.currentTarget as HTMLDivElement).style.borderColor = "var(--border-hover)";
        (e.currentTarget as HTMLDivElement).style.boxShadow = "0 1px 3px rgba(0,0,0,0.04)";
      }}
      onMouseLeave={(e) => {
        (e.currentTarget as HTMLDivElement).style.borderColor = "var(--border)";
        (e.currentTarget as HTMLDivElement).style.boxShadow = "none";
      }}
    >
      {/* Header row */}
      <div className="flex items-start gap-3 px-4" style={{ minHeight: 48, paddingTop: 14, paddingBottom: 14 }}>
        <span
          className="mono flex-shrink-0"
          style={{ fontSize: 11, color: "#9ca3af", letterSpacing: "0.06em", marginTop: 1 }}
        >
          CLAIM {String(claim.index).padStart(2, "0")}
        </span>
        <p className="flex-1" style={{ fontSize: 15, color: "#1a1a1a", margin: 0, lineHeight: 1.55 }}>
          {claim.text}
        </p>
        <div
          className="rounded-full flex-shrink-0 mono"
          style={{
            height: 28,
            padding: "0 12px",
            background: chipBg,
            border: `1px solid ${chipBorder}`,
            fontSize: 13,
            color: color,
            display: "flex",
            alignItems: "center",
            whiteSpace: "nowrap",
            marginTop: 1,
          }}
          aria-label={`${claim.confidence}% confidence`}
        >
          {claim.confidence}% confidence
        </div>
      </div>

      {/* Divider */}
      <div style={{ height: 1, background: "#EFEFEA" }} />

      {/* Evidence toggle row */}
      <button
        onClick={() => setExpanded((v) => !v)}
        aria-expanded={expanded}
        className="w-full flex items-center gap-2 px-4 transition-colors"
        style={{
          height: 40,
          background: "none",
          border: "none",
          cursor: "pointer",
          textAlign: "left",
          color: "#374151",
        }}
      >
        <motion.span
          animate={{ rotate: expanded ? 90 : 0 }}
          transition={{ duration: 0.2 }}
          style={{ display: "inline-flex", color: "#9ca3af" }}
        >
          <ChevronRight size={13} strokeWidth={2.5} />
        </motion.span>
        <span className="mono" style={{ fontSize: 13 }}>
          {evidenceSummary || "No sources"}
        </span>
      </button>

      {/* Evidence rows */}
      <AnimatePresence initial={false}>
        {expanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            style={{ overflow: "hidden" }}
          >
            <div style={{ borderTop: "1px solid #EFEFEA" }}>
              {claim.evidence.map((ev, i) => {
                const showMore = readMoreMap[ev.id];
                const isLong = ev.excerpt.length > 220;
                const displayExcerpt =
                  isLong && !showMore ? ev.excerpt.slice(0, 220) + "…" : ev.excerpt;

                return (
                  <motion.div
                    key={ev.id}
                    initial={{ opacity: 0, y: 4 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: i * 0.06, duration: 0.15 }}
                    className="flex"
                    style={{
                      borderBottom:
                        i < claim.evidence.length - 1 ? "1px solid #F3F3EF" : "none",
                    }}
                  >
                    {/* Stance bar */}
                    <div
                      style={{
                        width: 4,
                        background: stanceBarColor(ev.stance),
                        flexShrink: 0,
                        borderRadius: "0 0 0 0",
                      }}
                    />
                    <div className="flex-1 px-4 py-3" style={{ paddingLeft: 12 }}>
                      <div
                        className="mono label-caps"
                        style={{ color: "#6b7280", marginBottom: 6, fontSize: 11 }}
                      >
                        {ev.source}
                      </div>
                      <p
                        style={{
                          fontSize: 14,
                          color: "#374151",
                          fontStyle: "italic",
                          margin: 0,
                          lineHeight: 1.6,
                        }}
                      >
                        {displayExcerpt}
                        {isLong && (
                          <button
                            onClick={() => setReadMoreMap((m) => ({ ...m, [ev.id]: !m[ev.id] }))}
                            style={{
                              marginLeft: 4,
                              color: "var(--accent)",
                              background: "none",
                              border: "none",
                              cursor: "pointer",
                              fontSize: 13,
                              fontStyle: "normal",
                              fontFamily: "inherit",
                            }}
                          >
                            {showMore ? "Show less" : "Read more"}
                          </button>
                        )}
                      </p>
                      <div className="flex items-center justify-between mt-2.5">
                        <CredibilityDots value={ev.credibility} />
                        <a
                          href="#"
                          style={{
                            fontSize: 12,
                            color: "var(--accent)",
                            textDecoration: "none",
                            fontFamily: "inherit",
                          }}
                          onMouseEnter={(e) => ((e.target as HTMLAnchorElement).style.textDecoration = "underline")}
                          onMouseLeave={(e) => ((e.target as HTMLAnchorElement).style.textDecoration = "none")}
                          onClick={(e) => e.preventDefault()}
                        >
                          View source
                        </a>
                      </div>
                    </div>
                  </motion.div>
                );
              })}
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Uncertainty footnote */}
      {claim.uncertainty && claim.confidence < 60 && (
        <div
          style={{
            background: "var(--subtle)",
            padding: "10px 16px",
            borderTop: "1px solid #EFEFEA",
            borderRadius: "0 0 10px 10px",
          }}
        >
          <span
            className="label-caps"
            style={{ color: "#9ca3af", display: "block", marginBottom: 3 }}
          >
            Why this is uncertain:
          </span>
          <p style={{ fontSize: 13, color: "#6b7280", margin: 0, lineHeight: 1.55 }}>
            {claim.uncertainty}
          </p>
        </div>
      )}
    </div>
  );
}
