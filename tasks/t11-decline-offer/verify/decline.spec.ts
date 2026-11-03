import { spawn, type ChildProcess } from "node:child_process";
import { readFileSync } from "node:fs";
import { expect, test, type APIRequestContext, type Page } from "@playwright/test";
import { OWNER, almaty, apiSlots, biz, insertBooking, login, q, serviceId, staffId, upcoming } from "../lib/kz";

const APP = "/opt/kezek";
const SERVICE = "Women's haircut";
const workers: ChildProcess[] = [];

// Two outbox workers, started the way the app's own `worker` script starts one.
test.beforeAll(() => {
  const cmd = JSON.parse(readFileSync(`${APP}/package.json`, "utf8")).scripts.worker;
  for (let i = 0; i < 2; i++) {
    workers.push(spawn("sh", ["-c", cmd], {
      cwd: APP, detached: true, stdio: "ignore",
      env: { ...process.env, PATH: `${APP}/node_modules/.bin:${process.env.PATH}` },
    }));
  }
});
test.afterAll(() => {
  for (const w of workers) try { process.kill(-w.pid!, "SIGTERM"); } catch { /* already gone */ }
});

/** A client waiting for `date`, any master; `minutesAgo` sets their place in the queue. */
async function waiting(phone: string, date: string, minutesAgo: number): Promise<void> {
  const b = await biz();
  const [c] = await q<{ id: string }>(
    `INSERT INTO clients (business_id, name, phone) VALUES ($1, $2, $3)
     ON CONFLICT (business_id, phone) DO UPDATE SET name = EXCLUDED.name RETURNING id`,
    [b.id, `Waiting ${phone.slice(-4)}`, phone],
  );
  await q(
    `INSERT INTO waitlist_entries (business_id, service_id, client_id, date_iso, created_at)
     VALUES ($1, $2, $3, $4, now() - ($5 || ' minutes')::interval)`,
    [b.id, await serviceId(SERVICE), c.id, date, String(minutesAgo)],
  );
}

/** Offer links sent to `phone` by SMS so far, oldest first. */
const offers = async (phone: string) =>
  (await q<{ body: string }>("SELECT body FROM message_log WHERE recipient = $1 AND body LIKE '%/w/%' ORDER BY created_at", [phone]))
    .map((r) => r.body.match(/\/w\/[A-Za-z0-9_-]+/)![0]);

async function offerLink(phone: string): Promise<string> {
  await expect.poll(async () => (await offers(phone)).length, { message: `offer SMS to ${phone}`, timeout: 30_000 }).toBeGreaterThan(0);
  return (await offers(phone)).at(-1)!;
}

/** A confirmed 12:00 booking with Dana, cancelled by the owner on the calendar. */
async function cancelledSlot(page: Page, date: string, client: string, phone: string): Promise<number> {
  const start = almaty(date, "12:00");
  const id = await insertBooking({ staff: "Dana", service: SERVICE, startMs: start, minutes: 60, client, phone });
  await login(page, OWNER.email, OWNER.password);
  await page.goto(`/admin?date=${date}`);
  await page.locator("article", { hasText: client }).getByRole("button", { name: /^Cancel$/ }).click();
  await expect.poll(async () => (await q<{ status: string }>("SELECT status FROM bookings WHERE id = $1", [id]))[0].status).toBe("cancelled");
  await page.context().clearCookies();
  return start;
}

const claimButton = (page: Page) => page.getByRole("button", { name: /claim/i });
const noThanks = (page: Page) => page.getByRole("button", { name: /no thanks/i });

/** What the No thanks button submits, so it can be sent again from elsewhere. */
const declineFields = (page: Page) =>
  noThanks(page).evaluate((btn) => {
    const b = btn as HTMLButtonElement;
    const out: Record<string, string> = {};
    const own = b.name.startsWith("$ACTION_ID_");
    for (const el of Array.from(b.form!.elements) as HTMLInputElement[]) {
      if (!el.name || el === (b as unknown) || (own && el.name.startsWith("$ACTION_ID_"))) continue;
      out[el.name] = el.value;
    }
    if (own) out[b.name] = b.value;
    return out;
  });

const bookedBy = async (phone: string, start: number) =>
  (await q("SELECT 1 FROM bookings b JOIN clients c ON c.id = b.client_id WHERE c.phone = $1 AND b.start_at = $2 AND b.status = 'confirmed'",
    [phone, new Date(start)])).length;

async function claim(page: Page, link: string, phone: string, start: number) {
  await page.goto(link);
  await claimButton(page).click();
  await expect.poll(() => bookedBy(phone, start), `${phone} booked the time`).toBe(1);
}

const isOnSale = async (request: APIRequestContext, date: string, start: number) =>
  (await apiSlots(request, { serviceId: await serviceId(SERVICE), staffId: await staffId("Dana"), date })).some((s) => s.startMs === start);

test("No thanks hands the time to the next client in the queue", async ({ page }) => {
  const b = await biz();
  const date = upcoming(b.timezone, 3);
  await waiting("+77015550111", date, 30);
  await waiting("+77015550112", date, 20);
  const start = await cancelledSlot(page, date, "Cancels Wed", "+77015550101");

  const first = await offerLink("+77015550111");
  await page.goto(first);
  await noThanks(page).click();
  await page.waitForLoadState("networkidle");

  const next = await offerLink("+77015550112");
  await page.goto(first);
  await expect(claimButton(page), "the declined link still offers the slot").toHaveCount(0);
  await claim(page, next, "+77015550112", start);
  expect(await offers("+77015550111"), "offered again to the client who declined").toHaveLength(1);
  expect(await bookedBy("+77015550111", start)).toBe(0);
});

test("with nobody else waiting the time is back on sale at once", async ({ page, request }) => {
  const b = await biz();
  const date = upcoming(b.timezone, 4);
  await waiting("+77015550211", date, 30);
  const start = await cancelledSlot(page, date, "Cancels Thu", "+77015550201");

  const link = await offerLink("+77015550211");
  expect(await isOnSale(request, date, start), "held for the offer").toBe(false);
  await page.goto(link);
  await noThanks(page).click();
  await expect.poll(() => isOnSale(request, date, start), { message: "back on sale", timeout: 10_000 }).toBe(true);
});

test("a double tap across two servers declines once", async ({ page }) => {
  const b = await biz();
  const date = upcoming(b.timezone, 5);
  await waiting("+77015550311", date, 30);
  await waiting("+77015550312", date, 20);
  await waiting("+77015550313", date, 10);
  const start = await cancelledSlot(page, date, "Cancels Fri", "+77015550301");

  const link = await offerLink("+77015550311");
  await page.goto(link);
  const fields = await declineFields(page);
  await Promise.all(
    Array.from({ length: 6 }, (_, i) =>
      page.request.post(`http://localhost:${3000 + (i % 2)}${link}`, { multipart: fields, maxRedirects: 0 })),
  );

  const next = await offerLink("+77015550312");
  await page.waitForTimeout(8_000); // four worker polls for a second offer to show up
  expect(await offers("+77015550312"), "offers to the next client").toHaveLength(1);
  expect(await offers("+77015550313"), "offers to the client after them").toHaveLength(0);
  await claim(page, next, "+77015550312", start);
});

test("No thanks after claiming changes nothing", async ({ page }) => {
  const b = await biz();
  const date = upcoming(b.timezone, 2);
  await waiting("+77015550411", date, 30);
  await waiting("+77015550412", date, 20);
  const start = await cancelledSlot(page, date, "Cancels Tue", "+77015550401");

  const link = await offerLink("+77015550411");
  await page.goto(link);
  const fields = await declineFields(page);
  await claim(page, link, "+77015550411", start);
  await page.request.post(`http://localhost:3001${link}`, { multipart: fields, maxRedirects: 0 });

  await page.waitForTimeout(8_000);
  expect(await bookedBy("+77015550411", start), "the booking stays").toBe(1);
  expect(await offers("+77015550412"), "offered a booked time").toHaveLength(0);
});
