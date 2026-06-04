"use client";

import { useState, useMemo } from "react";
import { FileText } from "lucide-react";
import { TopBar } from "@/components/TopBar";
import { SummaryBar } from "@/components/SummaryBar";
import { FilterBar, type FilterType, type SortType } from "@/components/FilterBar";
import { ClaimCard } from "@/components/ClaimCard";
import { NoteSlideOver } from "@/components/NoteSlideOver";
import { MOCK_CLAIMS, DOCUMENT_META } from "@/lib/mock-data";

export default function VerificationReport() {
  const [filter, setFilter] = useState<FilterType>("all");
  const [sort, setSort] = useState<SortType>("index");
  const [noteOpen, setNoteOpen] = useState(false);
  const [showUpload, setShowUpload] = useState(false);

  const filtered = useMemo(() => {
    let list = [...MOCK_CLAIMS];
    if (filter === "disputed")
      list = list.filter((c) => c.confidence < 60 && c.contradicting > 0);
    if (filter === "unverified")
      list = list.filter((c) => c.supporting === 0 && c.neutral === 0);
    if (sort === "confidence-asc") list.sort((a, b) => a.confidence - b.confidence);
    if (sort === "confidence-desc") list.sort((a, b) => b.confidence - a.confidence);
    return list;
  }, [filter, sort]);

  if (showUpload) {
    return <UploadState onBack={() => setShowUpload(false)} />;
  }

  return (
    <div style={{ minHeight: "100vh", background: "var(--bg)" }}>
      <TopBar onNewVerification={() => setShowUpload(true)} />

      {/* Main content */}
      <div
        style={{
          maxWidth: 880,
          margin: "0 auto",
          padding: "28px 24px 80px",
        }}
      >
        {/* Page header */}
        <div className="mb-5">
          <div className="flex items-start justify-between gap-4 mb-1.5">
            <h1 style={{ fontSize: 22, fontWeight: 500, margin: 0, color: "#1a1a1a", lineHeight: 1.25 }}>
              {DOCUMENT_META.title}
            </h1>
            <button
              onClick={() => setNoteOpen(true)}
              className="flex items-center gap-1.5 rounded-md px-3 transition-colors flex-shrink-0"
              style={{
                height: 32,
                fontSize: 13,
                color: "#374151",
                border: "1px solid var(--border)",
                background: "white",
                cursor: "pointer",
                fontFamily: "inherit",
              }}
              onMouseEnter={(e) => ((e.currentTarget as HTMLElement).style.borderColor = "var(--border-hover)")}
              onMouseLeave={(e) => ((e.currentTarget as HTMLElement).style.borderColor = "var(--border)")}
            >
              <FileText size={13} strokeWidth={2} />
              View original note
            </button>
          </div>
          <p className="mono" style={{ fontSize: 13, color: "#9ca3af", margin: 0 }}>
            Uploaded {DOCUMENT_META.uploaded} · {DOCUMENT_META.words.toLocaleString()} words ·{" "}
            {DOCUMENT_META.totalClaims} atomic claims
          </p>
        </div>

        {/* Summary bar */}
        <div className="mb-4">
          <SummaryBar claims={MOCK_CLAIMS} />
        </div>

        {/* Filter bar */}
        <FilterBar
          claims={MOCK_CLAIMS}
          active={filter}
          sort={sort}
          onFilter={setFilter}
          onSort={setSort}
        />

        {/* Claim cards */}
        <div style={{ display: "flex", flexDirection: "column", gap: 16, marginTop: 20 }}>
          {filtered.length === 0 ? (
            <p style={{ fontSize: 14, color: "#9ca3af", textAlign: "center", padding: "40px 0" }}>
              No claims match this filter.
            </p>
          ) : (
            filtered.map((claim) => (
              <ClaimCard key={claim.id} claim={claim} />
            ))
          )}
        </div>
      </div>

      <NoteSlideOver
        open={noteOpen}
        onClose={() => setNoteOpen(false)}
        claims={MOCK_CLAIMS}
      />
    </div>
  );
}

function UploadState({ onBack }: { onBack: () => void }) {
  return (
    <div style={{ minHeight: "100vh", background: "var(--bg)" }}>
      <TopBar onNewVerification={onBack} />
      <div
        style={{
          maxWidth: 880,
          margin: "0 auto",
          padding: "80px 24px",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
        }}
      >
        <div
          style={{
            width: "100%",
            maxWidth: 560,
            height: 320,
            border: "1.5px dashed #D1D5DB",
            borderRadius: 10,
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "center",
            gap: 8,
            background: "white",
          }}
        >
          <FileText size={20} strokeWidth={1.5} color="#9ca3af" />
          <p style={{ fontSize: 14, color: "#374151", margin: 0, fontWeight: 500 }}>
            Drop a PDF or paste text.
          </p>
          <p style={{ fontSize: 13, color: "#9ca3af", margin: 0, textAlign: "center", maxWidth: 320 }}>
            Memos, 10-Qs, pitch decks, founder updates — up to 50 pages.
          </p>
          <button
            onClick={onBack}
            style={{
              marginTop: 16,
              height: 32,
              padding: "0 16px",
              fontSize: 13,
              color: "#374151",
              background: "white",
              border: "1px solid var(--border)",
              borderRadius: 6,
              cursor: "pointer",
              fontFamily: "inherit",
            }}
          >
            Back to demo report
          </button>
        </div>
      </div>
    </div>
  );
}
