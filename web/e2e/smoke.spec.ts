import { expect, test } from '@playwright/test';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const source = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  '..',
  '..',
  'data',
  'fixtures',
  'sources',
  'handwashing-sop-en.md',
);

test('upload, chat, approve the script and the video', async ({ page }) => {
  await page.goto('/?token=e2e');
  await expect(page.getByLabel('Chat')).toBeVisible();
  await expect(page.getByLabel('Video')).toBeVisible();
  await expect(page.getByLabel('Project')).toHaveValue(/[a-f0-9]{12}/);

  await page.getByTestId('file-input').setInputFiles(source);
  await expect(page.getByText('Source uploaded: handwashing-sop-en.md')).toBeVisible();

  await page.getByLabel('Message').fill('A 45-second Georgian training video with one quiz');
  await page.getByRole('button', { name: 'Send' }).click();
  await expect(page.getByRole('region', { name: 'Fact-check' }).first()).toBeVisible({ timeout: 60_000 });
  await page.getByRole('button', { name: 'Approve script' }).click();

  await expect(page.getByTestId('player')).toBeVisible({ timeout: 60_000 });
  await expect(page.getByLabel('Render speed')).toContainText('fps');
  await page.getByRole('button', { name: 'Approve final video' }).click();
  await expect(page.getByText(/Final video, version \d+, is ready/)).toBeVisible({ timeout: 60_000 });
  await expect(page.getByRole('link', { name: 'Download MP4' })).toHaveAttribute('href', /final\/mp4/);
});
