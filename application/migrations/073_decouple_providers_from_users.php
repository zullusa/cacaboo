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

class Migration_Decouple_providers_from_users extends EA_Migration
{
    /**
     * Upgrade method.
     */
    public function up(): void
    {
        // 1. Create the new providers table.
        if (!$this->db->table_exists('providers')) {
            $this->dbforge->add_field([
                'id' => [
                    'type' => 'INT',
                    'constraint' => '11',
                    'auto_increment' => true,
                ],
                'name' => [
                    'type' => 'VARCHAR',
                    'constraint' => '256',
                    'null' => true,
                ],
                'create_datetime' => [
                    'type' => 'DATETIME',
                    'null' => true,
                ],
                'update_datetime' => [
                    'type' => 'DATETIME',
                    'null' => true,
                ],
            ]);

            $this->dbforge->add_key('id', true);
            $this->dbforge->create_table('providers', true, ['engine' => 'InnoDB']);
        }

        // 2. Migrate existing provider users into the new providers table. The IDs are preserved so that existing
        // references from appointments, services_providers, working_plan_exceptions and secretaries_providers remain
        // valid.
        $provider_role = $this->db->get_where('roles', ['slug' => 'provider'])->row_array();

        $provider_users = [];

        if (!empty($provider_role)) {
            $provider_users = $this->db->get_where('users', ['id_roles' => $provider_role['id']])->result_array();

            foreach ($provider_users as $user) {
                $name = trim(($user['first_name'] ?? '') . ' ' . ($user['last_name'] ?? ''));

                $this->db->insert('providers', [
                    'id' => $user['id'],
                    'name' => $name ?: 'Provider',
                    'create_datetime' => $user['create_datetime'] ?? date('Y-m-d H:i:s'),
                    'update_datetime' => $user['update_datetime'] ?? date('Y-m-d H:i:s'),
                ]);
            }
        }

        // 3. Drop the foreign keys that reference the users table from the provider related columns.
        $this->db->query(
            'ALTER TABLE `' .
                $this->db->dbprefix('appointments') .
                '` DROP FOREIGN KEY `appointments_users_provider`',
        );

        $this->db->query(
            'ALTER TABLE `' .
                $this->db->dbprefix('services_providers') .
                '` DROP FOREIGN KEY `services_providers_users_provider`',
        );

        $this->db->query(
            'ALTER TABLE `' .
                $this->db->dbprefix('working_plan_exceptions') .
                '` DROP FOREIGN KEY `working_plan_exceptions_users_provider`',
        );

        $this->db->query(
            'ALTER TABLE `' .
                $this->db->dbprefix('secretaries_providers') .
                '` DROP FOREIGN KEY `secretaries_users_provider`',
        );

        // 4. Add new foreign keys that reference the new providers table.
        $this->db->query(
            'ALTER TABLE `' .
                $this->db->dbprefix('appointments') .
                '` ADD CONSTRAINT `appointments_providers_provider` FOREIGN KEY (`id_users_provider`) REFERENCES `' .
                $this->db->dbprefix('providers') .
                '` (`id`) ON DELETE CASCADE ON UPDATE CASCADE',
        );

        $this->db->query(
            'ALTER TABLE `' .
                $this->db->dbprefix('services_providers') .
                '` ADD CONSTRAINT `services_providers_provider` FOREIGN KEY (`id_users`) REFERENCES `' .
                $this->db->dbprefix('providers') .
                '` (`id`) ON DELETE CASCADE ON UPDATE CASCADE',
        );

        $this->db->query(
            'ALTER TABLE `' .
                $this->db->dbprefix('working_plan_exceptions') .
                '` ADD CONSTRAINT `working_plan_exceptions_provider` FOREIGN KEY (`id_users_provider`) REFERENCES `' .
                $this->db->dbprefix('providers') .
                '` (`id`) ON DELETE CASCADE ON UPDATE CASCADE',
        );

        $this->db->query(
            'ALTER TABLE `' .
                $this->db->dbprefix('secretaries_providers') .
                '` ADD CONSTRAINT `secretaries_providers_provider` FOREIGN KEY (`id_users_provider`) REFERENCES `' .
                $this->db->dbprefix('providers') .
                '` (`id`) ON DELETE CASCADE ON UPDATE CASCADE',
        );

        // 5. Remove the provider users from the users table. Their user_settings rows are removed by the ON DELETE
        // CASCADE foreign key of the user_settings table.
        if (!empty($provider_role)) {
            foreach ($provider_users as $user) {
                $this->db->where('id', $user['id'])->delete('users');
            }
        }
    }

    /**
     * Downgrade method.
     */
    public function down(): void
    {
        // Recreate provider users from the providers table.
        $providers = $this->db->get('providers')->result_array();

        $provider_role = $this->db->get_where('roles', ['slug' => 'provider'])->row_array();

        if (!empty($provider_role)) {
            foreach ($providers as $provider) {
                $this->db->insert('users', [
                    'id' => $provider['id'],
                    'first_name' => $provider['name'],
                    'last_name' => '',
                    'email' => 'provider-' . $provider['id'] . '@example.com',
                    'id_roles' => $provider_role['id'],
                    'create_datetime' => $provider['create_datetime'],
                    'update_datetime' => $provider['update_datetime'],
                ]);

                $this->db->insert('user_settings', [
                    'id_users' => $provider['id'],
                ]);
            }
        }

        // Drop the new foreign keys.
        $this->db->query(
            'ALTER TABLE `' .
                $this->db->dbprefix('appointments') .
                '` DROP FOREIGN KEY `appointments_providers_provider`',
        );

        $this->db->query(
            'ALTER TABLE `' .
                $this->db->dbprefix('services_providers') .
                '` DROP FOREIGN KEY `services_providers_provider`',
        );

        $this->db->query(
            'ALTER TABLE `' .
                $this->db->dbprefix('working_plan_exceptions') .
                '` DROP FOREIGN KEY `working_plan_exceptions_provider`',
        );

        $this->db->query(
            'ALTER TABLE `' .
                $this->db->dbprefix('secretaries_providers') .
                '` DROP FOREIGN KEY `secretaries_providers_provider`',
        );

        // Restore the foreign keys that reference the users table.
        $this->db->query(
            'ALTER TABLE `' .
                $this->db->dbprefix('appointments') .
                '` ADD CONSTRAINT `appointments_users_provider` FOREIGN KEY (`id_users_provider`) REFERENCES `' .
                $this->db->dbprefix('users') .
                '` (`id`) ON DELETE CASCADE ON UPDATE CASCADE',
        );

        $this->db->query(
            'ALTER TABLE `' .
                $this->db->dbprefix('services_providers') .
                '` ADD CONSTRAINT `services_providers_users_provider` FOREIGN KEY (`id_users`) REFERENCES `' .
                $this->db->dbprefix('users') .
                '` (`id`) ON DELETE CASCADE ON UPDATE CASCADE',
        );

        $this->db->query(
            'ALTER TABLE `' .
                $this->db->dbprefix('working_plan_exceptions') .
                '` ADD CONSTRAINT `working_plan_exceptions_users_provider` FOREIGN KEY (`id_users_provider`) REFERENCES `' .
                $this->db->dbprefix('users') .
                '` (`id`) ON DELETE CASCADE ON UPDATE CASCADE',
        );

        $this->db->query(
            'ALTER TABLE `' .
                $this->db->dbprefix('secretaries_providers') .
                '` ADD CONSTRAINT `secretaries_users_provider` FOREIGN KEY (`id_users_provider`) REFERENCES `' .
                $this->db->dbprefix('users') .
                '` (`id`) ON DELETE CASCADE ON UPDATE CASCADE',
        );
    }
}
