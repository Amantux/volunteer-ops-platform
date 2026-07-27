import { expect, test } from '@playwright/test';

// A full authed flow needs a seeded session + `shift.manage`, which the E2E
// harness doesn't provision. We assert the client-side auth gate (the same
// guard used by the dashboard and other admin surfaces) and that the route
// module builds and renders.
test.describe('schedule admin', () => {
  test('the schedule admin page without a token redirects to login', async ({
    page,
  }) => {
    await page.goto('/admin/schedule');
    await expect(page).toHaveURL(/\/login$/);
    await expect(
      page.getByRole('heading', { level: 1, name: /sign in/i }),
    ).toBeVisible();
  });
});
