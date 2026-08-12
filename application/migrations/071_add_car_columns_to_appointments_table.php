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

class Migration_Add_car_columns_to_appointments_table extends EA_Migration
{
    /**
     * Upgrade method.
     */
    public function up(): void
    {
        $this->add_car_columns();
    }

    /**
     * Downgrade method.
     */
    public function down(): void
    {
        $this->drop_car_columns();
    }

    private function add_car_columns(): void
    {
        if (!$this->db->field_exists('car_make', 'appointments')) {
            $fields = [
                'car_make' => [
                    'type' => 'VARCHAR',
                    'constraint' => '255',
                    'null' => true,
                    'after' => 'notes',
                ],
            ];

            $this->dbforge->add_column('appointments', $fields);
        }

        if (!$this->db->field_exists('car_plate', 'appointments')) {
            $fields = [
                'car_plate' => [
                    'type' => 'VARCHAR',
                    'constraint' => '255',
                    'null' => true,
                    'after' => 'car_make',
                ],
            ];

            $this->dbforge->add_column('appointments', $fields);
        }
    }

    private function drop_car_columns(): void
    {
        if ($this->db->field_exists('car_make', 'appointments')) {
            $this->dbforge->drop_column('appointments', 'car_make');
        }

        if ($this->db->field_exists('car_plate', 'appointments')) {
            $this->dbforge->drop_column('appointments', 'car_plate');
        }
    }
}