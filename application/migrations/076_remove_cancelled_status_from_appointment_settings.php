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
 * Removes the "Отменено" (Cancelled) appointment status option.
 *
 * The cancelled status is not used anymore because appointments are deleted
 * directly in order to free up the available time.
 */
class Migration_Remove_cancelled_status_from_appointment_settings extends EA_Migration
{
    public const CANCELLED_STATUS = 'Отменено';

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

        $statuses = array_values(array_diff($statuses, [self::CANCELLED_STATUS]));

        $this->db->where('name', 'appointment_status_options');

        $this->db->update('settings', [
            'value' => json_encode($statuses, JSON_UNESCAPED_UNICODE),
        ]);
    }

    /**
     * Downgrade method.
     *
     * Restores the "Отменено" (Cancelled) status option at the end of the list.
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
            $statuses = [];
        }

        if (!in_array(self::CANCELLED_STATUS, $statuses, true)) {
            $statuses[] = self::CANCELLED_STATUS;

            $this->db->where('name', 'appointment_status_options');

            $this->db->update('settings', [
                'value' => json_encode($statuses, JSON_UNESCAPED_UNICODE),
            ]);
        }
    }
}