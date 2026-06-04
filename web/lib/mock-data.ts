import type { Claim } from "./types";

export const MOCK_CLAIMS: Claim[] = [
  {
    id: "c01",
    index: 1,
    text: "Q2 2026 revenue grew 34% year-over-year to $127M, ahead of consensus estimates of $118M.",
    confidence: 87,
    supporting: 3,
    contradicting: 0,
    neutral: 1,
    sourceSentence: "Q2 2026 revenue grew 34% year-over-year to $127M, ahead of consensus estimates of $118M.",
    evidence: [
      {
        id: "e1a",
        stance: "supporting",
        source: "SEC 10-Q · FILED 2026-08-12",
        filed: "2026-08-12",
        excerpt: "“Net revenues for the second quarter of fiscal 2026 were $127.4 million, representing an increase of 33.8% compared to net revenues of $95.2 million for the second quarter of fiscal 2025.”",
        credibility: 6,
      },
      {
        id: "e1b",
        stance: "supporting",
        source: "BLOOMBERG · ACME EQUITY RESEARCH · MORGAN STANLEY",
        filed: "2026-07-30",
        excerpt: "“We maintain our Buy rating with a revised price target of $84. Our Q2 estimate of $118M reflected conservative assumptions on enterprise upsell; management’s $127M print was 7.6% above our model.”",
        credibility: 4,
      },
      {
        id: "e1c",
        stance: "supporting",
        source: "ACME CAPITAL 8-K · FILED 2026-08-03",
        filed: "2026-08-03",
        excerpt: "“The Company today announced preliminary unaudited revenue of approximately $127 million for the fiscal second quarter ended June 30, 2026.”",
        credibility: 6,
      },
      {
        id: "e1d",
        stance: "neutral",
        source: "REFINITIV I/B/E/S · CONSENSUS SNAPSHOT 2026-07-28",
        filed: "2026-07-28",
        excerpt: "“Median sell-side estimate for ACME Q2 2026 revenue: $118.3M (n=14 analysts). Range $112M–$124M. Beat probability implied by options: 62%.”",
        credibility: 5,
      },
    ],
  },
  {
    id: "c02",
    index: 2,
    text: "Gross margin expanded 180 basis points sequentially to 71.4%, driven by software mix shift.",
    confidence: 82,
    supporting: 2,
    contradicting: 0,
    neutral: 1,
    sourceSentence: "Gross margin expanded 180 basis points sequentially to 71.4%, driven by software mix shift.",
    evidence: [
      {
        id: "e2a",
        stance: "supporting",
        source: "SEC 10-Q · FILED 2026-08-12",
        filed: "2026-08-12",
        excerpt: "“Gross profit as a percentage of net revenues was 71.4% for Q2 2026, compared to 69.6% for Q1 2026 and 68.1% for Q2 2025.”",
        credibility: 6,
      },
      {
        id: "e2b",
        stance: "supporting",
        source: "ACME CAPITAL Q2 2026 EARNINGS CALL TRANSCRIPT",
        filed: "2026-08-12",
        excerpt: "“The 180bp sequential improvement reflects our continued pivot to subscription-first delivery. Hardware and professional services revenue, which carry lower margins, declined as a share of mix from 38% to 31% of total.”",
        credibility: 4,
      },
      {
        id: "e2c",
        stance: "neutral",
        source: "JPMORGAN EQUITY RESEARCH · 2026-08-13",
        filed: "2026-08-13",
        excerpt: "“Gross margin at 71.4% surprised to the upside by ~120bp vs. our model. We attribute the delta primarily to favorable revenue mix and lower cloud infrastructure costs from the AWS re-negotiation disclosed in the Q1 10-Q.”",
        credibility: 4,
      },
    ],
  },
  {
    id: "c03",
    index: 3,
    text: "The company holds $340M in cash and short-term investments with zero drawn on its $200M revolving credit facility.",
    confidence: 91,
    supporting: 4,
    contradicting: 0,
    neutral: 0,
    sourceSentence: "The company holds $340M in cash and short-term investments with zero drawn on its $200M revolving credit facility.",
    evidence: [
      {
        id: "e3a",
        stance: "supporting",
        source: "SEC 10-Q · BALANCE SHEET · FILED 2026-08-12",
        filed: "2026-08-12",
        excerpt: "“Cash and cash equivalents: $218.7M; short-term investments: $121.4M; total liquidity: $340.1M as of June 30, 2026.”",
        credibility: 6,
      },
      {
        id: "e3b",
        stance: "supporting",
        source: "SEC 10-Q · NOTE 7 — CREDIT FACILITY · FILED 2026-08-12",
        filed: "2026-08-12",
        excerpt: "“As of June 30, 2026, there were no amounts outstanding under the Company’s $200.0 million revolving credit facility. The facility matures on March 15, 2029.”",
        credibility: 6,
      },
      {
        id: "e3c",
        stance: "supporting",
        source: "ACME CAPITAL 8-K · FILED 2026-08-03",
        filed: "2026-08-03",
        excerpt: "“The Company had total liquidity of approximately $340 million as of quarter-end, with the revolving credit facility fully undrawn.”",
        credibility: 6,
      },
      {
        id: "e3d",
        stance: "supporting",
        source: "MOODY’S CREDIT OPINION · ACME CAPITAL · 2026-06-15",
        filed: "2026-06-15",
        excerpt: "“Liquidity is strong. We expect the company to maintain $250M+ in cash and equivalents over the next 12 months, supported by free cash flow generation of approximately $80–90M annually.”",
        credibility: 5,
      },
    ],
  },
  {
    id: "c04",
    index: 4,
    text: "Net Revenue Retention rate of 118% reflects strong expansion within the existing customer base.",
    confidence: 73,
    supporting: 2,
    contradicting: 1,
    neutral: 0,
    sourceSentence: "Net Revenue Retention rate of 118% reflects strong expansion within the existing customer base.",
    evidence: [
      {
        id: "e4a",
        stance: "supporting",
        source: "ACME CAPITAL INVESTOR PRESENTATION · JUNE 2026",
        filed: "2026-06-10",
        excerpt: "“Net Revenue Retention (NRR) was 118% for the trailing twelve months ended March 31, 2026, reflecting net expansion from upsell and cross-sell activity.”",
        credibility: 3,
      },
      {
        id: "e4b",
        stance: "supporting",
        source: "SEC 10-K · FILED 2026-03-15",
        filed: "2026-03-15",
        excerpt: "“Our dollar-based NRR for fiscal 2025 was 118%. This metric is calculated on a trailing twelve-month basis and is updated annually.”",
        credibility: 6,
      },
      {
        id: "e4c",
        stance: "contradicting",
        source: "GOLDMAN SACHS EQUITY RESEARCH · 2026-08-14",
        filed: "2026-08-14",
        excerpt: "“Management declined to update NRR on the Q2 call, citing a methodology change under consideration. Our channel checks suggest the Q2 2026 TTM figure may be closer to 112–114%, reflecting churn in the mid-market segment post-pricing revision.”",
        credibility: 4,
      },
    ],
  },
  {
    id: "c05",
    index: 5,
    text: "The enterprise segment added 47 net-new customers in Q2, bringing total enterprise customer count to 412.",
    confidence: 64,
    supporting: 1,
    contradicting: 1,
    neutral: 2,
    sourceSentence: "The enterprise segment added 47 net-new customers in Q2, bringing total enterprise customer count to 412.",
    evidence: [
      {
        id: "e5a",
        stance: "supporting",
        source: "ACME CAPITAL Q2 2026 EARNINGS CALL TRANSCRIPT",
        filed: "2026-08-12",
        excerpt: "“We added 47 enterprise customers in the quarter, ending Q2 with 412 enterprise logos. We define enterprise as organizations with more than 500 employees or $50M in annual revenue.”",
        credibility: 3,
      },
      {
        id: "e5b",
        stance: "contradicting",
        source: "SEC 10-Q · FOOTNOTE 4 — SEGMENT REPORTING · FILED 2026-08-12",
        filed: "2026-08-12",
        excerpt: "“As of June 30, 2026, the Company had 398 customers meeting the enterprise definition. The definition was updated in Q1 2026 to require $100M in annual revenue (previously $50M), affecting retroactive comparability.”",
        credibility: 6,
      },
      {
        id: "e5c",
        stance: "neutral",
        source: "BARCLAYS EQUITY RESEARCH · 2026-08-13",
        filed: "2026-08-13",
        excerpt: "“The discrepancy between management’s 412 figure and the 10-Q’s 398 appears to reflect the mid-quarter definition change. We are seeking clarification from IR before updating our model.”",
        credibility: 4,
      },
      {
        id: "e5d",
        stance: "neutral",
        source: "ACME CAPITAL IR CORRESPONDENCE · 2026-08-15",
        filed: "2026-08-15",
        excerpt: "“The 412 figure referenced by the CEO reflects customers under the prior definition for comparability purposes. The 398 figure in the 10-Q applies the updated definition.”",
        credibility: 2,
      },
    ],
    uncertainty:
      "The cited customer count of 412 is computed under the prior enterprise definition (>$50M revenue). The 10-Q applies a revised threshold of $100M, which yields 398 customers. Management acknowledged the discrepancy on the Q2 call but did not restate prior periods. The figure as presented is not directly comparable to Q1 disclosures.",
  },
  {
    id: "c06",
    index: 6,
    text: "Management reaffirmed full-year revenue guidance of $490–505M, implying 28–32% growth.",
    confidence: 79,
    supporting: 3,
    contradicting: 0,
    neutral: 1,
    sourceSentence: "Management reaffirmed full-year revenue guidance of $490–505M, implying 28–32% growth.",
    evidence: [
      {
        id: "e6a",
        stance: "supporting",
        source: "ACME CAPITAL Q2 2026 EARNINGS CALL TRANSCRIPT",
        filed: "2026-08-12",
        excerpt: "“We are reaffirming our full-year 2026 revenue guidance of $490 to $505 million.”",
        credibility: 3,
      },
      {
        id: "e6b",
        stance: "supporting",
        source: "SEC 8-K · EXHIBIT 99.1 PRESS RELEASE · FILED 2026-08-12",
        filed: "2026-08-12",
        excerpt: "“Full Year 2026 Guidance: Revenue $490M–$505M; Non-GAAP Operating Income $58M–$65M.”",
        credibility: 6,
      },
      {
        id: "e6c",
        stance: "supporting",
        source: "BLOOMBERG CONSENSUS · 2026-08-14",
        filed: "2026-08-14",
        excerpt: "“Median full-year 2026 estimate revised to $497M following Q2 print, within the guided range. Prior consensus was $488M.”",
        credibility: 5,
      },
      {
        id: "e6d",
        stance: "neutral",
        source: "ACME CAPITAL FISCAL 2025 10-K · REVENUE NOTE",
        filed: "2026-03-15",
        excerpt: "“Fiscal 2025 net revenues were $380.4 million. On this base, the guided range of $490–$505M implies growth of 28.8% to 32.8%.”",
        credibility: 6,
      },
    ],
  },
  {
    id: "c07",
    index: 7,
    text: "The proposed acquisition of DataBridge Analytics for $215M in cash will close by end of Q4 2026, pending HSR clearance.",
    confidence: 42,
    supporting: 1,
    contradicting: 2,
    neutral: 1,
    sourceSentence: "The proposed acquisition of DataBridge Analytics for $215M in cash will close by end of Q4 2026, pending HSR clearance.",
    evidence: [
      {
        id: "e7a",
        stance: "supporting",
        source: "ACME CAPITAL 8-K · MERGER AGREEMENT · FILED 2026-07-22",
        filed: "2026-07-22",
        excerpt: "“Acme Capital and DataBridge Analytics today announced a definitive agreement under which Acme will acquire DataBridge for $215 million in cash. The transaction is expected to close by December 31, 2026.”",
        credibility: 6,
      },
      {
        id: "e7b",
        stance: "contradicting",
        source: "DOJ ANTITRUST DIVISION — PUBLIC STATEMENT · 2026-08-10",
        filed: "2026-08-10",
        excerpt: "“The Antitrust Division has issued a Second Request for additional information and documentary material in connection with the proposed acquisition of DataBridge Analytics by Acme Capital. The issuance of a Second Request extends the HSR waiting period.”",
        credibility: 6,
      },
      {
        id: "e7c",
        stance: "contradicting",
        source: "WALL STREET JOURNAL · M&A COLUMN · 2026-08-11",
        filed: "2026-08-11",
        excerpt: "“A DOJ Second Request typically adds four to six months to deal timelines, making a Q4 2026 close highly unlikely. Legal experts cited by the Journal estimate a mid-2027 resolution at the earliest, with a non-trivial probability of remedies or abandonment.”",
        credibility: 3,
      },
      {
        id: "e7d",
        stance: "neutral",
        source: "ACME CAPITAL Q2 2026 EARNINGS CALL TRANSCRIPT",
        filed: "2026-08-12",
        excerpt: "“We received a Second Request and are cooperating fully. We continue to believe the transaction will close, though we are not in a position to affirm the original timeline at this time.”",
        credibility: 3,
      },
    ],
    uncertainty:
      "The DOJ issued a Second Request on August 10, after the merger agreement was signed. Management walked back the Q4 2026 close date on the earnings call. A Second Request has historically extended deal timelines by 4–6 months; Q4 2026 close is no longer the base case. The $215M cash consideration is confirmed, but deal certainty is materially lower than presented in the memo.",
  },
  {
    id: "c08",
    index: 8,
    text: "ACME’s stock has outperformed the S&P 500 by 22 percentage points year-to-date through August 12, 2026.",
    confidence: 31,
    supporting: 0,
    contradicting: 2,
    neutral: 1,
    sourceSentence: "ACME’s stock has outperformed the S&P 500 by 22 percentage points year-to-date through August 12, 2026.",
    evidence: [
      {
        id: "e8a",
        stance: "contradicting",
        source: "BLOOMBERG TERMINAL · ACME.O EQUITY · PRICE HISTORY",
        filed: "2026-08-12",
        excerpt: "“ACME.O YTD return through 2026-08-12: +18.4%. S&P 500 (SPX) YTD return: +9.7%. Relative outperformance: 870bp (8.7 percentage points).”",
        credibility: 6,
      },
      {
        id: "e8b",
        stance: "contradicting",
        source: "FACTSET MARKET DATA · 2026-08-12 CLOSE",
        filed: "2026-08-12",
        excerpt: "“ACME Capital (ACME): YTD price return +18.3% vs. SPX +9.6%. Outperformance: 8.7pp. Total return (with dividends): ACME +18.3%, SPX +11.1%, outperformance 7.2pp.”",
        credibility: 6,
      },
      {
        id: "e8c",
        stance: "neutral",
        source: "ACME CAPITAL INVESTOR PRESENTATION · JUNE 2026",
        filed: "2026-06-10",
        excerpt: "“ACME has delivered 22pp of relative outperformance vs. the S&P 500 over the trailing twelve months ended May 31, 2026.”",
        credibility: 3,
      },
    ],
    uncertainty:
      "The memo cites 22pp outperformance on a year-to-date basis through August 12. Two independent market data sources (Bloomberg and FactSet) show YTD outperformance of approximately 8.7pp over the same period. The 22pp figure is consistent with the trailing twelve-month figure cited in ACME’s June 2026 investor presentation — a materially different measurement window. This appears to be a YTD vs. TTM conflation.",
  },
];

export const DOCUMENT_META = {
  title: "Acme Capital — Q3 2026 Growth Memo",
  uploaded: "Oct 14, 2026",
  words: 1847,
  totalClaims: 23,
  reportedClaims: 8,
};

export const ORIGINAL_NOTE = `Acme Capital — Q3 2026 Growth Memo

Executive Summary

${MOCK_CLAIMS[0].text} The business continues to execute on its platform consolidation strategy, with software subscription revenues now representing 69% of total revenue compared to 61% in the prior year period.

${MOCK_CLAIMS[1].text} Management attributes the improvement to the ongoing shift away from lower-margin hardware and professional services, with the subscription gross margin now tracking above 78%.

Balance Sheet and Capital Allocation

${MOCK_CLAIMS[2].text} The company generated $31M in free cash flow during the quarter, maintaining its trajectory toward full-year FCF of $80–90M.

Customer Metrics

${MOCK_CLAIMS[3].text} The cohort of customers acquired in fiscal 2023 now shows NRR of 127%, indicating strong product-market fit in the enterprise segment.

${MOCK_CLAIMS[4].text} Average contract value among new enterprise logos was $184K annually, up from $141K in Q2 2025, reflecting the company's success moving upmarket.

Forward Guidance

${MOCK_CLAIMS[5].text} The guidance implies second-half revenue of $236–251M, representing 23–31% H2-over-H2 growth.

Strategic Initiatives

${MOCK_CLAIMS[6].text} The DataBridge platform adds approximately 180 data connectors and a proprietary entity resolution engine that management expects to integrate into the Acme core product within 18 months of close.

Market Performance

${MOCK_CLAIMS[7].text} This outperformance reflects the market's recognition of Acme's durable revenue model and strong competitive positioning within the enterprise data infrastructure category.`;
