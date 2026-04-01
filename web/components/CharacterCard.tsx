"use client";

import ScoreBar from "./ScoreBar";

interface Character {
  rank: number;
  name: string;
  source: string;
  description: string;
  tags: string[];
  interaction_count: number;
  image_url: string;
  url: string;
  g3: number;
  g4: number;
  g5: number;
  total: number;
  reason: string;
  unx_fit: string;
}

interface Props {
  character: Character;
}

const SOURCE_COLORS: Record<string, string> = {
  zeta: "bg-zeta/20 text-blue-400",
  crack: "bg-crack/20 text-emerald-400",
  rofan: "bg-rofan/20 text-amber-400",
};

const SOURCE_LABELS: Record<string, string> = {
  zeta: "Zeta",
  crack: "Crack",
  rofan: "Rofan",
};

const RANK_COLORS: Record<number, string> = {
  1: "bg-yellow-500 text-black",
  2: "bg-gray-400 text-black",
  3: "bg-amber-600 text-white",
};

function formatCount(n: number): string {
  if (!n) return "";
  if (n >= 100_000_000) return `${(n / 100_000_000).toFixed(1)}억`;
  if (n >= 10_000) return `${(n / 10_000).toFixed(1)}만`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}천`;
  return String(n);
}

export default function CharacterCard({ character: char }: Props) {
  const sourceColor = SOURCE_COLORS[char.source] || "bg-gray-700 text-gray-300";
  const sourceLabel = SOURCE_LABELS[char.source] || char.source.toUpperCase();
  const rankColor = RANK_COLORS[char.rank] || "bg-border text-gray-300";

  return (
    <div className="bg-card border border-border rounded-2xl overflow-hidden hover:border-accent/50 transition-colors flex flex-col">
      {/* 이미지 영역 */}
      <div className="relative aspect-[4/3] bg-bg overflow-hidden">
        {char.image_url ? (
          /* eslint-disable-next-line @next/next/no-img-element */
          <img
            src={char.image_url}
            alt={char.name}
            className="w-full h-full object-cover"
            onError={(e) => {
              (e.target as HTMLImageElement).style.display = "none";
            }}
          />
        ) : (
          <div className="w-full h-full flex items-center justify-center bg-gradient-to-br from-accent/10 to-bg">
            <span className="text-4xl text-accent/30">
              {char.name.charAt(0)}
            </span>
          </div>
        )}

        {/* 오버레이: 순위 + 소스 배지 */}
        <div className="absolute top-3 left-3 right-3 flex justify-between items-start">
          {/* 순위 배지 */}
          <span
            className={`text-xs font-bold px-2 py-0.5 rounded-md ${rankColor}`}
          >
            #{char.rank}
          </span>
          {/* 소스 배지 */}
          <span
            className={`text-xs font-semibold px-2 py-0.5 rounded-md ${sourceColor}`}
          >
            {sourceLabel}
          </span>
        </div>

        {/* 대화수 오버레이 */}
        {char.interaction_count > 0 && (
          <div className="absolute bottom-2 right-2 bg-black/60 backdrop-blur-sm text-white text-xs px-2 py-0.5 rounded-md">
            {formatCount(char.interaction_count)} 대화
          </div>
        )}
      </div>

      {/* 카드 본문 */}
      <div className="p-4 flex flex-col gap-3 flex-1">
        {/* 이름 */}
        <div>
          <h3 className="text-base font-semibold text-white leading-tight line-clamp-1">
            {char.name}
          </h3>
          {/* 태그 */}
          {char.tags && char.tags.length > 0 && (
            <div className="flex flex-wrap gap-1 mt-1.5">
              {char.tags.slice(0, 4).map((tag, i) => (
                <span
                  key={i}
                  className="text-xs text-muted bg-bg px-1.5 py-0.5 rounded"
                >
                  {tag.startsWith("#") ? tag : `#${tag}`}
                </span>
              ))}
            </div>
          )}
        </div>

        {/* G3/G4/G5 점수 */}
        <div className="space-y-1.5">
          <ScoreBar label="G3" score={char.g3} color="bg-blue-500" />
          <ScoreBar label="G4" score={char.g4} color="bg-purple-500" />
          <ScoreBar label="G5" score={char.g5} color="bg-pink-500" />
          <div className="flex justify-between items-center pt-0.5">
            <span className="text-xs text-muted">합계</span>
            <span className="text-sm font-bold text-accent-light">
              {char.total ?? char.g3 + char.g4 + char.g5}
              <span className="text-xs text-muted font-normal">/30</span>
            </span>
          </div>
        </div>

        {/* 설명 */}
        {char.description && (
          <p className="text-xs text-muted leading-relaxed line-clamp-3">
            {char.description}
          </p>
        )}

        {/* UNX 추천 이유 */}
        {char.unx_fit && (
          <div className="bg-accent/10 border border-accent/20 rounded-lg px-3 py-2">
            <p className="text-xs text-accent-light leading-relaxed line-clamp-2">
              {char.unx_fit}
            </p>
          </div>
        )}

        {/* GPT 분석 (접힌 상태) */}
        {char.reason && (
          <details className="group">
            <summary className="text-xs text-muted cursor-pointer hover:text-gray-300 transition-colors list-none flex items-center gap-1">
              <span className="group-open:rotate-90 transition-transform">▶</span>
              GPT 분석 보기
            </summary>
            <p className="text-xs text-gray-400 leading-relaxed mt-2 pl-3 border-l border-border">
              {char.reason}
            </p>
          </details>
        )}

        {/* 링크 */}
        {char.url && (
          <a
            href={char.url}
            target="_blank"
            rel="noopener noreferrer"
            className="mt-auto text-xs text-center text-muted hover:text-accent-light border border-border hover:border-accent/40 rounded-lg py-1.5 transition-colors"
          >
            캐릭터 보러가기 →
          </a>
        )}
      </div>
    </div>
  );
}
