<?php defined('BASEPATH') or exit('No direct script access allowed');

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
 * Adds the "Оповещен" (Notified) appointment status option.
 *
 * Appends the new status to the existing "appointment_status_options"
 * setting so that reminders sent by the SMS service can mark an
 * appointment as notified.
 */
class Migration_Add_notified_status_to_appointment_settings extends EA_Migration
{
    public const NOTIFIED_STATUS = 'Оповещен';

    /**
     * Upgrade method.
     */
    public function up(): void
    {
        $this->add_notified_status();
    }

    /**
     * Downgrade method.
     */
    public function down(): void
    {
        $this->remove_notified_status();
    }

    private function add_notified_status(): void
    {
        $this->db->where('name', 'appointment_status_options');

        $query = $this->db->get('settings');

        if ($query->num_rows() === 0) {
            $this->db->insert('settings', [
                'name' => 'appointment_status_options',
                'value' => json_encode(['Записано', 'Подтверждено', 'Отменено', self::NOTIFIED_STATUS], JSON_UNESCAPED_UNICODE),
            ]);

            return;
        }

        $statuses = json_decode((string) $query->row()->value, true);

        if (!is_array($statuses)) {
            $statuses = [];
        }

        if (in_array(self::NOTIFIED_STATUS, $statuses, true)) {
            return;
        }

        $statuses[] = self::NOTIFIED_STATUS;

        $this->db->where('name', 'appointment_status_options');

        $this->db->update('settings', [
            'value' => json_encode($statuses, JSON_UNESCAPED_UNICODE),
        ]);
    }

    private function remove_notified_status(): void
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

        $statuses = array_values(array_diff($statuses, [self::NOTIFIED_STATUS]));

        $this->db->where('name', 'appointment_status_options');

        $this->db->update('settings', [
            'value' => json_encode($statuses, JSON_UNESCAPED_UNICODE),
        ]);
    }
}
