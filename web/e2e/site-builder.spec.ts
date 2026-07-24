import AxeBuilder from '@axe-core/playwright';
import { expect, test, type Page } from '@playwright/test';

// These specs assume the FastAPI backend is reachable (see playwright.config.ts)
// and has a PUBLISHED CMS page seeded at the slug `our-story`.
const SLUG = '/our-story';

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

test.describe('CMS site builder — public rendering', () => {
  test('a published page renders at its slug with a heading', async ({
    page,
  }) => {
    await page.goto(SLUG);
    // The scoped content container is always present on a rendered page.
    await expect(page.locator('[id^="page-"]').first()).toBeVisible();
    await expect(page.getByRole('heading').first()).toBeVisible();
  });

  test('a published page has no serious a11y violations', async ({ page }) => {
    await page.goto(SLUG);
    await expectNoSeriousA11yViolations(page);
  });

  // XSS containment — the important one. The public renderer must never let
  // content execute script: sanitized html/paragraph fields carry no <script>,
  // and any embed is confined to a sandboxed iframe (opaque origin).
  test('rendered page content executes no script', async ({ page }) => {
    let dialogFired = false;
    page.on('dialog', (d) => {
      dialogFired = true;
      void d.dismiss();
    });

    await page.goto(SLUG);
    await expect(page.locator('[id^="page-"]').first()).toBeVisible();

    // No <script> element injected from page content into the scoped container.
    const contentScripts = await page
      .locator('[id^="page-"] script')
      .count();
    expect(contentScripts).toBe(0);

    // No content-injected global (a classic marker for successful XSS).
    const injectedMarker = await page.evaluate(
      () =>
        (window as unknown as Record<string, unknown>).__xss__ ??
        (window as unknown as Record<string, unknown>).xssPwned ??
        null,
    );
    expect(injectedMarker).toBeNull();

    // Any embed lives in a sandboxed iframe with NO allow-same-origin, so its
    // scripts cannot reach the parent. Assert that invariant if one exists.
    const frames = page.locator('[id^="page-"] iframe');
    const frameCount = await frames.count();
    for (let i = 0; i < frameCount; i += 1) {
      const sandbox = await frames.nth(i).getAttribute('sandbox');
      expect(sandbox).not.toBeNull();
      expect(sandbox ?? '').not.toContain('allow-same-origin');
    }

    // Give any (blocked) inline handler a tick, then confirm nothing fired.
    await page.waitForTimeout(200);
    expect(dialogFired).toBe(false);
  });
});
