import { expect, test } from '@playwright/test';

// The kiosk admin manager reuses the same client-side auth gate as the other
// admin surfaces: no token bounces to the sign-in page. (The public kiosk
// display at /kiosk/[token] is intentionally NOT gated — the URL token is the
// capability — so it is not covered here.)
test.describe('kiosk admin', () => {
  test('the kiosks page without a token redirects to login', async ({
    page,
  }) => {
    await page.goto('/admin/kiosks');
    await expect(page).toHaveURL(/\/login$/);
    await expect(
      page.getByRole('heading', { level: 1, name: /sign in/i }),
    ).toBeVisible();
  });
});
