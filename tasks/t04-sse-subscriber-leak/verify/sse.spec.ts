import { expect, test, type BrowserContext, type Page } from "@playwright/test";
import { OWNER, almaty, apiHoldAndBook, biz, login, redis, resetRateLimits, serviceId, staffId, upcoming } from "../lib/kz";

async function redisState(bizId: string) {
  const [, subs] = (await redis().pubsub("NUMSUB", `calendar:${bizId}`)) as [string, number];
  const clients = String(await redis().client("LIST")).trim().split("\n").length;
  return { subs: Number(subs), clients };
}

/** Opens the calendar in a new tab and waits until its event stream is connected. */
async function openCalendar(ctx: BrowserContext, date: string): Promise<Page> {
  const page = await ctx.newPage();
  const stream = page.waitForResponse((r) => r.url().includes("/api/admin/events"));
  await page.goto(`/admin?date=${date}`);
  await stream;
  await page.waitForTimeout(300);
  return page;
}

test("closed tabs release their Redis subscriber and connection", async ({ browser }) => {
  const b = await biz();
  const ctx = await browser.newContext();
  const first = await ctx.newPage();
  await login(first, OWNER.email, OWNER.password);
  const date = upcoming(b.timezone, 3);
  const keeper = await openCalendar(ctx, date);
  await first.close();
  await expect.poll(() => redisState(b.id).then((s) => s.subs), { timeout: 5000 }).toBeLessThanOrEqual(1);
  const base = await redisState(b.id);

  // Chromium allows 6 HTTP/1.1 connections per host and every open stream
  // holds one, so stay below that: the keeper plus 4 tabs per round.
  for (let round = 0; round < 3; round++) {
    const tabs = [];
    for (let i = 0; i < 4; i++) tabs.push(await openCalendar(ctx, date));
    for (const t of tabs) await t.close();
    await expect
      .poll(() => redisState(b.id), { timeout: 6000, message: `after closing 4 tabs (round ${round + 1})` })
      .toEqual(expect.objectContaining({ subs: base.subs }));
    await expect.poll(() => redisState(b.id).then((s) => s.clients), { timeout: 6000 }).toBeLessThanOrEqual(base.clients);
  }
  await keeper.close();
  await ctx.close();
});

test("open calendar still updates live, also after other tabs closed", async ({ browser, request }) => {
  const b = await biz();
  const ctx = await browser.newContext();
  const first = await ctx.newPage();
  await login(first, OWNER.email, OWNER.password);
  const date = upcoming(b.timezone, 4);
  const watcher = await openCalendar(ctx, date);
  for (let i = 0; i < 3; i++) await (await openCalendar(ctx, date)).close();
  await first.close();

  await resetRateLimits();
  const res = await apiHoldAndBook(request, {
    serviceId: await serviceId("Women's haircut"),
    staffId: await staffId("Madina"),
    date,
    startMs: almaty(date, "16:00"),
    name: "Live Update",
    phone: "+77014440001",
  });
  expect(res.status, JSON.stringify(res.body)).toBe(200);
  await expect(watcher.getByText("Live Update")).toBeVisible({ timeout: 8000 });

  // The server survived publishing to streams whose tabs are gone.
  expect((await request.get("/login")).status()).toBe(200);
  await ctx.close();
});
