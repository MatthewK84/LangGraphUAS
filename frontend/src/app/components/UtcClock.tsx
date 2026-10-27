"use client";

import { useEffect, useState } from "react";
import type { JSX } from "react";

/** `HH:mm:ssZ` for a date, in UTC. */
export function formatUtcClock(date: Date): string {
  return `${date.toISOString().slice(11, 19)}Z`;
}

/** The top bar's UTC clock. Blank until mounted, so server and client agree. */
export function UtcClock(): JSX.Element {
  const [now, setNow] = useState<Date | null>(null);
  useEffect(() => {
    setNow(new Date());
    const timer = setInterval(() => {
      setNow(new Date());
    }, 1000);
    return () => {
      clearInterval(timer);
    };
  }, []);
  return (
    <time
      className="font-mono text-sm text-fg-secondary tabular"
      aria-label="UTC time"
    >
      {now === null ? "--:--:--Z" : formatUtcClock(now)}
    </time>
  );
}
