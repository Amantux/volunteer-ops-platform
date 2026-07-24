import AxeBuilder from '@axe-core/playwright';
import { expect, test, type Page } from '@playwright/test';

// Assert no serious/critical accessibility violations on a page (matches the
// bar used by the public registration suite).
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

test.describe('authentication', () => {
  test('login page renders the email form and confirms on submit', async ({
    page,
  }) => {
    await page.goto('/login');

    await expect(
      page.getByRole('heading', { level: 1, name: /sign in/i }),
    ).toBeVisible();

    await page
      .getByLabel(/email address/i)
      .fill(`playwright+${Date.now()}@example.com`);
    await page.getByRole('button', { name: /send sign-in link/i }).click();

    // The response is intentionally neutral (never reveals if the account exists).
    const status = page.getByRole('status');
    await expect(status).toBeVisible();
    await expect(status).toContainText(/sign-in link|check your email/i);
  });

  test('invalid sign-in link shows an expired/invalid error', async ({
    page,
  }) => {
    await page.goto('/login?token=bogus-token-value');

    await expect(
      page.getByText(/invalid or has expired/i),
    ).toBeVisible();
    // And offers a way to request a fresh link.
    await expect(
      page.getByRole('button', { name: /send sign-in link/i }),
    ).toBeVisible();
  });

  test('dashboard without a token redirects to login', async ({ page }) => {
    await page.goto('/dashboard');
    await expect(page).toHaveURL(/\/login$/);
    await expect(
      page.getByRole('heading', { level: 1, name: /sign in/i }),
    ).toBeVisible();
  });
});

test.describe('accessibility', () => {
  test('login page has no serious a11y violations', async ({ page }) => {
    await page.goto('/login');
    await expect(
      page.getByRole('heading', { level: 1, name: /sign in/i }),
    ).toBeVisible();
    await expectNoSeriousA11yViolations(page);
  });
});
