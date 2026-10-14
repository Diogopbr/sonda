import { test, expect, type Page } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

async function start(page: Page): Promise<void> {
  await page.goto('/');
  await page.getByRole('button', { name: 'Iniciar demonstração' }).click();
  await expect(page.getByRole('heading', { name: 'Registro de serviços' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'API de pedidos', exact: true })).toBeVisible();
}
async function service(page: Page): Promise<void> {
  await page.getByRole('link', { name: 'API de pedidos', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'API de pedidos', exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Verificar agora' })).toBeEnabled();
}
async function scenario(page: Page, value: string): Promise<void> {
  await page.getByLabel('Cenário do alvo fictício').selectOption(value);
  await page.getByRole('button', { name: 'Aplicar cenário' }).click();
  await expect(page.getByRole('button', { name: 'Verificar agora' })).toBeEnabled();
  await expect(page.getByRole('button', { name: 'Aplicar cenário' })).toBeDisabled();
}
async function verify(page: Page): Promise<void> {
  await page.getByRole('button', { name: 'Verificar agora' }).click();
  await expect(page.getByRole('button', { name: 'Verificar agora' })).toBeEnabled();
  await expect(page.getByRole('status').filter({ hasText: 'Verificação registrada.' })).toBeVisible();
}
async function openIncident(page: Page): Promise<string> {
  await scenario(page, 'unavailable');
  await verify(page);
  await verify(page);
  await page.getByRole('link', { name: /Ver evidências/ }).click();
  await expect(page.getByRole('heading', { name: 'Incidente em API de pedidos' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Reconhecer incidente' })).toBeVisible();
  return new URL(page.url()).pathname;
}
async function accessible(page: Page): Promise<void> {
  const result = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze();
  expect(result.violations).toEqual([]);
}

test('real incident cycle, acknowledgement, recovery, history and reload', async ({ page }) => {
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  await start(page); await service(page); await verify(page);
  await expect(page.getByText('Saudável', { exact: true })).toBeVisible();
  const incident = await openIncident(page);
  await page.getByLabel('Comentário de investigação').fill('Conferindo a resposta da API.\nRevisando a origem do erro.');
  await page.getByRole('button', { name: 'Reconhecer incidente' }).click();
  await expect(page.getByText('Reconhecido', { exact: true })).toBeVisible();
  await scenario(page, 'available'); await verify(page); await verify(page);
  await expect(page.getByText('Resolvido', { exact: true })).toBeVisible();
  await expect(page.getByText('Conferindo a resposta da API.\nRevisando a origem do erro.', { exact: true })).toBeVisible();
  await accessible(page);
  await page.reload();
  await expect(page.getByText('Resolvido', { exact: true })).toBeVisible();
  await page.getByRole('link', { name: 'Voltar ao serviço' }).click();
  await page.locator('.incident-history').getByRole('link', { name: /Recuperação confirmada/ }).click();
  expect(new URL(page.url()).pathname).toBe(incident);
  expect(errors).toEqual([]);
});

test('two visitors cannot read each others records and private source paths stay inaccessible', async ({ browser, baseURL }) => {
  const first = await browser.newContext({ baseURL });
  const second = await browser.newContext({ baseURL });
  try {
    const a = await first.newPage(); const b = await second.newPage();
    await start(a); await service(a);
    const monitor = new URL(a.url()).pathname.split('/').at(-1);
    await start(b);
    expect((await second.request.get(`/api/monitors/${monitor}`)).status()).toBe(404);
    for (const path of ['/.env', '/.local/settings.json', '/README.md', '/frontend/src/App.svelte', '/sonda/config.py']) {
      expect((await first.request.get(path)).status()).toBe(404);
    }
  } finally { await first.close(); await second.close(); }
});

test('stale acknowledgement preserves draft and requires explicit review', async ({ page, context }) => {
  await start(page); await service(page); const incident = await openIncident(page);
  const other = await context.newPage(); await other.goto(incident);
  await expect(other.getByLabel('Comentário de investigação')).toBeVisible();
  await other.getByLabel('Comentário de investigação').fill('Rascunho da segunda aba.');
  await page.getByLabel('Comentário de investigação').fill('Analisando o serviço na primeira aba.');
  await page.getByRole('button', { name: 'Reconhecer incidente' }).click();
  await expect(page.getByText('Reconhecido', { exact: true })).toBeVisible();
  await other.getByRole('button', { name: 'Reconhecer incidente' }).click();
  await expect(other.getByRole('alert')).toBeFocused();
  await expect(other.getByLabel('Comentário de investigação')).toHaveValue('Rascunho da segunda aba.');
  await other.getByRole('button', { name: 'Revisar dados atuais' }).click();
  await expect(other.getByLabel('Rascunho não enviado')).toHaveValue('Rascunho da segunda aba.');
  await expect(other.getByText('Analisando o serviço na primeira aba.', { exact: true })).toBeVisible();
  await accessible(other);
});

test('reset dialog contains focus, restores it on cancel and old-tab commands keep their draft', async ({ page, context }) => {
  await start(page); await service(page); const incident = await openIncident(page);
  const other = await context.newPage(); await other.goto(incident);
  await other.getByLabel('Comentário de investigação').fill('Rascunho preservado após reinício.');
  await page.getByRole('button', { name: 'Reiniciar demo' }).click();
  await expect(page.getByRole('button', { name: 'Manter ambiente' })).toBeFocused();
  await page.keyboard.press('Escape');
  await expect(page.getByRole('button', { name: 'Reiniciar demo' })).toBeFocused();
  await page.getByRole('button', { name: 'Reiniciar demo' }).click();
  await page.getByRole('button', { name: 'Reiniciar ambiente', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Registro de serviços' })).toBeVisible();
  await other.getByRole('button', { name: 'Reconhecer incidente' }).click();
  await expect(other.getByLabel('Rascunho não enviado')).toHaveValue('Rascunho preservado após reinício.');
  await expect(other.getByRole('alert')).toBeFocused();
  const response = await context.request.get('/api/monitors');
  expect((await response.json()).monitors.every((monitor: { last_check: unknown }) => monitor.last_check === null)).toBe(true);
});

test('mobile records, empty filter and keyboard verification remain accessible', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await start(page); await accessible(page);
  await page.getByRole('button', { name: 'Pausados', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Nenhum serviço neste filtro' })).toBeVisible();
  await page.getByRole('button', { name: 'Mostrar todos' }).click();
  await service(page);
  await page.getByRole('button', { name: 'Verificar agora' }).focus();
  await page.keyboard.press('Enter');
  await expect(page.getByRole('button', { name: 'Verificar agora' })).toBeEnabled();
  await expect(page.getByText('Saudável', { exact: true })).toBeVisible();
  await accessible(page);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});
