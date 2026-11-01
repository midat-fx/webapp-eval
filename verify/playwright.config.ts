import { defineConfig } from "@playwright/test";

// Hidden verifiers for one task are copied into ./specs right before they run.
export default defineConfig({
  testDir: "./specs",
  workers: 1,
  retries: 0,
  timeout: 90_000,
  expect: { timeout: 20_000 },
  reporter: [["json", { outputFile: process.env.PW_JSON ?? "playwright.json" }], ["list"]],
  outputDir: process.env.PW_OUTPUT ?? "test-results",
  use: {
    actionTimeout: 20_000,
    baseURL: "http://localhost:3000",
    timezoneId: "Asia/Almaty",
    locale: "en-GB",
    trace: "off",
  },
});
