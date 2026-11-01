import { expect, test } from "@playwright/test";
import {
  SLUG, apiHoldAndBook, biz, almaty, openWizard, pickDate, pickMaster, pickService, pickSlot,
  resetRateLimits, serviceId, staffId, upcoming,
  nameField, phoneField,
} from "../lib/kz";

test("wizard books with a formatted phone", async ({ page }) => {
  const b = await biz();
  await openWizard(page);
  await pickService(page, "Women's haircut");
  await pickMaster(page, "Dana");
  await pickDate(page, upcoming(b.timezone, 3));
  await pickSlot(page, "11:00");
  await nameField(page).fill("Phone Format");
  await phoneField(page).fill("+7 (701) 555-12-34");
  await page.getByRole("button", { name: "Confirm booking" }).click();
  await expect(page.getByText("You are booked!")).toBeVisible();
});

test("API books with spaces in the phone", async ({ request }) => {
  await resetRateLimits();
  const b = await biz();
  const date = upcoming(b.timezone, 3);
  const res = await apiHoldAndBook(request, {
    serviceId: await serviceId("Men's haircut"),
    staffId: await staffId("Dana"),
    date,
    startMs: almaty(date, "15:00"),
    name: "Phone Format",
    phone: "+7 701 555 12 34",
  });
  expect(res.status, JSON.stringify(res.body)).toBe(200);
});

test("waitlist accepts dashes", async ({ request }) => {
  await resetRateLimits();
  const b = await biz();
  const res = await request.post(`/api/public/${SLUG}/waitlist`, {
    data: {
      serviceId: await serviceId("Women's haircut"),
      staffId: await staffId("Madina"),
      date: upcoming(b.timezone, 4),
      name: "Phone Format",
      phone: "+7-701-555-12-34",
    },
  });
  expect(res.status(), await res.text()).toBe(200);
});

test("non-numbers are still rejected", async ({ request }) => {
  await resetRateLimits();
  const svc = await serviceId("Women's haircut");
  const st = await staffId("Dana");
  for (const phone of ["call me maybe", "+7 701", "+7 701 555 12 34 ext 9"]) {
    const book = await request.post(`/api/public/${SLUG}/book`, {
      data: { serviceId: svc, staffId: st, startMs: 1, endMs: 2, holdToken: "x".repeat(32), name: "Nope", phone },
    });
    expect(book.status(), `book ${phone}`).toBe(400);
    const wl = await request.post(`/api/public/${SLUG}/waitlist`, {
      data: { serviceId: svc, staffId: st, date: "2030-01-02", name: "Nope", phone },
    });
    expect(wl.status(), `waitlist ${phone}`).toBe(400);
  }
});
