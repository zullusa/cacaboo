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
 * Creates the "audit_logs" table.
 *
 * Stores the user action history (created / updated / deleted records) with a
 * JSON map of the changes: {added: {...}, changed: {...}, deleted: {...}}.
 */
class Migration_Create_audit_logs_table extends EA_Migration
{
    /**
     * Upgrade method.
     */
    public function up(): void
    {
        if ($this->db->table_exists('audit_logs')) {
            return;
        }

        $this->dbforge->add_field([
            'id' => [
                'type' => 'INT',
                'constraint' => 11,
                'auto_increment' => true,
            ],
            'user_id' => [
                'type' => 'INT',
                'constraint' => 11,
                'null' => true,
            ],
            'user_name' => [
                'type' => 'VARCHAR',
                'constraint' => '512',
                'null' => true,
            ],
            'action' => [
                'type' => 'VARCHAR',
                'constraint' => '32',
                'null' => false,
            ],
            'entity_type' => [
                'type' => 'VARCHAR',
                'constraint' => '64',
                'null' => false,
            ],
            'entity_id' => [
                'type' => 'INT',
                'constraint' => 11,
                'null' => true,
            ],
            'entity_name' => [
                'type' => 'VARCHAR',
                'constraint' => '512',
                'null' => true,
            ],
            'changes' => [
                'type' => 'LONGTEXT',
                'null' => true,
            ],
            'create_datetime' => [
                'type' => 'DATETIME',
                'null' => true,
            ],
        ]);

        $this->dbforge->add_key('id', true);

        $this->dbforge->add_key('user_id');

        $this->dbforge->add_key('entity_type');

        $this->dbforge->add_key('create_datetime');

        $this->dbforge->create_table('audit_logs', true, ['engine' => 'InnoDB']);
    }

    /**
     * Downgrade method.
     */
    public function down(): void
    {
        if ($this->db->table_exists('audit_logs')) {
            $this->dbforge->drop_table('audit_logs');
        }
    }
}
