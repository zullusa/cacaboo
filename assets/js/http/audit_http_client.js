/* ----------------------------------------------------------------------------
 * Easy!Appointments - Online Appointment Scheduler
 *
 * @package     EasyAppointments
 * @author      A.Tselegidis <alextselegidis@gmail.com>
 * @copyright   Copyright (c) Alex Tselegidis
 * @license     https://opensource.org/licenses/GPL-3.0 - GPLv3
 * @link        https://easyappointments.org
 * @since       v1.5.0
 * ---------------------------------------------------------------------------- */

/**
 * Audit HTTP client.
 *
 * This module implements the audit log related HTTP requests.
 */
App.Http.Audit = (function () {
    /**
     * Search audit log entries by keyword.
     *
     * @param {String} keyword
     * @param {Number} [limit]
     * @param {Number} [offset]
     * @param {String} [orderBy]
     *
     * @return {Object}
     */
    function search(keyword, limit = null, offset = null, orderBy = null) {
        const url = App.Utils.Url.siteUrl('audit/search');

        const data = {
            csrf_token: vars('csrf_token'),
            keyword,
            limit,
            offset,
            order_by: orderBy || undefined,
        };

        return $.post(url, data);
    }

    return {
        search,
    };
})();
