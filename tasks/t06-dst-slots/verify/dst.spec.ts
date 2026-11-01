import { expect, test } from "@playwright/test";
import {
  apiHold, apiSlots, openWizard, pickDate, pickMaster, pickService, q, resetRateLimits, serviceId,
  shownSlots, staffId,
} from "../lib/kz";

// Sundays (open 10:00-20:00): both clock changes in two years, two zones,
// plus an ordinary summer Sunday as a control.
const CASES: [string, string][] = [
  ["Europe/Berlin", "2027-03-28"],
  ["Europe/Berlin", "2027-10-31"],
  ["Europe/Berlin", "2028-03-26"],
  ["Europe/Berlin", "2028-10-29"],
  ["America/New_York", "2027-03-14"],
  ["America/New_York", "2027-11-07"],
  ["America/New_York", "2028-03-12"],
  ["America/New_York", "2028-11-05"],
  ["Europe/Berlin", "2027-07-04"],
];

const setZone = (tz: string) => q("UPDATE businesses SET timezone = $1 WHERE slug = 'aruzhan'", [tz]);
test.afterAll(() => setZone("Asia/Almaty"));

const local = (ms: number, tz: string) =>
  new Intl.DateTimeFormat("en-GB", { hour: "2-digit", minute: "2-digit", timeZone: tz }).format(ms);

for (const [tz, date] of CASES) {
  test(`slots follow opening hours in ${tz} on ${date}`, async ({ request }) => {
    await setZone(tz);
    await resetRateLimits();
    const p = { serviceId: await serviceId("Women's haircut"), staffId: await staffId("Dana"), date };
    const slots = await apiSlots(request, p);
    const times = slots.map((s) => local(s.startMs, tz));
    expect(times[0], "first slot").toBe("10:00");
    expect(times.at(-1), "last slot (60 min, closes 20:00)").toBe("19:00");
    expect(slots, "10:00..19:00 every 15 minutes").toHaveLength(37);
    for (const s of slots) expect(s.endMs - s.startMs).toBe(3600_000);
    expect(new Set(times).size, "no duplicated wall times").toBe(slots.length);
    const hold = await apiHold(request, { ...p, startMs: slots[0].startMs });
    expect(hold.status, JSON.stringify(hold.body)).toBe(200);
  });
}

test("wizard shows the Berlin opening time on the spring-forward day", async ({ browser }) => {
  await setZone("Europe/Berlin");
  const ctx = await browser.newContext({ timezoneId: "Europe/Berlin" });
  const page = await ctx.newPage();
  await openWizard(page);
  await pickService(page, "Women's haircut");
  await pickMaster(page, "Madina");
  await pickDate(page, "2027-03-28");
  await expect.poll(async () => (await shownSlots(page))[0]).toBe("10:00");
  expect((await shownSlots(page)).at(-1)).toBe("19:00");
  await ctx.close();
});
