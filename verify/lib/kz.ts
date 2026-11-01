// Shared helpers for the hidden verifiers. They talk to the app the way a
// user does (browser, public HTTP API) and inspect Postgres/Redis directly
// only to arrange fixtures and to read back state.
import { expect, type APIRequestContext, type Page } from "@playwright/test";
import bcrypt from "bcryptjs";
import Redis from "ioredis";
import pg from "pg";

export const SLUG = "aruzhan";
export const OWNER = { email: "owner@kezek.dev", password: "kezek-demo" };

const pool = new pg.Pool({ connectionString: process.env.DATABASE_URL, max: 4 });
export async function q<T = Record<string, unknown>>(text: string, params: unknown[] = []): Promise<T[]> {
  return (await pool.query(text, params)).rows as T[];
}

let _redis: Redis | undefined;
export function redis(): Redis {
  _redis ??= new Redis(process.env.REDIS_URL ?? "redis://127.0.0.1:6379");
  return _redis;
}

/** Public endpoints are rate limited per IP; verifiers are one IP doing a lot. */
export async function resetRateLimits(): Promise<void> {
  const keys = await redis().keys("rl:*");
  if (keys.length) await redis().del(...keys);
}

export type Biz = { id: string; timezone: string };
export async function biz(): Promise<Biz> {
  const [b] = await q<Biz>("SELECT id, timezone FROM businesses WHERE slug = $1", [SLUG]);
  return b;
}

export async function staffId(name: string): Promise<string> {
  const [r] = await q<{ id: string }>("SELECT id FROM staff WHERE name = $1", [name]);
  return r.id;
}
export async function serviceId(name: string): Promise<string> {
  const [r] = await q<{ id: string }>("SELECT id FROM services WHERE name = $1", [name]);
  return r.id;
}

/** Local YYYY-MM-DD in `tz`, `days` from now. */
export function localDate(tz: string, days = 0, from = Date.now()): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: tz }).format(new Date(from + days * 86_400_000));
}

/**
 * A business-local date at least `minDays` ahead that falls on `weekday`
 * (ISO, 1 = Monday). The seed only books up to 3 days ahead, so a week out
 * every master's day is empty.
 */
export function upcoming(tz: string, weekday: number, minDays = 8): string {
  for (let d = minDays; d < minDays + 7; d++) {
    const iso = localDate(tz, d);
    const [y, m, dd] = iso.split("-").map(Number);
    const dow = new Date(Date.UTC(y, m - 1, dd)).getUTCDay() || 7;
    if (dow === weekday) return iso;
  }
  throw new Error("unreachable");
}

/** UTC epoch ms of local wall time on a local date (fixed-offset zones only). */
export function almaty(dateISO: string, hhmm: string): number {
  return Date.parse(`${dateISO}T${hhmm}:00+05:00`);
}

export function fmtLocal(ms: number, tz: string): string {
  return new Intl.DateTimeFormat("en-GB", { hour: "2-digit", minute: "2-digit", timeZone: tz }).format(ms);
}

export async function createUser(u: {
  email: string;
  password: string;
  name: string;
  role: "owner" | "staff";
  businessId: string;
}): Promise<string> {
  const hash = await bcrypt.hash(u.password, 4);
  const [r] = await q<{ id: string }>(
    `INSERT INTO users (email, password_hash, name, role, business_id) VALUES ($1, $2, $3, $4, $5)
     ON CONFLICT (email) DO UPDATE SET password_hash = EXCLUDED.password_hash RETURNING id`,
    [u.email, hash, u.name, u.role, u.businessId],
  );
  return r.id;
}

export async function login(page: Page, email: string, password: string): Promise<void> {
  await resetRateLimits();
  await page.goto("/login");
  await page.locator('input[name="email"]').fill(email);
  await page.locator('input[name="password"]').fill(password);
  await page.locator('button[type="submit"], form button').first().click();
  await page.waitForURL(/\/admin/);
}

// ---------- public booking wizard ----------

export async function openWizard(page: Page): Promise<void> {
  await resetRateLimits();
  await page.goto(`/${SLUG}`);
}
export async function pickService(page: Page, name: string): Promise<void> {
  await page.getByRole("button", { name: new RegExp(`^${name}`) }).click();
}
export async function pickMaster(page: Page, name: string): Promise<void> {
  await page.getByRole("button", { name, exact: true }).click();
}
export async function pickDate(page: Page, iso: string): Promise<void> {
  await page.locator('input[type="date"]').first().fill(iso);
}
export async function pickSlot(page: Page, hhmm: string): Promise<void> {
  await page.getByRole("button", { name: hhmm, exact: true }).click();
}

// ---------- public HTTP API ----------

export type Slot = { startMs: number; endMs: number };

export async function apiSlots(
  request: APIRequestContext,
  p: { serviceId: string; staffId: string; date: string },
  base = "",
): Promise<Slot[]> {
  const res = await request.get(
    `${base}/api/public/${SLUG}/slots?serviceId=${p.serviceId}&staffId=${p.staffId}&date=${p.date}`,
  );
  expect(res.status(), await res.text()).toBe(200);
  return (await res.json()).slots;
}

export async function apiHold(
  request: APIRequestContext,
  p: { serviceId: string; staffId: string; date: string; startMs: number },
  base = "",
) {
  const res = await request.post(`${base}/api/public/${SLUG}/hold`, { data: p });
  return { status: res.status(), body: await res.json().catch(() => ({})) };
}

export async function apiBook(
  request: APIRequestContext,
  p: {
    serviceId: string;
    staffId: string;
    startMs: number;
    endMs: number;
    holdToken: string;
    name: string;
    phone: string;
    [k: string]: unknown;
  },
  base = "",
) {
  const res = await request.post(`${base}/api/public/${SLUG}/book`, { data: p });
  return { status: res.status(), body: await res.json().catch(() => ({})) };
}

/** Hold then book in one go; returns the /book response. */
export async function apiHoldAndBook(
  request: APIRequestContext,
  p: { serviceId: string; staffId: string; date: string; startMs: number; name: string; phone: string },
) {
  const h = await apiHold(request, p);
  expect(h.status, JSON.stringify(h.body)).toBe(200);
  return apiBook(request, {
    serviceId: p.serviceId,
    staffId: p.staffId,
    startMs: h.body.slot.startMs,
    endMs: h.body.slot.endMs,
    holdToken: h.body.holdToken,
    name: p.name,
    phone: p.phone,
  });
}

// ---------- server actions ----------

/**
 * Replays a server-action form the way the browser would submit it, but with
 * whatever field values we like. Grabs the action's hidden inputs from a form
 * on a page the *owner* can see, then posts them with another session's
 * cookies — exactly what a curious staff member with devtools can do.
 */
export async function formFields(page: Page, formSelector: string): Promise<Record<string, string>> {
  return page.locator(formSelector).first().evaluate((form) => {
    // A form with a `formAction` button carries a second $ACTION_ID input;
    // the first one is the form's own action.
    const out: Record<string, string> = {};
    let seenAction = false;
    for (const el of Array.from((form as HTMLFormElement).elements) as HTMLInputElement[]) {
      if (!el.name) continue;
      if (el.name.startsWith("$ACTION_ID_")) {
        if (seenAction) continue;
        seenAction = true;
      }
      out[el.name] = el.value;
    }
    return out;
  });
}

export async function postAction(
  request: APIRequestContext,
  path: string,
  fields: Record<string, string>,
): Promise<number> {
  const res = await request.post(path, { multipart: fields, maxRedirects: 0 });
  return res.status();
}
