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
 * Providers page.
 *
 * This module implements the functionality of the providers page.
 */
App.Pages.Providers = (function () {
    const $providers = $('#providers');
    const $id = $('#id');
    const $providerName = $('#provider-name');
    const $filterProviders = $('#filter-providers');
    let filterResults = {};
    let filterLimit = 20;

    /**
     * Add the page event listeners.
     */
    function addEventListeners() {
        /**
         * Event: Filter Providers Form "Submit"
         *
         * Filter the provider records with the given key string.
         *
         * @param {jQuery.Event} event
         */
        $providers.on('submit', '#filter-providers form', (event) => {
            event.preventDefault();
            const key = $('#filter-providers .key').val();
            $('.selected').removeClass('selected');
            App.Pages.Providers.resetForm();
            App.Pages.Providers.filter(key);
        });

        /**
         * Event: Filter Provider Row "Click"
         *
         * Display the selected provider data to the user.
         */
        $providers.on('click', '.provider-row', (event) => {
            if ($filterProviders.find('.filter').prop('disabled')) {
                $filterProviders.find('.results').css('color', '#AAA');
                return; // Exit because we are currently on edit mode.
            }

            const providerId = $(event.currentTarget).attr('data-id');
            const provider = filterResults.find((filterResult) => Number(filterResult.id) === Number(providerId));

            App.Pages.Providers.display(provider);
            $filterProviders.find('.selected').removeClass('selected');
            $(event.currentTarget).addClass('selected');
            $('#edit-provider, #delete-provider').prop('disabled', false);

            // Automatically enter edit mode
            $('#providers-page').addClass('editing');
            $providers.find('.add-edit-delete-group').hide();
            $providers.find('.save-cancel-group').show();
            $providers.find('#delete-provider').show(); // Show delete button when editing
            $filterProviders.find('button').prop('disabled', true);
            $filterProviders.find('.results').css('color', '#AAA');
            $providers.find('.record-details').find('input, select, textarea').prop('disabled', false);
            $providers.find('.record-details .form-label span').prop('hidden', false);
            $('#provider-services input:checkbox').prop('disabled', false);
            $('#select-all-services, #select-none-services').prop('disabled', false);
            $('#providers input:checkbox').prop('disabled', false);
        });

        /**
         * Event: Add New Provider Button "Click"
         */
        $providers.on('click', '#add-provider', () => {
            App.Pages.Providers.resetForm();
            $('#providers-page').addClass('editing');
            $filterProviders.find('button').prop('disabled', true);
            $filterProviders.find('.results').css('color', '#AAA');
            $providers.find('.add-edit-delete-group').hide();
            $providers.find('.save-cancel-group').show();
            $providers.find('#delete-provider').hide(); // Hide delete button when adding
            $providers.find('.record-details').find('input, select, textarea').prop('disabled', false);
            $providers.find('.record-details .form-label span').prop('hidden', false);
            $('#provider-services input:checkbox').prop('disabled', false);
            $('#select-all-services, #select-none-services').prop('disabled', false);
        });

        /**
         * Event: Edit Provider Button "Click"
         */
        $providers.on('click', '#edit-provider', () => {
            $('#providers-page').addClass('editing');
            $providers.find('.add-edit-delete-group').hide();
            $providers.find('.save-cancel-group').show();
            $filterProviders.find('button').prop('disabled', true);
            $filterProviders.find('.results').css('color', '#AAA');
            $providers.find('.record-details').find('input, select, textarea').prop('disabled', false);
            $providers.find('.record-details .form-label span').prop('hidden', false);
            $('#provider-services input:checkbox').prop('disabled', false);
            $('#select-all-services, #select-none-services').prop('disabled', false);
            $('#providers input:checkbox').prop('disabled', false);
        });

        /**
         * Event: Delete Provider Button "Click"
         */
        $providers.on('click', '#delete-provider', () => {
            const providerId = $id.val();

            const buttons = [
                {
                    text: lang('cancel'),
                    click: (event, messageModal) => {
                        messageModal.hide();
                    },
                },
                {
                    text: lang('delete'),
                    click: (event, messageModal) => {
                        App.Pages.Providers.remove(providerId);
                        messageModal.hide();
                    },
                },
            ];

            App.Utils.Message.show(lang('delete_provider'), lang('delete_record_prompt'), buttons);
        });

        /**
         * Event: Save Provider Button "Click"
         */
        $providers.on('click', '#save-provider', () => {
            const provider = {
                name: $providerName.val(),
            };

            // Include provider services.
            provider.services = [];
            $('#provider-services input:checkbox').each((index, checkboxEl) => {
                if ($(checkboxEl).prop('checked')) {
                    provider.services.push($(checkboxEl).attr('data-id'));
                }
            });

            // Include id if changed.
            if ($id.val() !== '') {
                provider.id = $id.val();
            }

            if (!App.Pages.Providers.validate()) {
                return;
            }

            App.Pages.Providers.save(provider);
        });

        /**
         * Event: Cancel Provider Button "Click"
         *
         * Cancel add or edit of an provider record.
         */
        $providers.on('click', '#cancel-provider', () => {
            const id = $('#filter-providers .selected').attr('data-id');
            App.Pages.Providers.resetForm();
            $('#providers-page').removeClass('editing');
            if (id) {
                App.Pages.Providers.select(id, true);
            }
        });

        /**
         * Event: Select All Services Button "Click"
         */
        $providers.on('click', '#select-all-services', () => {
            $('#provider-services input:checkbox').prop('checked', true);
        });

        /**
         * Event: Select None Services Button "Click"
         */
        $providers.on('click', '#select-none-services', () => {
            $('#provider-services input:checkbox').prop('checked', false);
        });
    }

    /**
     * Save provider record to database.
     *
     * @param {Object} provider Contains the provider record data. If an 'id' value is provided
     * then the update operation is going to be executed.
     */
    function save(provider) {
        App.Http.Providers.save(provider).then((response) => {
            App.Layouts.Backend.displayNotification(lang('provider_saved'));
            App.Pages.Providers.resetForm();
            $('#providers-page').removeClass('editing');
            $('#filter-providers .key').val('');
            App.Pages.Providers.filter('', response.id, true);
        });
    }

    /**
     * Delete a provider record from database.
     *
     * @param {Number} id Record id to be deleted.
     */
    function remove(id) {
        App.Http.Providers.destroy(id).then(() => {
            App.Layouts.Backend.displayNotification(lang('provider_deleted'));
            App.Pages.Providers.resetForm();
            $('#providers-page').removeClass('editing');
            App.Pages.Providers.filter($('#filter-providers .key').val());
        });
    }

    /**
     * Validates a provider record.
     *
     * @return {Boolean} Returns the validation result.
     */
    function validate() {
        $providers.find('.is-invalid').removeClass('is-invalid');
        $providers.find('.form-message').removeClass('alert-danger').hide();

        try {
            // Validate required fields.
            let missingRequired = false;

            $providers.find('.required').each((index, requiredFieldEl) => {
                if (!$(requiredFieldEl).val()) {
                    $(requiredFieldEl).addClass('is-invalid');
                    missingRequired = true;
                }
            });

            if (missingRequired) {
                throw new Error(lang('fields_are_required'));
            }

            return true;
        } catch (error) {
            $('#providers .form-message').addClass('alert-danger').text(error.message).show();
            return false;
        }
    }

    /**
     * Resets the provider tab form back to its initial state.
     */
    function resetForm() {
        $filterProviders.find('.selected').removeClass('selected');
        $filterProviders.find('button').prop('disabled', false);
        $filterProviders.find('.results').css('color', '');

        $providers.find('.add-edit-delete-group').show();
        $providers.find('.save-cancel-group').hide();
        $providers.find('.record-details h4 a').remove();
        $providers.find('.record-details').find('input, select, textarea').val('').prop('disabled', true);
        $providers.find('.record-details .form-label span').prop('hidden', true);

        $providers.find('.record-details .is-invalid').removeClass('is-invalid');
        $providers.find('.record-details .form-message').hide();

        $('#edit-provider, #delete-provider').prop('disabled', true);
        $('#provider-services input:checkbox').prop('disabled', true).prop('checked', false);
        $('#select-all-services, #select-none-services').prop('disabled', true);
        $('#provider-services a').remove();
    }

    /**
     * Display a provider record into the provider form.
     *
     * @param {Object} provider Contains the provider record data.
     */
    function display(provider) {
        $id.val(provider.id);
        $providerName.val(provider.name);

        // Add dedicated provider link.
        let dedicatedUrl = App.Utils.Url.siteUrl('?provider=' + encodeURIComponent(provider.id));
        let $link = $('<a/>', {
            'href': dedicatedUrl,
            'target': '_blank',
            'data-bs-toggle': 'tooltip',
            'title': lang('booking_link'),
            'aria-label': lang('booking_link'),
            'html': [
                $('<i/>', {
                    'class': 'fas fa-link',
                }),
            ],
        });

        $providers.find('.details-view h4').find('a').remove().end().append($link);
        new bootstrap.Tooltip($link[0]);

        $('#provider-services a').remove();
        $('#provider-services input:checkbox').prop('checked', false);

        provider.services.forEach((providerServiceId) => {
            const $checkbox = $('#provider-services input[data-id="' + providerServiceId + '"]');

            if (!$checkbox.length) {
                return;
            }

            $checkbox.prop('checked', true);

            // Add dedicated service-provider link.
            dedicatedUrl = App.Utils.Url.siteUrl(
                '?provider=' + encodeURIComponent(provider.id) + '&service=' + encodeURIComponent(providerServiceId),
            );

            $link = $('<a/>', {
                'href': dedicatedUrl,
                'target': '_blank',
                'class': 'ms-2',
                'data-bs-toggle': 'tooltip',
                'title': lang('booking_link'),
                'aria-label': lang('booking_link'),
                'html': [
                    $('<i/>', {
                        'class': 'fas fa-link',
                    }),
                ],
            });

            $checkbox.parent().append($link);
            new bootstrap.Tooltip($link[0]);
        });
    }

    /**
     * Filters provider records depending a string keyword.
     *
     * @param {string} keyword This is used to filter the provider records of the database.
     * @param {numeric} selectId Optional, if set, when the function is complete a result row can be set as selected.
     * @param {bool} show Optional (false), if true the selected record will be also displayed.
     */
    function filter(keyword, selectId = null, show = false) {
        App.Http.Providers.search(keyword, filterLimit).then((response) => {
            filterResults = response;

            $filterProviders.find('.results').empty();
            response.forEach((provider) => {
                $('#filter-providers .results').append(App.Pages.Providers.getFilterHtml(provider)).append($('<hr/>'));
            });

            if (!response.length) {
                $filterProviders.find('.results').append(
                    $('<em/>', {
                        'text': lang('no_records_found'),
                    }),
                );
            } else if (response.length === filterLimit) {
                $('<button/>', {
                    'type': 'button',
                    'class': 'btn btn-outline-secondary w-100 load-more text-center',
                    'text': lang('load_more'),
                    'click': () => {
                        filterLimit += 20;
                        App.Pages.Providers.filter(keyword, selectId, show);
                    },
                }).appendTo('#filter-providers .results');
            }

            if (selectId) {
                App.Pages.Providers.select(selectId, show);
            }
        });
    }

    /**
     * Get an provider row html code that is going to be displayed on the filter results list.
     *
     * @param {Object} provider Contains the provider record data.
     *
     * @return {String} The html code that represents the record on the filter results list.
     */
    function getFilterHtml(provider) {
        return $('<div/>', {
            'class': 'provider-row entry',
            'data-id': provider.id,
            'html': [
                $('<strong/>', {
                    'text': provider.name,
                }),
                $('<br/>'),
            ],
        });
    }

    /**
     * Select and display a providers filter result on the form.
     *
     * @param {Number} id Record id to be selected.
     * @param {Boolean} show Optional (false), if true the record will be displayed on the form.
     */
    function select(id, show = false) {
        // Select record in filter results.
        $filterProviders.find('.provider-row[data-id="' + id + '"]').addClass('selected');

        // Display record in form (if display = true).
        if (show) {
            const provider = filterResults.find((filterResult) => Number(filterResult.id) === Number(id));

            App.Pages.Providers.display(provider);

            $('#edit-provider, #delete-provider').prop('disabled', false);
        }
    }

    /**
     * Initialize the module.
     */
    function initialize() {
        App.Pages.Providers.resetForm();
        App.Pages.Providers.filter('');
        App.Pages.Providers.addEventListeners();

        vars('services').forEach((service) => {
            const checkboxId = `provider-service-${service.id}`;

            $('<div/>', {
                'class': 'checkbox',
                'html': [
                    $('<div/>', {
                        'class': 'checkbox form-check',
                        'html': [
                            $('<input/>', {
                                'id': checkboxId,
                                'class': 'form-check-input',
                                'type': 'checkbox',
                                'data-id': service.id,
                                'prop': {
                                    'disabled': true,
                                },
                            }),
                            $('<label/>', {
                                'class': 'form-check-label',
                                'text': service.name,
                                'for': checkboxId,
                            }),
                        ],
                    }),
                ],
            }).appendTo('#provider-services');
        });
    }

    document.addEventListener('DOMContentLoaded', initialize);

    return {
        filter,
        save,
        remove,
        validate,
        getFilterHtml,
        resetForm,
        display,
        select,
        addEventListeners,
    };
})();
