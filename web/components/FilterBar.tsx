"use client";

import type { Claim } from "@/lib/types";

export type FilterType = "all" | "disputed" | "unverified";
export type SortType = "confidence-asc" | "confidence-desc" | "index";

interface FilterBarProps {
  claims: Claim[];
  active: FilterType;
  sort: SortType;
  onFilter: (f: FilterType) => void;
  onSort: (s: SortType) => void;
}

const SORT_LABELS: Record<SortType, string> = {
  "confidence-asc": "Confidence — low to high",
  "confidence-desc": "Confidence — high to low",
  index: "Document order",
};

export function FilterBar({ claims, active, sort, onFilter, onSort }: FilterBarProps) {
  const disputed = claims.filter((c) => c.confidence < 60 && c.contradicting > 0).length;
  const unverified = claims.filter((c) => c.supporting === 0 && c.neutral === 0).length;

  const filters: { key: FilterType; label: string; count: number }[] = [
    { key: "all", label: "All", count: claims.length },
    { key: "disputed", label: "Disputed", count: disputed },
    { key: "unverified", label: "Unverified", count: unverified },
  ];

  return (
    <div
      className="sticky z-30 bg-white border-b flex items-center justify-between px-6"
      style={{ top: 56, height: 44, borderColor: "var(--border)", maxWidth: "100%" }}
    >
      {/* Filter chips */}
      <div className="flex items-center gap-0">
        {filters.map(({ key, label, count }, i) => (
          <button
            key={key}
            onClick={() => onFilter(key)}
            className="flex items-center gap-1.5 h-full px-3 transition-colors"
            style={{
              fontSize: 13,
              color: active === key ? "var(--accent)" : "#6b7280",
              fontWeight: active === key ? 500 : 400,
              borderTop: "none",
              borderLeft: "none",
              borderRight: "none",
              borderBottom: active === key ? `1.5px solid var(--accent)` : "1.5px solid transparent",
              marginBottom: -1,
              background: "none",
              cursor: "pointer",
              height: 44,
              paddingLeft: i === 0 ? 0 : 12,
              paddingRight: 12,
            }}
            aria-pressed={active === key}
          >
            {label}
            <span
              className="mono"
              style={{
                fontSize: 12,
                color: active === key ? "var(--accent)" : "#9ca3af",
                fontWeight: 400,
              }}
            >
              {count}
            </span>
          </button>
        ))}
      </div>

      {/* Sort */}
      <div className="flex items-center gap-2">
        <span style={{ fontSize: 13, color: "#6b7280" }}>Order:</span>
        <select
          value={sort}
          onChange={(e) => onSort(e.target.value as SortType)}
          style={{
            fontSize: 13,
            color: "#374151",
            background: "none",
            border: "none",
            cursor: "pointer",
            outline: "none",
            fontFamily: "inherit",
          }}
        >
          {Object.entries(SORT_LABELS).map(([k, v]) => (
            <option key={k} value={k}>{v}</option>
          ))}
        </select>
      </div>
    </div>
  );
}
