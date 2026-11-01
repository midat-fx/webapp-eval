import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Locator, type Page } from "@playwright/test";
import { biz, openWizard, pickDate, pickSlot, upcoming } from "../lib/kz";

async function audit(page: Page, state: string) {
  await page.waitForTimeout(400); // let colour transitions settle
  const r = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze();
  expect(r.violations.map((v) => `${v.id} (${v.impact}): ${v.nodes.map((n) => n.target.join(" ")).join(" | ")}`), state).toEqual([]);
}

/** Whether assistive tech sees `el` as selected, whichever pattern was used. */
const selected = (el: Locator) =>
  el.evaluate((e) =>
    ["aria-pressed", "aria-checked", "aria-selected", "aria-current"].some((a) => {
      const v = e.getAttribute(a);
      return v !== null && v !== "false";
    }) || (e as HTMLInputElement).checked === true,
  );

/** Is the text inside a live region (role alert/status or aria-live)? */
const announced = (page: Page, text: string | RegExp) =>
  page.getByText(text).first().evaluate((e) => {
    for (let n: Element | null = e; n; n = n.parentElement) {
      const live = n.getAttribute("aria-live");
      if (["alert", "status", "log"].includes(n.getAttribute("role") ?? "") || (live && live !== "off")) return true;
    }
    return false;
  });

// Found by role and accessible name (decorative aria-hidden icons don't count),
// whether the fix kept toggle buttons or switched to radios / options.
const choice = (page: Page, name: RegExp) =>
  page.getByRole("button", { name }).or(page.getByRole("radio", { name })).or(page.getByRole("option", { name })).first();
const serviceButton = (page: Page, name: string) => choice(page, new RegExp(`(^|\\W)${name}`));
const staffButton = (page: Page, name: string) => choice(page, new RegExp(`^\\W*${name}\\W*$`));

/** Click a staff member and let the times it triggers land (see pickMaster in lib/kz). */
async function chooseStaff(page: Page, name: string) {
  const loaded = page.waitForResponse((r) => r.url().includes("/slots?"), { timeout: 15_000 }).catch(() => undefined);
  await staffButton(page, name).click();
  await loaded;
}

test("every wizard state passes axe", { tag: "@axe" }, async ({ page }) => {
  const b = await biz();
  await openWizard(page);
  await expect(serviceButton(page, "Women's haircut")).toBeVisible();
  await audit(page, "service list");
  await serviceButton(page, "Women's haircut").click();
  await audit(page, "staff list");
  await chooseStaff(page, "Dana");
  await pickDate(page, upcoming(b.timezone, 1)); // Monday: closed
  await expect(page.getByText(/fully booked/)).toBeVisible();
  await audit(page, "waitlist box");
  await pickDate(page, upcoming(b.timezone, 3));
  await expect(page.getByRole("button", { name: "11:00", exact: true })).toBeVisible();
  await audit(page, "date and times");
  await pickSlot(page, "11:00");
  await audit(page, "your details");
  await page.getByLabel(/name/i).first().fill("A11y Check");
  await page.getByLabel(/phone/i).first().fill("12");
  await page.getByRole("button", { name: "Confirm booking" }).click();
  await expect(page.getByText(/Check the name and phone/)).toBeVisible();
  await audit(page, "validation error");
});

test("fields have real labels and nothing visible was dropped", async ({ page }) => {
  const b = await biz();
  await openWizard(page);
  for (const [svc, min] of [["Women's haircut", 60], ["Men's haircut", 45], ["Hair coloring", 120]] as const) {
    await expect(serviceButton(page, svc)).toContainText(`${min} min`);
  }
  await serviceButton(page, "Women's haircut").click();
  await chooseStaff(page, "Dana");
  await expect(page.getByLabel(/date/i).first()).toHaveAttribute("type", "date");
  await pickDate(page, upcoming(b.timezone, 3));
  await pickSlot(page, "12:00");
  await expect(page.getByLabel(/name/i).first()).toBeEditable();
  await expect(page.getByLabel(/phone/i).first()).toHaveAttribute("type", "tel");
  await expect(page.getByText(/held for another/)).toBeVisible();
});

test("selection is exposed to assistive tech", async ({ page }) => {
  await openWizard(page);
  await serviceButton(page, "Men's haircut").click();
  expect(await selected(serviceButton(page, "Men's haircut"))).toBe(true);
  expect(await selected(serviceButton(page, "Women's haircut"))).toBe(false);
  await chooseStaff(page, "Dana");
  expect(await selected(staffButton(page, "Dana"))).toBe(true);
  await serviceButton(page, "Women's haircut").click();
  expect(await selected(serviceButton(page, "Women's haircut"))).toBe(true);
  expect(await selected(serviceButton(page, "Men's haircut"))).toBe(false);
});

test("errors are announced", async ({ page }) => {
  const b = await biz();
  await openWizard(page);
  await serviceButton(page, "Women's haircut").click();
  await chooseStaff(page, "Madina");
  await pickDate(page, upcoming(b.timezone, 3));
  await pickSlot(page, "13:00");
  await page.getByLabel(/name/i).first().fill("A11y Error");
  await page.getByLabel(/phone/i).first().fill("12");
  await page.getByRole("button", { name: "Confirm booking" }).click();
  await expect(page.getByText(/Check the name and phone/)).toBeVisible();
  expect(await announced(page, /Check the name and phone/), "booking error").toBe(true);

  await page.getByRole("button", { name: "Back" }).click();
  await pickDate(page, upcoming(b.timezone, 1));
  await expect(page.getByText(/fully booked/)).toBeVisible();
  const box = page.locator("div", { hasText: /fully booked/ }).last();
  await box.getByLabel(/name/i).fill("A11y Waitlist");
  await box.getByLabel(/phone/i).fill("12345");
  await box.getByRole("button", { name: /Join the waitlist/ }).click();
  await expect(page.getByText(/That did not work/)).toBeVisible();
  expect(await announced(page, /That did not work/), "waitlist error").toBe(true);
});
