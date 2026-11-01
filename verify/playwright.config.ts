import { defineConfig } from "@playwright/test";

// Hidden verifiers for one task are copied into ./specs right before they run.
export default defineConfig({
  testDir: "./specs",
  workers: 1,
  retries: 0,
  timeout: 90_000,
  expect: { timeout: 10_000 },
  reporter: [["json", { outputFile: process.env.PW_JSON ?? "playwright.json" }], ["list"]],
  use: {
    baseURL: "http://localhost:3000",
    timezoneId: "Asia/Almaty",
    locale: "en-GB",
    trace: "off",
  },
});
