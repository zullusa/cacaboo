/* ----------------------------------------------------------------------------
 * Easy!Appointments - Online Appointment Scheduler
 *
 * @author      A.Tselegidis <alextselegidis@gmail.com>
 * @copyright   Copyright (c) Alex Tselegidis
 * @license     https://opensource.org/licenses/GPL-3.0 - GPLv3
 * @link        https://easyappointments.org
 * @since       v1.5.0
 * ---------------------------------------------------------------------------- */

/**
 * App global namespace object.
 *
 * This script should be loaded before the other modules in order to define the global application namespace.
 */
window.App = (function () {
    function onAjaxError(event, jqXHR, textStatus, errorThrown) {
        console.error('Unexpected HTTP Error: ', jqXHR, textStatus, errorThrown);

        let response;

        try {
            response = JSON.parse(jqXHR.responseText); // JSON response
        } catch (error) {
            response = {message: jqXHR.responseText}; // String response
        }

        if (!response || !response.message) {
            return;
        }

        if (App.Utils.Message) {
            App.Utils.Message.show('CaCaBoo', lang('unexpected_issues_message'));

            $('<div/>', {
                'class': 'card',
                'html': [
                    $('<div/>', {
                        'class': 'card-body overflow-auto',
                        'html': response.message,
                    }),
                ],
            }).appendTo('#message-modal .modal-body');
        }
    }

    $(document).ajaxError(onAjaxError);

    $(function () {
        if (window.moment) {
            window.moment.locale(vars('language_code'));
        }

        // Close any open modal when the Escape key is pressed.
        //
        // Bootstrap already does this when the focus is inside the modal, but
        // this document level handler makes it work regardless of the focused
        // element so that every modal in the application can be dismissed.
        $(document).on('keydown', (event) => {
            if (event.key !== 'Escape') {
                return;
            }

            const $modal = $('.modal.show').last();

            if (!$modal.length) {
                return;
            }

            const modalInstance = bootstrap.Modal.getInstance($modal[0]);

            // Respect modals that were explicitly created as non-dismissible
            // (e.g. blocking message boxes that require a decision).
            if (modalInstance && modalInstance._config && modalInstance._config.keyboard === false) {
                return;
            }

            if (modalInstance) {
                modalInstance.hide();
            } else {
                $modal.modal('hide');
            }
        });
    });

    return {
        Components: {},
        Http: {},
        Layouts: {},
        Pages: {},
        Utils: {},
    };
})();
