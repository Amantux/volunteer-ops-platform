import { expect, test } from '@playwright/test';

// The finance admin surfaces reuse the same client-side auth gate as the
// dashboard and other admin pages: no token bounces to the sign-in page.
test.describe('donations admin', () => {
  test('the donations page without a token redirects to login', async ({
    page,
  }) => {
    await page.goto('/admin/donations');
    await expect(page).toHaveURL(/\/login$/);
    await expect(
      page.getByRole('heading', { level: 1, name: /sign in/i }),
    ).toBeVisible();
  });
});

// The public donation return page is refresh-safe and reads its capability
// token from the URL. With no token it must show a friendly state, not crash.
test.describe('donation return', () => {
  test('the return page with no token shows a friendly state', async ({
    page,
  }) => {
    await page.goto('/donate/return');
    await expect(
      page.getByRole('heading', { level: 1, name: /thank you/i }),
    ).toBeVisible();
    await expect(
      page.getByRole('heading', { level: 2, name: /nothing to confirm/i }),
    ).toBeVisible();
    await expect(
      page.getByRole('link', { name: /make a donation/i }),
    ).toBeVisible();
  });
});
