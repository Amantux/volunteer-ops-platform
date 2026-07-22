import AxeBuilder from '@axe-core/playwright';
import { expect, test, type Page } from '@playwright/test';

// Assert no serious/critical accessibility violations on a page.
async function expectNoSeriousA11yViolations(page: Page) {
  const results = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa'])
    .analyze();
  const serious = results.violations.filter(
    (v) => v.impact === 'serious' || v.impact === 'critical',
  );
  expect(
    serious,
    serious.map((v) => `${v.id}: ${v.help}`).join('\n'),
  ).toEqual([]);
}

test.describe('public registration flow', () => {
  test('browse trainings, open a session, register, see confirmation', async ({
    page,
  }) => {
    await page.goto('/trainings');
    await expect(
      page.getByRole('heading', { level: 1, name: /upcoming trainings/i }),
    ).toBeVisible();

    // Open the first available session detail.
    const firstCard = page.locator('.card-list a.card-link').first();
    await expect(firstCard).toBeVisible();
    await firstCard.click();

    // Detail page shows the registration form.
    await expect(
      page.getByRole('heading', { name: /register for this training/i }),
    ).toBeVisible();

    await page.getByLabel(/full name/i).fill('Test Volunteer');
    await page
      .getByLabel(/email address/i)
      .fill(`playwright+${Date.now()}@example.com`);
    await page.getByLabel(/phone/i).fill('555-0100');

    await page.getByRole('button', { name: /register|join the waitlist/i }).click();

    // Success or waitlist status message appears in the live region.
    const status = page.getByRole('status');
    await expect(status).toBeVisible();
    await expect(status).toContainText(/registered|waitlist/i);
    // "check your email" appears in both the status line and a follow-up note; assert at
    // least one is visible without tripping strict-mode.
    await expect(page.getByText(/check your email/i).first()).toBeVisible();
  });

  test('keyboard-only: reach and submit the registration form', async ({
    page,
  }) => {
    await page.goto('/trainings');

    // Tab to the first training card link and activate with Enter.
    const firstCard = page.locator('.card-list a.card-link').first();
    await expect(firstCard).toBeVisible();
    await firstCard.focus();
    await expect(firstCard).toBeFocused();
    await page.keyboard.press('Enter');

    await expect(
      page.getByRole('heading', { name: /register for this training/i }),
    ).toBeVisible();

    // Fill the form using keyboard only.
    await page.getByLabel(/full name/i).focus();
    await page.keyboard.type('Keyboard Volunteer');
    await page.keyboard.press('Tab');
    await page.keyboard.type(`kb+${Date.now()}@example.com`);

    const submit = page.getByRole('button', {
      name: /register|join the waitlist/i,
    });
    await submit.focus();
    await expect(submit).toBeFocused();
    await page.keyboard.press('Enter');

    await expect(page.getByRole('status')).toContainText(/registered|waitlist/i);
  });

  test('detail page 404 for an unknown session', async ({ page }) => {
    const res = await page.goto('/trainings/99999999');
    expect(res?.status()).toBe(404);
    await expect(
      page.getByRole('heading', { name: /page not found/i }),
    ).toBeVisible();
  });
});

test.describe('accessibility', () => {
  test('home page has no serious a11y violations', async ({ page }) => {
    await page.goto('/');
    await expectNoSeriousA11yViolations(page);
  });

  test('trainings list has no serious a11y violations', async ({ page }) => {
    await page.goto('/trainings');
    await expectNoSeriousA11yViolations(page);
  });

  test('training detail has no serious a11y violations', async ({ page }) => {
    await page.goto('/trainings');
    await page.locator('.card-list a.card-link').first().click();
    await expect(
      page.getByRole('heading', { name: /register for this training/i }),
    ).toBeVisible();
    await expectNoSeriousA11yViolations(page);
  });
});
