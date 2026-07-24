import { expect, test } from '@playwright/test';

test.describe('public dynamic form', () => {
  test('incident report form renders its heading and category select', async ({
    page,
  }) => {
    await page.goto('/forms/incident_report');
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
    // The incident report schema includes a category select (combobox role).
    await expect(page.getByRole('combobox').first()).toBeVisible();
  });
});

test.describe('reviewer inbox', () => {
  // The authed inbox reuses the same client-side auth gate as the dashboard /
  // social admin: no token bounces to the sign-in page.
  test('the requests page without a token redirects to login', async ({
    page,
  }) => {
    await page.goto('/admin/requests');
    await expect(page).toHaveURL(/\/login$/);
    await expect(
      page.getByRole('heading', { level: 1, name: /sign in/i }),
    ).toBeVisible();
  });
});
