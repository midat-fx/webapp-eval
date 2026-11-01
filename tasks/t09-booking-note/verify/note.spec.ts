import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import {
  OWNER, almaty, apiHold, apiBook, biz, login, openWizard, pickDate, pickMaster, pickService, pickSlot, q,
  resetRateLimits, serviceId, staffId, upcoming,
  nameField, phoneField,
} from "../lib/kz";

const NOTE = "Allergic to ammonia dye.\nPlease use the gentle one.";
const noteOf = async (phone: string) =>
  (await q<{ note: string | null }>(
    "SELECT b.note FROM bookings b JOIN clients c ON c.id = b.client_id WHERE c.phone = $1", [phone],
  )).map((r) => r.note);

async function toStep4(page: import("@playwright/test").Page, weekday: number, hhmm: string) {
  const b = await biz();
  await openWizard(page);
  await pickService(page, "Women's haircut");
  await pickMaster(page, "Dana");
  await pickDate(page, upcoming(b.timezone, weekday));
  await pickSlot(page, hhmm);
  await expect(page.getByRole("heading", { name: /Your details/ })).toBeVisible();
}

test("wizard: labelled note is saved as typed", async ({ page }) => {
  await toStep4(page, 3, "12:00");
  await nameField(page).fill("Note Writer");
  await phoneField(page).fill("+77013330001");
  await page.getByLabel(/note/i).fill(`  ${NOTE}  `);
  await page.getByRole("button", { name: "Confirm booking" }).click();
  await expect(page.getByText("You are booked!")).toBeVisible();
  expect(await noteOf("+77013330001")).toEqual([NOTE]);
});

test("step 4 has no accessibility violations", { tag: "@axe" }, async ({ page }) => {
  await toStep4(page, 3, "15:00");
  await expect(page.getByLabel(/note/i)).toBeVisible();
  const section = page.locator("section", { has: page.getByRole("heading", { name: /Your details/ }) });
  await page.getByLabel(/note/i).fill("Window seat, please");
  const r = await new AxeBuilder({ page }).include(await section.evaluate((el) => { el.setAttribute("data-axe", "step4"); return '[data-axe="step4"]'; }))
    .withTags(["wcag2a", "wcag2aa"]).analyze();
  expect(r.violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`)).toEqual([]);
});

test("wizard without a note stores NULL", async ({ page }) => {
  await toStep4(page, 4, "12:00");
  await nameField(page).fill("No Note");
  await phoneField(page).fill("+77013330002");
  await page.getByRole("button", { name: "Confirm booking" }).click();
  await expect(page.getByText("You are booked!")).toBeVisible();
  expect(await noteOf("+77013330002")).toEqual([null]);
});

test("API: 500 characters is the limit, blank is no note", async ({ request }) => {
  const b = await biz();
  const date = upcoming(b.timezone, 5);
  const svc = await serviceId("Women's haircut");
  const st = await staffId("Madina");
  const book = async (hhmm: string, phone: string, note: string) => {
    await resetRateLimits();
    const h = await apiHold(request, { serviceId: svc, staffId: st, date, startMs: almaty(date, hhmm) });
    expect(h.status, JSON.stringify(h.body)).toBe(200);
    return apiBook(request, { serviceId: svc, staffId: st, startMs: h.body.slot.startMs, endMs: h.body.slot.endMs, holdToken: h.body.holdToken, name: "Api Note", phone, note });
  };
  expect((await book("10:00", "+77013330003", "x".repeat(501))).status).toBe(400);
  expect(await noteOf("+77013330003")).toEqual([]);
  expect((await book("12:00", "+77013330004", "y".repeat(500))).status).toBe(200);
  expect(await noteOf("+77013330004")).toEqual(["y".repeat(500)]);
  expect((await book("14:00", "+77013330005", "   \n  ")).status).toBe(200);
  expect(await noteOf("+77013330005")).toEqual([null]);
  expect((await book("16:00", "+77013330006", '<img src=x onerror="window.__pwned=1">')).status).toBe(200);
});

test("admin calendar shows the note as plain text", async ({ page }) => {
  const b = await biz();
  await login(page, OWNER.email, OWNER.password);
  await page.goto(`/admin?date=${upcoming(b.timezone, 3)}`);
  const card = page.locator("article", { hasText: "Note Writer" });
  await expect(card).toContainText("Allergic to ammonia dye.");
  // toContainText normalises whitespace; innerText follows CSS, so a line
  // break the card collapses into a space shows up here.
  expect(await card.innerText()).toContain(NOTE);
  await page.goto(`/admin?date=${upcoming(b.timezone, 5)}`);
  await expect(page.locator("article", { hasText: "Api Note" }).filter({ hasText: "onerror" })).toHaveCount(1);
  await page.waitForTimeout(500);
  expect(await page.evaluate(() => (window as unknown as { __pwned?: number }).__pwned)).toBeUndefined();
});
