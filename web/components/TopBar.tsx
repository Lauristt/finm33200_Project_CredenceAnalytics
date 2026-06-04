"use client";

import { ChevronRight } from "lucide-react";

interface TopBarProps {
  onNewVerification: () => void;
}

export function TopBar({ onNewVerification }: TopBarProps) {
  return (
    <header
      className="sticky top-0 z-40 bg-white border-b"
      style={{ height: 56, borderColor: "var(--border)" }}
    >
      <div
        className="h-full flex items-center justify-between px-6"
        style={{ maxWidth: 880, margin: "0 auto" }}
      >
        {/* Wordmark */}
        <div className="flex items-center gap-2">
          <div
            className="rounded-sm flex-shrink-0"
            style={{ width: 6, height: 6, background: "var(--accent)" }}
          />
          <span style={{ fontWeight: 500, fontSize: 15, color: "#1a1a1a" }}>
            Veritas
          </span>
        </div>

        {/* Breadcrumb */}
        <nav className="flex items-center gap-1.5 text-gray-500" style={{ fontSize: 13 }}>
          <span>Reports</span>
          <ChevronRight size={12} strokeWidth={2} />
          <span style={{ color: "#1a1a1a" }}>Q3 Memo — Acme Capital</span>
        </nav>

        {/* Actions */}
        <div className="flex items-center gap-3">
          <button
            onClick={onNewVerification}
            className="rounded-md px-3 text-white transition-transform active:scale-[0.98]"
            style={{
              height: 32,
              background: "var(--accent)",
              fontSize: 13,
              fontWeight: 500,
              border: "none",
              cursor: "pointer",
            }}
          >
            New verification
          </button>
          <div
            className="rounded-full flex items-center justify-center flex-shrink-0"
            style={{
              width: 28,
              height: 28,
              background: "#E8EFF5",
              fontSize: 11,
              fontWeight: 600,
              color: "var(--accent)",
              fontFamily: "Inter, sans-serif",
            }}
            aria-label="User: YL"
          >
            YL
          </div>
        </div>
      </div>
    </header>
  );
}
