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
 * Audit page.
 *
 * This module implements the functionality of the audit log page.
 */
App.Pages.Audit = (function () {
    const $audit = $('#audit');
    const $filterAudit = $('#filter-audit');
    let filterResults = {};
    let filterLimit = 50;

    /**
     * Add the page event listeners.
     */
    function addEventListeners() {
        $audit.on('submit', '#filter-audit form', (event) => {
            event.preventDefault();

            const keyword = encodeURIComponent($('#filter-audit .key').val());

            filterLimit = 50;

            App.Pages.Audit.filter(keyword);
        });

        $audit.on('click', '#load-more', () => {
            const keyword = encodeURIComponent($('#filter-audit .key').val());

            App.Pages.Audit.filter(keyword, null, filterLimit);
        });

        $audit.on('click', '.entry-toggle', (event) => {
            $(event.currentTarget).closest('.entry').find('.entry-details').toggle();
        });
    }

    /**
     * Filters the audit log entries by a keyword string.
     *
     * @param {String} keyword This string is used to filter the audit log entries.
     * @param {Number} [selectId] Not used, kept for consistency.
     * @param {Number} [limit] Optional limit override (used by the load more button).
     */
    function filter(keyword, selectId = null, limit = null) {
        if (limit !== null) {
            filterLimit += 50;
        }

        App.Http.Audit.search(keyword, filterLimit).then((response) => {
            renderResults(response);
        });
    }

    /**
     * Render the given audit log entries into the results list.
     *
     * @param {Array} response Audit log entries to render.
     */
    function renderResults(response) {
        filterResults = response;

        $filterAudit.find('.results').empty();

        response.forEach((log) => {
            $filterAudit.find('.results').append(App.Pages.Audit.getFilterHtml(log)).append($('<hr/>'));
        });

        if (!response.length) {
            $filterAudit.find('.results').append(
                $('<em/>', {
                    'text': lang('no_records_found'),
                }),
            );
        }

        $('#load-more').toggle(response.length >= filterLimit);
    }

    /**
     * Get an audit log row html code that is going to be displayed on the results list.
     *
     * @param {Object} log Contains the audit log record data.
     *
     * @return {String} The html code that represents the record on the results list.
     */
    function getFilterHtml(log) {
        const actionLabels = {
            created: lang('action_created'),
            updated: lang('action_updated'),
            deleted: lang('action_deleted'),
        };

        const actionClasses = {
            created: 'success',
            updated: 'primary',
            deleted: 'danger',
        };

        return $('<div/>', {
            'class': 'audit-row entry',
            'data-id': log.id,
            'html': [
                $('<div/>', {
                    'class': 'd-flex flex-wrap align-items-center gap-2',
                    'html': [
                        $('<small/>', {
                            'class': 'text-muted',
                            'text': format_datetime(log.create_datetime),
                        }),
                        $('<strong/>', {
                            'class': 'me-2',
                            'text': log.user_name || '—',
                        }),
                        $('<span/>', {
                            'class': 'badge bg-' + (actionClasses[log.action] || 'secondary'),
                            'text': actionLabels[log.action] || log.action,
                        }),
                        $('<span/>', {
                            'class': 'badge bg-light text-dark border',
                            'text': entity_label(log.entity_type),
                        }),
                        $('<span/>', {
                            'class': 'flex-grow-1 text-truncate',
                            'text': log.entity_name || ('#' + (log.entity_id ?? '')),
                        }),
                        $('<button/>', {
                            'type': 'button',
                            'class': 'btn btn-sm btn-outline-secondary entry-toggle',
                            'html': '<i class="fas fa-chevron-down"></i>',
                        }),
                    ],
                }),
                $('<div/>', {
                    'class': 'entry-details border rounded p-2 mt-2 bg-light',
                    'style': 'display:none;',
                    'html': get_changes_html(log.changes),
                }),
            ],
        });
    }

    /**
     * Get the localized label of an entity type.
     *
     * @param {String} entityType
     *
     * @return {String}
     */
    function entity_label(entityType) {
        const labels = {
            appointment: lang('entity_appointment'),
            unavailability: lang('entity_unavailability'),
            customer: lang('entity_customer'),
            provider: lang('entity_provider'),
            admin: lang('entity_admin'),
            secretary: lang('entity_secretary'),
            service: lang('entity_service'),
            service_category: lang('entity_service_category'),
            blocked_period: lang('entity_blocked_period'),
        };

        return labels[entityType] || entityType;
    }

    /**
     * Build the html of the changes details block.
     *
     * @param {Object} changes Changes map ({added, changed, deleted}).
     *
     * @return {Array|String}
     */
    function get_changes_html(changes) {
        if (!changes || typeof changes !== 'object') {
            return '';
        }

        const sections = [];

        const append_values = (title, values, cssClass) => {
            const items = Object.entries(values || {});

            if (!items.length) {
                return;
            }

            sections.push(
                $('<div/>', {
                    'html': [
                        $('<strong/>', {
                            'class': cssClass,
                            'text': title,
                        }),
                        $('<ul/>', {
                            'class': 'mb-0 ps-4',
                            'html': items.map(([field, value]) =>
                                $('<li/>', {
                                    'html': [
                                        $('<code/>', {text: field}),
                                        document.createTextNode(': ' + format_value(value)),
                                    ],
                                }),
                            ),
                        }),
                    ],
                }),
            );
        };

        append_values(lang('audit_changes_added'), changes.added, 'text-success');
        append_values(lang('audit_changes_deleted'), changes.deleted, 'text-danger');

        const changedItems = Object.entries(changes.changed || {});

        if (changedItems.length) {
            sections.push(
                $('<div/>', {
                    'html': [
                        $('<strong/>', {
                            'class': 'text-primary',
                            'text': lang('audit_changes_changed'),
                        }),
                        $('<ul/>', {
                            'class': 'mb-0 ps-4',
                            'html': changedItems.map(([field, value]) =>
                                $('<li/>', {
                                    'html': [
                                        $('<code/>', {text: field}),
                                        document.createTextNode(
                                            ': ' + format_value(value?.from) + ' → ' + format_value(value?.to),
                                        ),
                                    ],
                                }),
                            ),
                        }),
                    ],
                }),
            );
        }

        return sections.length ? sections : $('<em/>', {text: '—'});
    }

    /**
     * Format a change value for display.
     *
     * @param {*} value
     *
     * @return {String}
     */
    function format_value(value) {
        if (value === null || value === undefined || value === '') {
            return '—';
        }

        if (typeof value === 'object') {
            return JSON.stringify(value);
        }

        return String(value);
    }

    /**
     * Format the create datetime value for display.
     *
     * @param {String} value Datetime value ("YYYY-MM-DD HH:MM:SS").
     *
     * @return {String}
     */
    function format_datetime(value) {
        if (!value) {
            return '';
        }

        const matches = String(value).match(/^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})/);

        return matches ? `${matches[3]}.${matches[2]}.${matches[1]} ${matches[4]}:${matches[5]}` : value;
    }

    /**
     * Initialize the module.
     */
    function initialize() {
        const logs = vars('logs');

        if (Array.isArray(logs)) {
            renderResults(logs);
        } else {
            App.Pages.Audit.filter('');
        }

        App.Pages.Audit.addEventListeners();
    }

    document.addEventListener('DOMContentLoaded', initialize);

    return {
        filter,
        getFilterHtml,
        addEventListeners,
    };
})();
