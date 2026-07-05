import type { Metadata } from "next";
import type { JSX, ReactNode } from "react";

import "./globals.css";

export const metadata: Metadata = {
  title: "sUAS Mission Planner",
  description: "AI-powered deterministic flight planning",
};

export default function RootLayout({ children }: { readonly children: ReactNode }): JSX.Element {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
