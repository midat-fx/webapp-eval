import { expect, test, type Page } from "@playwright/test";
import {
  almaty, biz, insertBooking, openWizard, pickDate, pickMaster, pickService, q, shownSlots, staffId, upcoming,
} from "../lib/kz";

/** Delay /slots responses that match `when` by `ms`. */
async function delaySlots(page: Page, ms: number, when: (u: URL) => boolean) {
  await page.route("**/api/public/*/slots?*", async (route) => {
    if (when(new URL(route.request().url()))) await new Promise((r) => setTimeout(r, ms));
    await route.continue();
  });
}

// [delay, weekday of the first pick, weekday of the second pick]
for (const [delay, dayA, dayB] of [[2500, 2, 3], [1200, 7, 6]]) {
  test(`late response for the previous date is ignored (${delay} ms)`, async ({ page }) => {
    const b = await biz();
    const dateA = upcoming(b.timezone, dayA); // empty day: first slot 10:00
    const dateB = upcoming(b.timezone, dayB); // Dana busy 10:00-14:00: first slot 14:00
    const tag = `+7701777${delay}`.slice(0, 12);
    await insertBooking({ staff: "Dana", service: "Hair coloring", startMs: almaty(dateB, "10:00"), minutes: 240, client: "Busy Morning", phone: `${tag}1` });

    await delaySlots(page, delay, (u) => u.searchParams.get("date") === dateA);
    await openWizard(page);
    await pickService(page, "Women's haircut");
    await pickMaster(page, "Dana");
    await pickDate(page, dateA, { waitForSlots: false });
    await page.waitForTimeout(500);
    // The issue requires changing the selection while times are loading.
    await expect(page.locator('input[type="date"]')).toBeEnabled({ timeout: 200 });
    await pickDate(page, dateB, { waitForSlots: false });
    await expect.poll(async () => (await shownSlots(page))[0]).toBe("14:00");
    await page.waitForTimeout(delay + 800);
    const shown = await shownSlots(page);
    expect(shown[0], "grid must still show the second date").toBe("14:00");
    expect(shown).not.toContain("10:00");

    // Booking from that grid lands on the day that is selected.
    await page.getByRole("button", { name: "14:00", exact: true }).click();
    await page.getByPlaceholder("Name").fill("Stale Check");
    await page.getByPlaceholder("+7701…").fill(`${tag}2`);
    await page.getByRole("button", { name: "Confirm booking" }).click();
    await expect(page.getByText("You are booked!")).toBeVisible();
    const rows = await q<{ start_at: Date }>(
      "SELECT b.start_at FROM bookings b JOIN clients c ON c.id = b.client_id WHERE c.phone = $1",
      [`${tag}2`],
    );
    expect(rows.map((r) => r.start_at.getTime())).toEqual([almaty(dateB, "14:00")]);
  });
}

test("late response for the previous staff member is ignored", async ({ page }) => {
  const b = await biz();
  const date = upcoming(b.timezone, 5);
  await insertBooking({ staff: "Madina", service: "Hair coloring", startMs: almaty(date, "10:00"), minutes: 120, client: "Busy Madina", phone: "+77017770003" });
  const dana = await staffId("Dana");

  await openWizard(page);
  await pickService(page, "Women's haircut");
  await pickMaster(page, "Madina");
  await pickDate(page, date, { waitForSlots: false });
  await expect.poll(async () => (await shownSlots(page))[0]).toBe("12:00");
  await delaySlots(page, 2000, (u) => u.searchParams.get("staffId") === dana);
  await pickMaster(page, "Dana", { waitForSlots: false });
  await page.waitForTimeout(500);
  await expect(page.getByRole("button", { name: "Madina", exact: true })).toBeEnabled({ timeout: 200 });
  await pickMaster(page, "Madina", { waitForSlots: false });
  await expect.poll(async () => (await shownSlots(page))[0]).toBe("12:00");
  await page.waitForTimeout(2600);
  expect((await shownSlots(page))[0], "grid must show Madina's day").toBe("12:00");
});

test("plain selection still loads times", async ({ page }) => {
  const b = await biz();
  await openWizard(page);
  await pickService(page, "Men's haircut");
  await pickMaster(page, "Dana");
  await pickDate(page, upcoming(b.timezone, 4));
  await expect.poll(async () => (await shownSlots(page))[0]).toBe("10:00");
});
