import { readFileSync, existsSync, readdirSync } from "fs";
import { join } from "path";
import { notFound } from "next/navigation";
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

export async function generateStaticParams() {
  return getAvailableDates().map((date) => ({ date }));
}

export default function DatePage({ params }: { params: { date: string } }) {
  const { date } = params;

  // 날짜 형식 검증
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) {
    notFound();
  }

  const filePath = join(getDataDir(), `${date}.json`);
  if (!existsSync(filePath)) {
    notFound();
  }

  let data: DayResult;
  try {
    data = JSON.parse(readFileSync(filePath, "utf-8")) as DayResult;
  } catch {
    notFound();
  }

  const characters: CharacterData[] = data.top_k || data.top5 || [];
  const dates = getAvailableDates();

  return (
    <div className="flex gap-6">
      {/* 날짜 네비게이션 */}
      <aside className="hidden lg:block w-48 flex-shrink-0">
        <DateNav dates={dates} currentDate={date} />
      </aside>

      {/* 메인 콘텐츠 */}
      <div className="flex-1 min-w-0">
        <div className="mb-8">
          <div className="flex items-center gap-3 mb-2">
            <h2 className="text-2xl font-bold text-white">
              AI 캐릭터 TOP 5
            </h2>
            <span className="text-sm bg-accent/20 text-accent-light px-3 py-1 rounded-full">
              {date}
            </span>
          </div>
          {data.sources_used && (
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
          <DateNav dates={dates} currentDate={date} mobile />
        </div>

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
            <p>데이터가 없습니다.</p>
          </div>
        )}
      </div>
    </div>
  );
}
