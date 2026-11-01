import { expect, test, type Page } from "@playwright/test";
import { OWNER, almaty, biz, formFields, insertBooking, login, q, upcoming } from "../lib/kz";

const SERVERS = ["http://localhost:3000", "http://localhost:3001"];

const status = async (id: string) => (await q<{ status: string }>("SELECT status FROM bookings WHERE id = $1", [id]))[0].status;
const audits = async (id: string) =>
  (await q<{ action: string }>("SELECT action FROM audit_log WHERE entity_id = $1 AND action LIKE 'booking.%' ORDER BY created_at", [id])).map((r) => r.action);
const outbox = async (id: string) =>
  (await q<{ dedupe_key: string }>("SELECT dedupe_key FROM outbox WHERE dedupe_key IN ($1, $2)", [`booking.cancelled:${id}`, `waitlist.freed:${id}`])).map((r) => r.dedupe_key.split(":")[0]).sort();

async function setup(page: Page, n: number, weekday: number) {
  const b = await biz();
  const date = upcoming(b.timezone, weekday);
  const ids: string[] = [];
  for (let i = 0; i < n; i++) {
    ids.push(await insertBooking({ staff: "Dana", service: "Women's haircut", startMs: almaty(date, `${10 + 2 * i}:00`), minutes: 60, client: `Status ${weekday}-${i}`, phone: `+7701880${weekday}${String(i).padStart(3, "0")}` }));
  }
  await login(page, OWNER.email, OWNER.password);
  await page.goto(`/admin?date=${date}`);
  // The form behind every status button: same action, bookingId + status fields.
  const fields = await formFields(page, `article:has-text("Status ${weekday}-0") form:has(input[name="status"][value="cancelled"])`);
  const replay = (bookingId: string, st: string, server = SERVERS[0]) =>
    page.request.post(`${server}/admin?date=${date}`, { multipart: { ...fields, bookingId, status: st }, maxRedirects: 0 });
  return { ids, date, replay };
}

test("a cancelled booking stays cancelled", async ({ page }) => {
  const { ids, replay } = await setup(page, 1, 2);
  await page.locator("article", { hasText: "Status 2-0" }).getByRole("button", { name: "Cancel" }).click();
  await expect.poll(() => status(ids[0])).toBe("cancelled");
  await replay(ids[0], "completed");
  await replay(ids[0], "no_show");
  await replay(ids[0], "cancelled");
  expect(await status(ids[0])).toBe("cancelled");
  expect(await audits(ids[0])).toEqual(["booking.cancelled"]);
  expect(await outbox(ids[0])).toEqual(["booking.cancelled", "waitlist.freed"]);
});

test("a completed booking can't be cancelled or turned into a no-show", async ({ page }) => {
  const { ids, replay } = await setup(page, 1, 3);
  await page.locator("article", { hasText: "Status 3-0" }).getByRole("button", { name: /Completed/ }).click();
  await expect.poll(() => status(ids[0])).toBe("completed");
  await replay(ids[0], "no_show");
  await replay(ids[0], "cancelled");
  await replay(ids[0], "completed");
  expect(await status(ids[0])).toBe("completed");
  expect(await audits(ids[0])).toEqual(["booking.completed"]);
  expect(await outbox(ids[0]), "no cancellation, no waitlist offer").toEqual([]);
});

test("simultaneous clicks on two servers: exactly one change wins", async ({ page }) => {
  const { ids, replay } = await setup(page, 4, 5);
  const kinds = ["completed", "no_show", "cancelled"];
  for (const id of ids) {
    await Promise.all(Array.from({ length: 9 }, (_, i) => replay(id, kinds[i % 3], SERVERS[i % 2])));
    const final = await status(id);
    expect(kinds).toContain(final);
    expect(await audits(id), `audit trail of ${id}`).toEqual([`booking.${final}`]);
    expect(await outbox(id)).toEqual(final === "cancelled" ? ["booking.cancelled", "waitlist.freed"] : []);
  }
});

test("normal use still works", async ({ page }) => {
  const { ids } = await setup(page, 1, 6);
  await page.locator("article", { hasText: "Status 6-0" }).getByRole("button", { name: "No-show" }).click();
  await expect.poll(() => status(ids[0])).toBe("no_show");
  await expect(page.locator("article", { hasText: "Status 6-0" }).getByText("no-show")).toBeVisible();
});
