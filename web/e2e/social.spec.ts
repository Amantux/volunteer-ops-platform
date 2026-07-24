import { expect, test } from '@playwright/test';

// A full authed lifecycle flow needs a seeded session + permissions, which the
// E2E harness doesn't provision. We assert the client-side auth gate (the same
// guard used by the dashboard and site-builder admin) and that the route
// module builds and renders.
test.describe('social admin', () => {
  test('the social admin page without a token redirects to login', async ({
    page,
  }) => {
    await page.goto('/admin/social');
    await expect(page).toHaveURL(/\/login$/);
    await expect(
      page.getByRole('heading', { level: 1, name: /sign in/i }),
    ).toBeVisible();
  });
});
