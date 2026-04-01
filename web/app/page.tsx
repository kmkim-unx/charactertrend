import { readFileSync, existsSync, readdirSync } from "fs";
import { join } from "path";
import CharacterCard from "@/components/CharacterCard";
import DateNav from "@/components/DateNav";

interface CharacterData {
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

interface DayResult {
  date?: string;
  generated_at?: string;
  sources_used?: string[];
  top_k?: CharacterData[];
  top5?: CharacterData[];
  all_chars?: CharacterData[];
}

function getDataDir() {
  return join(process.cwd(), "public", "data");
}

function getAvailableDates(): string[] {
  const dir = getDataDir();
  if (!existsSync(dir)) return [];
  return readdirSync(dir)
    .filter((f) => /^\d{4}-\d{2}-\d{2}\.json$/.test(f))
    .map((f) => f.replace(".json", ""))
    .sort()
    .reverse();
}

function loadDayData(date: string): DayResult | null {
  const filePath = join(getDataDir(), `${date}.json`);
  if (!existsSync(filePath)) return null;
  try {
    const raw = readFileSync(filePath, "utf-8");
    return JSON.parse(raw) as DayResult;
  } catch {
    return null;
  }
}

export default function HomePage() {
  const dates = getAvailableDates();
  const latestDate = dates[0] || null;
  const data = latestDate ? loadDayData(latestDate) : null;
  const characters: CharacterData[] = data?.top_k || data?.top5 || [];

  return (
    <div className="flex gap-6">
      {/* 날짜 네비게이션 */}
      <aside className="hidden lg:block w-48 flex-shrink-0">
        <DateNav dates={dates} currentDate={latestDate || ""} />
      </aside>

      {/* 메인 콘텐츠 */}
      <div className="flex-1 min-w-0">
        {/* 헤더 */}
        <div className="mb-8">
          <div className="flex items-center gap-3 mb-2">
            <h2 className="text-2xl font-bold text-white">
              오늘의 AI 캐릭터 TOP 5
            </h2>
            {latestDate && (
              <span className="text-sm bg-accent/20 text-accent-light px-3 py-1 rounded-full">
                {latestDate}
              </span>
            )}
          </div>
          {data?.sources_used && (
            <p className="text-muted text-sm">
              수집 소스:{" "}
              {data.sources_used
                .map((s) => s.charAt(0).toUpperCase() + s.slice(1))
                .join(", ")}
            </p>
          )}
        </div>

        {/* 모바일 날짜 네비게이션 */}
        <div className="lg:hidden mb-6">
          <DateNav dates={dates} currentDate={latestDate || ""} mobile />
        </div>

        {/* 캐릭터 카드 그리드 */}
        {characters.length > 0 ? (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-5">
            {characters.map((char, i) => (
              <CharacterCard
                key={`${char.name}-${i}`}
                character={{ ...char, rank: char.rank || i + 1 }}
              />
            ))}
          </div>
        ) : (
          <div className="text-center py-24 text-muted">
            <div className="text-5xl mb-4">📭</div>
            <p className="text-lg">아직 데이터가 없습니다.</p>
            <p className="text-sm mt-2">
              <code className="bg-card px-2 py-1 rounded text-accent-light">
                python3 run_pipeline.py --sources zeta,crack,rofan
              </code>
              을 실행하면 데이터가 생성됩니다.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
