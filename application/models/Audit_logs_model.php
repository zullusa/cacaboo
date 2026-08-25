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
 * Audit logs model.
 *
 * Handles all the database operations of the audit log resource.
 *
 * @package Models
 */
class Audit_logs_model extends EA_Model
{
    /**
     * @var array
     */
    protected array $casts = [
        'id' => 'integer',
        'user_id' => 'integer',
        'entity_id' => 'integer',
    ];

    /**
     * Save (insert) an audit log entry.
     *
     * @param array $log Associative array with the log data.
     *
     * @return int Returns the log ID.
     *
     * @throws InvalidArgumentException
     */
    public function save(array $log): int
    {
        $this->validate($log);

        if (!empty($log['changes']) && is_array($log['changes'])) {
            $log['changes'] = json_encode($log['changes'], JSON_UNESCAPED_UNICODE);
        }

        $log['create_datetime'] = date('Y-m-d H:i:s');

        if (!$this->db->insert('audit_logs', $log)) {
            throw new RuntimeException('Could not insert audit log entry.');
        }

        return $this->db->insert_id();
    }

    /**
     * Validate the audit log data.
     *
     * @param array $log Associative array with the log data.
     *
     * @throws InvalidArgumentException
     */
    public function validate(array $log): void
    {
        if (empty($log['action'])) {
            throw new InvalidArgumentException('The action field is required: ' . print_r($log, true));
        }

        if (!in_array($log['action'], ['created', 'updated', 'deleted'], true)) {
            throw new InvalidArgumentException('Unsupported audit log action provided: ' . $log['action']);
        }

        if (empty($log['entity_type'])) {
            throw new InvalidArgumentException('The entity_type field is required: ' . print_r($log, true));
        }
    }

    /**
     * Search audit log entries by the provided keyword.
     *
     * @param string $keyword Search keyword.
     * @param int|null $limit Record limit.
     * @param int|null $offset Record offset.
     * @param string|null $order_by Order by.
     *
     * @return array Returns an array of audit log entries.
     */
    public function search(string $keyword, ?int $limit = null, ?int $offset = null, ?string $order_by = null): array
    {
        if ($keyword !== '') {
            $this->db
                ->group_start()
                ->like('user_name', $keyword)
                ->or_like('entity_name', $keyword)
                ->or_like('entity_type', $keyword)
                ->or_like('action', $keyword)
                ->group_end();
        }

        $logs = $this->db
            ->select()
            ->from('audit_logs')
            ->limit($limit)
            ->offset($offset)
            ->order_by($this->quote_order_by($order_by), '', FALSE)
            ->get()
            ->result_array();

        foreach ($logs as &$log) {
            $this->decode($log);
        }

        return $logs;
    }

    /**
     * Get all audit log entries that match the provided criteria.
     *
     * @param array|string|null $where Where conditions.
     * @param int|null $limit Record limit.
     * @param int|null $offset Record offset.
     * @param string|null $order_by Order by.
     *
     * @return array Returns an array of audit log entries.
     */
    public function get(
        array|string|null $where = null,
        ?int $limit = null,
        ?int $offset = null,
        ?string $order_by = null,
    ): array {
        if ($where !== null) {
            $this->db->where($where);
        }

        if ($order_by !== null) {
            $this->db->order_by($this->quote_order_by($order_by), '', FALSE);
        }

        $logs = $this->db->get('audit_logs', $limit, $offset)->result_array();

        foreach ($logs as &$log) {
            $this->decode($log);
        }

        return $logs;
    }

    /**
     * Decode the JSON fields of an audit log entry.
     *
     * @param array $log Log data (passed by reference).
     */
    protected function decode(array &$log): void
    {
        $this->cast($log);

        $log['changes'] = json_decode((string) ($log['changes'] ?? ''), true) ?: [];
    }
}
