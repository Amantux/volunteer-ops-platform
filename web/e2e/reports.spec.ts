import { expect, test } from '@playwright/test';

// The hours & impact report reuses the same client-side auth gate as the
// dashboard and other admin surfaces: no token bounces to the sign-in page.
test.describe('reports admin', () => {
  test('the reports page without a token redirects to login', async ({
    page,
  }) => {
    await page.goto('/admin/reports');
    await expect(page).toHaveURL(/\/login$/);
    await expect(
      page.getByRole('heading', { level: 1, name: /sign in/i }),
    ).toBeVisible();
  });
});
