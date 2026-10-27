import type { Metadata } from "next";
import type { JSX, ReactNode } from "react";

import "../styles/tokens.css";
import "./globals.css";

export const metadata: Metadata = {
  title: "sUAS Mission Planner",
  description: "Deterministic preflight assessment with an operator signature",
};

export default function RootLayout({
  children,
}: {
  readonly children: ReactNode;
}): JSX.Element {
  return (
    <html lang="en" data-theme="dark">
      <body>{children}</body>
    </html>
  );
}
