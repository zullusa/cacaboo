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
 * Migration: Set the default timezone to Moscow.
 *
 * Updates the existing "default_timezone" setting value to "Europe/Moscow",
 * so that existing installations also use the new default timezone.
 */
class Migration_Set_default_timezone_to_moscow extends EA_Migration
{
    /**
     * Upgrade method.
     */
    public function up(): void
    {
        $this->db->where('name', 'default_timezone');

        $this->db->update('settings', ['value' => 'Europe/Moscow']);
    }

    /**
     * Downgrade method.
     */
    public function down(): void
    {
        $this->db->where('name', 'default_timezone');

        $this->db->update('settings', ['value' => 'UTC']);
    }
}
