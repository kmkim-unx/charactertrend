"use client";

interface ScoreBarProps {
  label: string;
  score: number;
  max?: number;
  color?: string;
}

export default function ScoreBar({
  label,
  score,
  max = 10,
  color = "bg-accent",
}: ScoreBarProps) {
  const pct = Math.min(100, Math.max(0, (score / max) * 100));

  return (
    <div className="flex items-center gap-2 text-xs">
      <span className="w-7 text-muted font-mono shrink-0">{label}</span>
      <div className="flex-1 h-1.5 bg-border rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-300 ${color}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="w-5 text-right text-gray-400 font-mono shrink-0">
        {score}
      </span>
    </div>
  );
}
