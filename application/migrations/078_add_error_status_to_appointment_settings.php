<?php defined('BASEPATH') or exit('No direct script access allowed');

/* ----------------------------------------------------------------------------
 * Easy!Appointments - Open Source Web Scheduler
 *
 * @package     EasyAppointments
 * @author      A.Tselegidis <alextselegidis@gmail.com>
 * @copyright   Copyright (c) Alex Tselegidis
 * @license     https://opensource.org/licenses/GPL-3.0 - GPLv3
 * @link        https://easyappointments.org
 * @since       v1.5.0
 * ---------------------------------------------------------------------------- */

/**
 * Adds the "Ошибка" (Error) appointment status option.
 *
 * Used by the reminder worker when the customer phone number is invalid
 * (e.g. starts with "8") and the SMS reminder cannot be sent.
 */
class Migration_Add_error_status_to_appointment_settings extends EA_Migration
{
    public const ERROR_STATUS = 'Ошибка';

    /**
     * Upgrade method.
     */
    public function up(): void
    {
        $this->db->where('name', 'appointment_status_options');

        $query = $this->db->get('settings');

        if ($query->num_rows() === 0) {
            return;
        }

        $statuses = json_decode((string) $query->row()->value, true);

        if (!is_array($statuses)) {
            return;
        }

        if (!in_array(self::ERROR_STATUS, $statuses, true)) {
            $statuses[] = self::ERROR_STATUS;

            $this->db->where('name', 'appointment_status_options');

            $this->db->update('settings', [
                'value' => json_encode($statuses, JSON_UNESCAPED_UNICODE),
            ]);
        }
    }

    /**
     * Downgrade method.
     *
     * Removes the "Ошибка" (Error) status option.
     */
    public function down(): void
    {
        $this->db->where('name', 'appointment_status_options');

        $query = $this->db->get('settings');

        if ($query->num_rows() === 0) {
            return;
        }

        $statuses = json_decode((string) $query->row()->value, true);

        if (!is_array($statuses)) {
            return;
        }

        $statuses = array_values(array_diff($statuses, [self::ERROR_STATUS]));

        $this->db->where('name', 'appointment_status_options');

        $this->db->update('settings', [
            'value' => json_encode($statuses, JSON_UNESCAPED_UNICODE),
        ]);
    }
}
