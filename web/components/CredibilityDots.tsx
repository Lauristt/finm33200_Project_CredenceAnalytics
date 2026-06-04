interface CredibilityDotsProps {
  value: number; // 1–6
}

export function CredibilityDots({ value }: CredibilityDotsProps) {
  return (
    <div className="flex items-center gap-0.5" aria-label={`Source credibility: ${value} of 6`}>
      {Array.from({ length: 6 }, (_, i) => (
        <div
          key={i}
          className="rounded-full"
          style={{
            width: 5,
            height: 5,
            background: i < value ? "#374151" : "#D1D5DB",
          }}
        />
      ))}
    </div>
  );
}
