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
 * Reorders the appointment status options.
 *
 * Sets the UI order of the appointment statuses to:
 * "Записано", "Оповещен", "Подтверждено", "Отменено".
 *
 * Custom statuses added by the admin are preserved and appended after the
 * default ones, keeping their relative order.
 */
class Migration_Reorder_appointment_status_options extends EA_Migration
{
    private const DEFAULT_STATUSES = ['Записано', 'Оповещен', 'Подтверждено', 'Отменено'];

    /**
     * Upgrade method.
     */
    public function up(): void
    {
        $this->db->where('name', 'appointment_status_options');

        $query = $this->db->get('settings');

        if ($query->num_rows() === 0) {
            $this->db->insert('settings', [
                'name' => 'appointment_status_options',
                'value' => json_encode(self::DEFAULT_STATUSES, JSON_UNESCAPED_UNICODE),
            ]);

            return;
        }

        $statuses = json_decode((string) $query->row()->value, true);

        if (!is_array($statuses)) {
            $statuses = [];
        }

        // Keep the known statuses in the desired order and append the custom ones.
        $knownStatuses = array_values(array_intersect(self::DEFAULT_STATUSES, $statuses));
        $customStatuses = array_values(array_diff($statuses, self::DEFAULT_STATUSES));

        $orderedStatuses = array_merge($knownStatuses, $customStatuses);

        if ($orderedStatuses !== $statuses) {
            $this->db->where('name', 'appointment_status_options');

            $this->db->update('settings', [
                'value' => json_encode($orderedStatuses, JSON_UNESCAPED_UNICODE),
            ]);
        }
    }

    /**
     * Downgrade method.
     *
     * Restores the previous status order: "Записано", "Подтверждено", "Отменено", "Оповещен".
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

        $legacyOrder = ['Записано', 'Подтверждено', 'Отменено', 'Оповещен'];

        $knownStatuses = array_values(array_intersect($legacyOrder, $statuses));
        $customStatuses = array_values(array_diff($statuses, $legacyOrder));

        $orderedStatuses = array_merge($knownStatuses, $customStatuses);

        $this->db->where('name', 'appointment_status_options');

        $this->db->update('settings', [
            'value' => json_encode($orderedStatuses, JSON_UNESCAPED_UNICODE),
        ]);
    }
}