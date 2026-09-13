import { expect, test, type Page } from '@playwright/test';

const NEXTS = {
    1: '#button-next-1',
    2: '#button-next-2',
    3: '#button-next-3',
};

async function stepNext(page: Page, step: number): Promise<void> {
    const sel = NEXTS[step as keyof typeof NEXTS];
    const loc = page.locator(sel);
    await expect(loc).toBeVisible();
    await loc.click();
}

test.describe('BookingBook wizard (фронт записи клиента)', () => {
    test('полный цикл записи', async ({ page }) => {
        await page.goto('/index.php/booking/');

        // Шаг 1 — услуга
        await expect(page.locator('#select-service')).toBeVisible();
        const svc = await page.locator('#select-service option').count();
        expect(svc).toBeGreaterThan(1);
        await page.locator('#select-service').selectOption({ index: 1 });
        await stepNext(page, 1);

        // Шаг 2 — дата (flatpickr; провайдер один → шаг пропущен)
        const calendar = page.locator('.flatpickr-calendar, .flatpickr-monthContainer, .flatpickr-days');
        await expect(calendar.first()).toBeVisible();

        const day = page
            .locator(
                '.flatpickr-day:not(.flatpickr-disabled):not(.flatpickr-nextmonthday):not(.flatpickr-prevmonthday)'
            )
            .first();
        await expect(day).toBeVisible();
        await day.click();

        // Шаг 2b — время
        const hour = page
            .locator('#available-hours .available-hour, #available-hours .available_time, #available-hours li, .available_hour')
            .first();
        await expect(hour).toBeVisible();
        await hour.click();
        await stepNext(page, 2);

        // Шаг 3 — данные клиента (fork: только имя и телефон)
        await expect(page.locator('#first-name').first()).toBeVisible();
        await page.locator('#first-name').first().fill('Иван');
        await expect(page.locator('#phone-number').first()).toBeVisible();
        await page.locator('#phone-number').first().fill('+79161234567');
        await page.locator('#button-next-3').click();

        // Шаг 4 — подтверждение
        await expect(page.locator('#book-appointment-submit')).toBeVisible();
        await page.locator('#book-appointment-submit').click();

        // Успешное завершение (редирект на страницу подтверждения)
        await page.waitForURL(/booking_confirmation/, { timeout: 20000 });
        await expect(page.locator('h3.text-success')).toBeVisible({ timeout: 20000 });
    });
});

test.describe('Backend login (админка)', () => {
    test('вход в админ-панель и открытие календаря', async ({ page }) => {
        await page.goto('/index.php/login/');
        await expect(page.locator('#login-form')).toBeVisible();

        await page.locator('#username').fill('admin');
        await page.locator('#password').fill('password123');
        await page.locator('#login').click();

        await page.waitForURL(/calendar/, { timeout: 30000 });
        await expect(page.locator('#calendar')).toBeVisible({ timeout: 30000 });
    });
});
