import { expect, test, type Page } from '@playwright/test';

import * as fs from 'fs';
import * as path from 'path';

/**
 * unexpected_issues_message — тесты на глобальный обработчик $(document).ajaxError
 * (assets/js/app.js → onAjaxError). Сообщение появляется в модальном окне
 * #message-modal ТОЛЬКО когда jQuery AJAX-запрос завершается с HTTP-ошибкой
 * (4xx/5xx) И тело ответа содержит message:
 *   - JSON с полем "message"
 *   - не-JSON тело (plain text / HTML) — целиком уходит в message
 * Если message пустой/отсутствует — модальное окно НЕ показывается.
 *
 * Русская строка: $lang['unexpected_issues_message'] = 'Операция не могла быть завершена.'
 */

const UNEXPECTED_ISSUES_RU = 'Операция не могла быть завершена.';

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

async function selectService(page: Page): Promise<void> {
    await expect(page.locator('#select-service')).toBeVisible();
    await page.locator('#select-service').selectOption({ index: 1 });
    await stepNext(page, 1);
}

async function selectDateAndHour(page: Page): Promise<void> {
    const calendar = page.locator('.flatpickr-calendar, .flatpickr-monthContainer, .flatpickr-days');
    await expect(calendar.first()).toBeVisible();

    const day = page
        .locator(
            '.flatpickr-day:not(.flatpickr-disabled):not(.flatpickr-nextmonthday):not(.flatpickr-prevmonthday)'
        )
        .first();
    await expect(day).toBeVisible();
    await day.click();

    const hour = page
        .locator('#available-hours .available-hour, #available-hours .available_time, #available-hours li, .available_hour')
        .first();
    await expect(hour).toBeVisible();
    await hour.click();
    await stepNext(page, 2);
}

async function fillCustomer(page: Page): Promise<void> {
    await expect(page.locator('#first-name').first()).toBeVisible();
    await page.locator('#first-name').first().fill('Иван');
    await expect(page.locator('#phone-number').first()).toBeVisible();
    await page.locator('#phone-number').first().fill('+79161234567');
    await page.locator('#button-next-3').click();
    await expect(page.locator('#book-appointment-submit')).toBeVisible();
}

async function clearRateLimitCache(): Promise<void> {
    const dir = path.resolve(__dirname, '..', '..', 'storage', 'cache');
    for (const file of fs.readdirSync(dir)) {
        if (file.startsWith('rate_limit_')) {
            try {
                fs.unlinkSync(path.join(dir, file));
            } catch (error) {
                console.warn('Could not remove rate limit cache file:', file, error);
            }
        }
    }
}

test.describe('unexpected_issues_message — AJAX-ошибки без message (модалка НЕ появляется)', () => {
    test('JSON 500 без поля message — модалка не появляется', async ({ page }) => {
        const requestPromise = page.waitForRequest('**/index.php/booking/get_unavailable_dates**');

        await page.route('**/index.php/booking/get_unavailable_dates**', (route) =>
            route.fulfill({
                status: 500,
                contentType: 'application/json',
                body: JSON.stringify({ success: false }),
            })
        );

        await page.goto('/index.php/booking/');
        await selectService(page);

        await requestPromise; // Убеждаемся, что AJAX-запрос реально выполнился.
        await page.waitForTimeout(500);
        await expect(page.locator('#message-modal')).toHaveCount(0);
    });

    test('HTTP 500 с пустым телом — модалка не появляется', async ({ page }) => {
        const requestPromise = page.waitForRequest('**/index.php/booking/get_unavailable_dates**');

        await page.route('**/index.php/booking/get_unavailable_dates**', (route) =>
            route.fulfill({ status: 500, body: '' })
        );

        await page.goto('/index.php/booking/');
        await selectService(page);

        await requestPromise; // Убеждаемся, что AJAX-запрос реально выполнился.
        await page.waitForTimeout(500);
        await expect(page.locator('#message-modal')).toHaveCount(0);
    });

    test('offline/сеть (abort) — модалка не появляется', async ({ page }) => {
        const requestPromise = page.waitForRequest('**/index.php/booking/get_unavailable_dates**');

        await page.route('**/index.php/booking/get_unavailable_dates**', (route) => route.abort());

        await page.goto('/index.php/booking/');
        await selectService(page);

        await requestPromise; // Убеждаемся, что AJAX-запрос реально выполнился.
        await page.waitForTimeout(500);
        await expect(page.locator('#message-modal')).toHaveCount(0);
    });
});

test.describe('unexpected_issues_message — реальный сценарий записи (модалка появляется)', () => {
    test('500 JSON c message при загрузке дат — модалка с текстом unexpected_issues_message', async ({ page }) => {
        await page.route('**/index.php/booking/get_unavailable_dates**', (route) =>
            route.fulfill({
                status: 500,
                contentType: 'application/json',
                body: JSON.stringify({ success: false, message: 'Datasource unreachable' }),
            })
        );

        await page.goto('/index.php/booking/');
        await selectService(page);

        await expect(page.locator('#message-modal')).toBeVisible({ timeout: 10000 });
        await expect(page.locator('#message-modal .modal-body')).toContainText(UNEXPECTED_ISSUES_RU);
        await expect(page.locator('#message-modal .modal-body .card .card-body')).toContainText('Datasource unreachable');
    });

    test('500 с не-JSON текстом (HTML страница ошибки) — модалка с raw-текстом', async ({ page }) => {
        await page.route('**/index.php/booking/get_unavailable_dates**', (route) =>
            route.fulfill({
                status: 500,
                contentType: 'text/html',
                body: '<html><body>An Error Was Encountered</body></html>',
            })
        );

        await page.goto('/index.php/booking/');
        await selectService(page);

        await expect(page.locator('#message-modal')).toBeVisible({ timeout: 10000 });
        await expect(page.locator('#message-modal .modal-body')).toContainText(UNEXPECTED_ISSUES_RU);
        await expect(page.locator('#message-modal .modal-body .card .card-body')).toContainText(
            'An Error Was Encountered'
        );
    });

    test('500 JSON c message при финальном booking/register — модалка, остаёмся на странице', async ({ page }) => {
        await page.goto('/index.php/booking/');

        await selectService(page);
        await selectDateAndHour(page);
        await fillCustomer(page);

        await page.route('**/index.php/booking/register', (route) =>
            route.fulfill({
                status: 500,
                contentType: 'application/json',
                body: JSON.stringify({
                    success: false,
                    message: 'requested_hour_is_unavailable',
                }),
            })
        );

        await page.locator('#book-appointment-submit').click();

        await expect(page.locator('#message-modal')).toBeVisible({ timeout: 10000 });
        await expect(page.locator('#message-modal .modal-body')).toContainText(UNEXPECTED_ISSUES_RU);
        await expect(page.locator('#message-modal .modal-body .card .card-body')).toContainText(
            'requested_hour_is_unavailable'
        );

        // Не должно быть редиректа на страницу подтверждения.
        expect(page.url()).toContain('/index.php/booking');
    });
});

test.describe('unexpected_issues_message — страница логина', () => {
    test('500 JSON c message при login/validate — модалка появляется', async ({ page }) => {
        await page.route('**/index.php/login/validate', (route) =>
            route.fulfill({
                status: 500,
                contentType: 'application/json',
                body: JSON.stringify({ success: false, message: 'Database connection lost' }),
            })
        );

        await page.goto('/index.php/login/');
        await expect(page.locator('#login-form')).toBeVisible();

        await page.locator('#username').fill('admin');
        await page.locator('#password').fill('wrong');
        await page.locator('#login').click();

        await expect(page.locator('#message-modal')).toBeVisible({ timeout: 10000 });
        await expect(page.locator('#message-modal .modal-body')).toContainText(UNEXPECTED_ISSUES_RU);
        await expect(page.locator('#message-modal .modal-body .card .card-body')).toContainText('Database connection lost');
    });

    test('реальные неверные учётные данные (200 с JSON) — модалка НЕ появляется', async ({ page }) => {
        await clearRateLimitCache();

        await page.goto('/index.php/login/');
        await expect(page.locator('#login-form')).toBeVisible();

        await page.locator('#username').fill('admin');
        await page.locator('#password').fill('totally-wrong-password-123');
        await page.locator('#login').click();

        // Сервер отвечает 200 {"success":false,"message":...}, это НЕ ajaxError.
        await expect(page.locator('#message-modal')).toHaveCount(0);
        await expect(page.locator('.alert-danger')).toBeVisible({ timeout: 10000 });

        await clearRateLimitCache();
    });
});