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

test.describe('public content pages', () => {
  test('opportunities renders its h1', async ({ page }) => {
    await page.goto('/opportunities');
    await expect(
      page.getByRole('heading', { level: 1, name: /find a way to help/i }),
    ).toBeVisible();
  });

  test('calendar renders its h1', async ({ page }) => {
    await page.goto('/calendar');
    await expect(
      page.getByRole('heading', { level: 1, name: /what.?s coming up/i }),
    ).toBeVisible();
  });

  // About/FAQ/Contact are now CMS-managed pages served via /[slug]. Assert they render an h1
  // (content is editable, so don't pin exact copy) plus the FAQ toggle and Contact mailto.
  test('about (CMS) renders an h1', async ({ page }) => {
    await page.goto('/about');
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
  });

  test('faq (CMS) renders and answers are keyboard-toggleable', async ({
    page,
  }) => {
    await page.goto('/faq');
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible();

    // Native <details> disclosure: focus the first summary and toggle it open.
    const firstSummary = page.locator('details > summary').first();
    await firstSummary.focus();
    await expect(firstSummary).toBeFocused();
    await page.keyboard.press('Enter');
    await expect(page.locator('details').first()).toHaveAttribute('open', '');
  });

  test('contact (CMS) renders an h1 and a mailto CTA', async ({ page }) => {
    await page.goto('/contact');
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
    await expect(
      page.getByRole('link', {
        name: /email contact@gofidog\.org/i,
      }),
    ).toBeVisible();
  });
});

test.describe('public pages accessibility', () => {
  test('about has no serious a11y violations', async ({ page }) => {
    await page.goto('/about');
    await expectNoSeriousA11yViolations(page);
  });

  test('faq has no serious a11y violations', async ({ page }) => {
    await page.goto('/faq');
    await expectNoSeriousA11yViolations(page);
  });

  test('calendar has no serious a11y violations', async ({ page }) => {
    await page.goto('/calendar');
    await expectNoSeriousA11yViolations(page);
  });
});
