import { existsSync } from "node:fs";
import { defineConfig } from "@playwright/test";

// End-to-end tests run against a running frontend + backend with the demo seed loaded
// (see README → "End-to-end tests"). Set E2E_BASE_URL to target another environment.
const localChromium = "/opt/pw-browsers/chromium";

export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  fullyParallel: false,
  workers: 1,
  reporter: [["list"]],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:3000",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    launchOptions: process.env.PW_CHROMIUM_PATH || existsSync(localChromium)
      ? { executablePath: process.env.PW_CHROMIUM_PATH ?? localChromium } : {},
  },
});
