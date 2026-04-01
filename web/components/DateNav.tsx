"use client";

import Link from "next/link";

interface Props {
  dates: string[];
  currentDate: string;
  mobile?: boolean;
}

export default function DateNav({ dates, currentDate, mobile = false }: Props) {
  if (dates.length === 0) {
    return (
      <div className="text-xs text-muted py-2 px-3">
        히스토리 없음
      </div>
    );
  }

  if (mobile) {
    return (
      <div className="flex gap-2 overflow-x-auto pb-2 scrollbar-hide">
        {dates.map((date) => (
          <Link
            key={date}
            href={date === dates[0] ? "/" : `/${date}`}
            className={`shrink-0 text-xs px-3 py-1.5 rounded-full border transition-colors ${
              date === currentDate
                ? "border-accent bg-accent/20 text-accent-light"
                : "border-border text-muted hover:border-accent/40 hover:text-gray-300"
            }`}
          >
            {date}
          </Link>
        ))}
      </div>
    );
  }

  return (
    <nav>
      <p className="text-xs text-muted font-semibold uppercase tracking-wider mb-3 px-1">
        히스토리
      </p>
      <ul className="space-y-0.5">
        {dates.map((date) => (
          <li key={date}>
            <Link
              href={date === dates[0] ? "/" : `/${date}`}
              className={`block text-sm px-3 py-1.5 rounded-lg transition-colors ${
                date === currentDate
                  ? "bg-accent/20 text-accent-light font-medium"
                  : "text-muted hover:bg-card hover:text-gray-300"
              }`}
            >
              {date}
            </Link>
          </li>
        ))}
      </ul>
    </nav>
  );
}
