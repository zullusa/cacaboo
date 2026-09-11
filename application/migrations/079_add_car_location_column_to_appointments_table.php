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
 * Adds the "car_location" column to the appointments table.
 *
 * The new booking form field stores whether the car is located at the owner
 * ("у владельца") or at the shop ("у нас"). Existing appointments default to
 * "у владельца" because the reminder worker still needs to notify their owners.
 */
class Migration_Add_car_location_column_to_appointments_table extends EA_Migration
{
    public const CAR_LOCATION_OWNER = 'у владельца';

    /**
     * Upgrade method.
     */
    public function up(): void
    {
        $this->add_car_location_column();
    }

    /**
     * Downgrade method.
     */
    public function down(): void
    {
        if ($this->db->field_exists('car_location', 'appointments')) {
            $this->dbforge->drop_column('appointments', 'car_location');
        }
    }

    private function add_car_location_column(): void
    {
        if (!$this->db->field_exists('car_location', 'appointments')) {
            $fields = [
                'car_location' => [
                    'type' => 'VARCHAR',
                    'constraint' => '255',
                    'null' => true,
                    'after' => 'car_plate',
                ],
            ];

            $this->dbforge->add_column('appointments', $fields);
        }

        $this->db->query(
            sprintf(
                "UPDATE `%s` SET `car_location` = '%s' WHERE `car_location` IS NULL OR `car_location` = ''",
                $this->db->dbprefix('appointments'),
                self::CAR_LOCATION_OWNER,
            ),
        );
    }
}