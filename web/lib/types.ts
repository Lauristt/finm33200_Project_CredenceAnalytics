export type ConfidenceBand = "green" | "amber" | "orange" | "red";

export function getBand(score: number): ConfidenceBand {
  if (score >= 80) return "green";
  if (score >= 60) return "amber";
  if (score >= 40) return "orange";
  return "red";
}

export function getBandColor(band: ConfidenceBand): string {
  switch (band) {
    case "green":  return "#2F7D5B";
    case "amber":  return "#B8923A";
    case "orange": return "#C2602E";
    case "red":    return "#A4332B";
  }
}

export function getVerdict(score: number): string {
  if (score >= 80) return "WELL SUPPORTED";
  if (score >= 60) return "MODERATELY SUPPORTED";
  if (score >= 40) return "PARTIALLY SUPPORTED";
  return "DISPUTED";
}

export type EvidenceStance = "supporting" | "contradicting" | "neutral";

export interface EvidenceItem {
  id: string;
  stance: EvidenceStance;
  source: string;
  filed: string;
  excerpt: string;
  credibility: number; // 1–6
}

export interface Claim {
  id: string;
  index: number;
  text: string;
  confidence: number;
  supporting: number;
  contradicting: number;
  neutral: number;
  evidence: EvidenceItem[];
  uncertainty?: string;
  sourceSentence: string;
}
