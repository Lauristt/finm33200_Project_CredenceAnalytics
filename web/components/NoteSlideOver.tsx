"use client";

import React, { useEffect, useRef } from "react";
import { X } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { getBandColor, getBand, type Claim } from "@/lib/types";
import { ORIGINAL_NOTE } from "@/lib/mock-data";

interface NoteSlideOverProps {
  open: boolean;
  onClose: () => void;
  claims: Claim[];
}

function highlightNote(text: string, claims: Claim[]): React.ReactNode[] {
  let key = 0;
  const segments = text.split("\n\n");
  return segments.map((para, pi) => {
    let paraContent: React.ReactNode[] = [];
    let rem = para;

    for (const claim of claims) {
      const idx = rem.indexOf(claim.sourceSentence);
      if (idx === -1) continue;

      const before = rem.slice(0, idx);
      const matched = rem.slice(idx, idx + claim.sourceSentence.length);
      rem = rem.slice(idx + claim.sourceSentence.length);

      if (before) paraContent.push(<span key={key++}>{before}</span>);

      const color = getBandColor(getBand(claim.confidence));
      paraContent.push(
        <span key={key++} style={{ position: "relative", display: "inline" }}>
          <span
            title={`Claim ${String(claim.index).padStart(2, "0")} · ${claim.confidence}% confidence`}
            style={{
              borderBottom: `2px solid ${color}`,
              cursor: "default",
            }}
          >
            {matched}
          </span>
        </span>
      );
    }

    if (rem) paraContent.push(<span key={key++}>{rem}</span>);
    if (paraContent.length === 0) paraContent = [<span key={key++}>{para}</span>];

    const isHeading = para.startsWith("Acme Capital") || !para.includes(" ") || para.length < 40;
    return (
      <p
        key={pi}
        style={{
          fontSize: 14,
          lineHeight: 1.65,
          color: "#374151",
          margin: 0,
          marginBottom: 16,
          fontWeight: isHeading ? 600 : 400,
        }}
      >
        {paraContent}
      </p>
    );
  });
}

export function NoteSlideOver({ open, onClose, claims }: NoteSlideOverProps) {
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    if (open) document.addEventListener("keydown", handleKey);
    return () => document.removeEventListener("keydown", handleKey);
  }, [open, onClose]);

  return (
    <AnimatePresence>
      {open && (
        <>
          {/* Backdrop */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.15 }}
            onClick={onClose}
            style={{
              position: "fixed",
              inset: 0,
              background: "rgba(0,0,0,0.18)",
              zIndex: 50,
            }}
          />

          {/* Panel */}
          <motion.div
            ref={panelRef}
            initial={{ x: 480 }}
            animate={{ x: 0 }}
            exit={{ x: 480 }}
            transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
            style={{
              position: "fixed",
              top: 0,
              right: 0,
              bottom: 0,
              width: 480,
              background: "white",
              borderLeft: "1px solid var(--border)",
              zIndex: 51,
              display: "flex",
              flexDirection: "column",
            }}
          >
            {/* Header */}
            <div
              className="flex items-center justify-between px-5"
              style={{
                height: 52,
                borderBottom: "1px solid var(--border)",
                flexShrink: 0,
              }}
            >
              <span style={{ fontSize: 14, fontWeight: 500, color: "#1a1a1a" }}>
                Original note
              </span>
              <button
                onClick={onClose}
                style={{
                  background: "none",
                  border: "none",
                  cursor: "pointer",
                  color: "#9ca3af",
                  display: "flex",
                  padding: 4,
                }}
                aria-label="Close"
              >
                <X size={16} />
              </button>
            </div>

            {/* Legend */}
            <div
              className="flex items-center gap-4 px-5 py-2.5"
              style={{ borderBottom: "1px solid #F3F3EF", flexShrink: 0 }}
            >
              {[
                { color: "#2F7D5B", label: "High confidence" },
                { color: "#B8923A", label: "Moderate" },
                { color: "#C2602E", label: "Low" },
                { color: "#A4332B", label: "Disputed" },
              ].map(({ color, label }) => (
                <span key={color} className="flex items-center gap-1.5" style={{ fontSize: 11, color: "#6b7280" }}>
                  <span style={{ width: 12, height: 2, background: color, display: "inline-block" }} />
                  {label}
                </span>
              ))}
            </div>

            {/* Content */}
            <div
              className="flex-1 overflow-y-auto px-5 py-5"
              style={{ fontSize: 14, lineHeight: 1.65 }}
            >
              {highlightNote(ORIGINAL_NOTE, claims)}
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
