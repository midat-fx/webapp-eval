import { expect, test } from "@playwright/test";
import { localDate, openWizard, pickMaster, pickService, q } from "../lib/kz";

// Offsets far enough apart that, at any instant, some of these zones are on a
// different calendar day than UTC, than Almaty, and than the visitor.
const ZONES = ["Etc/GMT+12", "Etc/GMT-14", "Asia/Almaty", "America/Los_Angeles", "Pacific/Kiritimati"];

test.afterAll(async () => {
  await q("UPDATE businesses SET timezone = 'Asia/Almaty' WHERE slug = 'aruzhan'");
});

for (const zone of ZONES) {
  test(`opens on the business's today in ${zone}`, async ({ browser }) => {
    await q("UPDATE businesses SET timezone = $1 WHERE slug = 'aruzhan'", [zone]);
    // The visitor is somewhere else entirely.
    const ctx = await browser.newContext({ timezoneId: "America/Sao_Paulo" });
    const page = await ctx.newPage();
    const before = localDate(zone);
    await openWizard(page);
    await pickService(page, "Women's haircut");
    const slotsRequest = page.waitForRequest(/\/slots\?/);
    await pickMaster(page, "Dana");
    const requested = new URL((await slotsRequest).url()).searchParams.get("date");
    const after = localDate(zone);
    const today = [before, after];

    const input = page.locator('input[type="date"]').first();
    expect(today, "pre-selected date").toContain(await input.inputValue());
    expect(today, "earliest allowed date").toContain(await input.getAttribute("min"));
    expect(today, "date the times were loaded for").toContain(requested);
    await ctx.close();
  });
}
