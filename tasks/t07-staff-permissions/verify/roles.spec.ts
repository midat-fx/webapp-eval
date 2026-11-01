import { expect, test, type Browser, type Page } from "@playwright/test";
import { OWNER, almaty, biz, createUser, formFields, insertBooking, login, postAction, q, staffId, serviceId, upcoming } from "../lib/kz";

const STAFF = { email: "aliya.staff@kezek.dev", password: "staff-pass-1" };
const OWNER_ONLY = ["/admin/services", "/admin/staff", "/admin/reports", "/admin/analytics", "/admin/notifications", "/admin/audit"];

async function as(browser: Browser, who: { email: string; password: string }): Promise<Page> {
  const ctx = await browser.newContext();
  const page = await ctx.newPage();
  await login(page, who.email, who.password);
  return page;
}

test.beforeAll(async () => {
  const b = await biz();
  await createUser({ ...STAFF, name: "Aliya", role: "staff", businessId: b.id });
});

test("staff cannot open owner-only pages", async ({ browser }) => {
  const page = await as(browser, STAFF);
  for (const path of OWNER_ONLY) {
    const res = await page.goto(path);
    const landed = new URL(page.url()).pathname;
    const blocked = landed !== path || [403, 404].includes(res?.status() ?? 0);
    expect(blocked, `${path}: landed on ${landed} with ${res?.status()}`).toBe(true);
    await expect(page.locator('input[name="priceKzt"]'), path).toHaveCount(0);
    await expect(page.getByText("Revenue"), path).toHaveCount(0);
  }
});

test("staff navigation only links to what staff can use", async ({ browser }) => {
  const page = await as(browser, STAFF);
  await page.goto("/admin");
  for (const path of OWNER_ONLY) await expect(page.locator(`header a[href="${path}"]`)).toHaveCount(0);
  await expect(page.locator('header a[href="/admin/clients"]')).toHaveCount(1);
});

test("replayed owner forms are refused for staff", async ({ browser }) => {
  const owner = await as(browser, OWNER);
  await owner.goto("/admin/services");
  const price = await formFields(owner, `form:has(input[name="name"][value="Women's haircut"])`);
  await owner.goto("/admin/staff");
  const madina = await staffId("Madina");
  const dana = await staffId("Dana");
  const coloring = await serviceId("Hair coloring");
  const hideMadina = await formFields(owner, `form:has(input[name="id"][value="${madina}"])`);
  const link = await formFields(owner, `form:has(input[name="staffId"][value="${dana}"]):has(input[name="serviceId"][value="${coloring}"])`);
  const addStaff = await formFields(owner, `form:has(input[name="name"][placeholder="Name"])`);

  const staff = await as(browser, STAFF);
  await postAction(staff.request, "/admin/services", { ...price, priceKzt: "1" });
  await postAction(staff.request, "/admin/staff", hideMadina);
  await postAction(staff.request, "/admin/staff", link);
  await postAction(staff.request, "/admin/staff", { ...addStaff, name: "Intruder" });

  const [svc] = await q<{ price_kzt: number }>("SELECT price_kzt FROM services WHERE name = 'Women''s haircut'");
  expect(svc.price_kzt, "price changed by staff").toBe(8000);
  const [m] = await q<{ is_active: boolean }>("SELECT is_active FROM staff WHERE name = 'Madina'");
  expect(m.is_active, "colleague hidden by staff").toBe(true);
  expect(await q("SELECT 1 FROM staff_services WHERE staff_id = $1 AND service_id = $2", [dana, coloring])).toHaveLength(0);
  expect(await q("SELECT 1 FROM staff WHERE name = 'Intruder'")).toHaveLength(0);
});

test("the same replay still works for the owner", async ({ browser }) => {
  // Proves the replay is a real submission, so a refusal above means something.
  const owner = await as(browser, OWNER);
  await owner.goto("/admin/services");
  const f = await formFields(owner, `form:has(input[name="name"][value="Hair coloring"])`);
  await postAction(owner.request, "/admin/services", { ...f, priceKzt: "26000" });
  const [svc] = await q<{ price_kzt: number }>("SELECT price_kzt FROM services WHERE name = 'Hair coloring'");
  expect(svc.price_kzt).toBe(26000);
});

test("staff can still run the day", async ({ browser }) => {
  const b = await biz();
  const date = upcoming(b.timezone, 4);
  const id = await insertBooking({ staff: "Dana", service: "Women's haircut", startMs: almaty(date, "12:00"), minutes: 60, client: "Walk In", phone: "+77016660001" });
  const page = await as(browser, STAFF);
  await page.goto(`/admin?date=${date}`);
  await page.locator("article", { hasText: "Walk In" }).getByRole("button", { name: /Completed/ }).click();
  await expect.poll(async () => (await q<{ status: string }>("SELECT status FROM bookings WHERE id = $1", [id]))[0].status).toBe("completed");
  const clients = await page.goto("/admin/clients");
  expect(clients?.status()).toBe(200);
  expect(new URL(page.url()).pathname).toBe("/admin/clients");
});

test("owner keeps every page and button", async ({ browser }) => {
  const page = await as(browser, OWNER);
  for (const path of OWNER_ONLY) {
    const res = await page.goto(path);
    expect(res?.status(), path).toBe(200);
    expect(new URL(page.url()).pathname).toBe(path);
  }
  await page.goto("/admin/services");
  const form = page.locator(`form:has(input[name="name"][value="Blow-dry"])`);
  await form.locator('input[name="priceKzt"]').fill("6500");
  await form.getByRole("button", { name: "Save" }).click();
  await expect.poll(async () => (await q<{ price_kzt: number }>("SELECT price_kzt FROM services WHERE name = 'Blow-dry'"))[0].price_kzt).toBe(6500);
});
