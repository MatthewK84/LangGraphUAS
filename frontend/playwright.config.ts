// End-to-end against a running stack (#116): the dashboard and the planner in
// their own containers, as Compose runs them. Start the stack first; see
// scripts/e2e.sh, which brings Compose up in demo mode (fixture weather, no
// live provider) and tears it down after.
import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  testMatch: "**/*.e2e.ts",
  fullyParallel: false,
  workers: 1,
  // A retry would hide exactly the intermittent disagreement this exists to find.
  retries: 0,
  timeout: 60_000,
  reporter: [["list"]],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:3000",
    trace: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
