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
 * Audit library.
 *
 * Tracks the user actions (created / updated / deleted records) into the
 * "audit_logs" table. The changes field contains a map with the added,
 * changed and removed values of the affected record.
 *
 * @package Libraries
 */
class Audit
{
    /**
     * Fields that must never be stored in the audit log.
     */
    protected const SENSITIVE_FIELDS = [
        'password',
        'salt',
        'password_reset_token',
        'password_reset_expires',
        'google_token',
        'caldav_username',
        'caldav_password',
        'secret_token',
    ];

    /**
     * Fields that add no value to the audit log.
     */
    protected const NOISY_FIELDS = [
        'create_datetime',
        'update_datetime',
    ];

    /**
     * @var EA_Controller
     */
    protected $CI;

    /**
     * Audit constructor.
     */
    public function __construct()
    {
        $this->CI =& get_instance();

        $this->CI->load->model('audit_logs_model');
    }

    /**
     * Track a user action into the audit log.
     *
     * @param string $action Either "created", "updated" or "deleted".
     * @param string $entity_type Entity type (e.g. "appointment", "customer").
     * @param int|null $entity_id Entity ID.
     * @param string $entity_name Human friendly name of the affected record.
     * @param array $new_data New record data (empty on delete).
     * @param array $old_data Old record data (empty on create).
     */
    public function track(
        string $action,
        string $entity_type,
        ?int $entity_id,
        string $entity_name = '',
        array $new_data = [],
        array $old_data = [],
    ): void {
        try {
            $changes = $this->diff($action, $new_data, $old_data);

            if ($action === 'updated' && empty($changes['changed'])) {
                return;
            }

            $user_id = (int) session('user_id');

            $this->CI->audit_logs_model->save([
                'user_id' => $user_id ?: null,
                'user_name' => $this->user_name($user_id),
                'action' => $action,
                'entity_type' => $entity_type,
                'entity_id' => $entity_id ?: null,
                'entity_name' => mb_substr($entity_name, 0, 512),
                'changes' => $this->mask_changes($entity_type, $entity_name, $changes),
            ]);
        } catch (Throwable $e) {
            log_message('error', 'Audit tracking failed: ' . $e->getMessage());
        }
    }

    /**
     * Get the display name of the user that performed the action.
     *
     * @param int $user_id User ID.
     *
     * @return string
     */
    protected function user_name(int $user_id): string
    {
        if (!$user_id) {
            return '';
        }

        try {
            return mb_substr($this->CI->accounts->get_user_display_name($user_id), 0, 512);
        } catch (Throwable $e) {
            return '#' . $user_id;
        }
    }

    /**
     * Mask sensitive values in the changes map before it gets stored.
     *
     * The comparison of the values happens on the raw data, only the stored
     * changes are masked (e.g. the value of the "api_token" setting).
     *
     * @param string $entity_type Entity type.
     * @param string $entity_name Entity name.
     * @param array $changes Changes map.
     *
     * @return array
     */
    protected function mask_changes(string $entity_type, string $entity_name, array $changes): array
    {
        if ($entity_type !== 'setting' || !preg_match('/token|secret|password|salt|hmac|_key/i', $entity_name)) {
            return $changes;
        }

        foreach (['added', 'deleted'] as $section) {
            if (array_key_exists('value', $changes[$section] ?? [])) {
                $changes[$section]['value'] = '***';
            }
        }

        foreach ($changes['changed'] as $field => &$pair) {
            if ($field === 'value') {
                $pair = ['from' => '***', 'to' => '***'];
            }
        }

        return $changes;
    }

    /**
     * Build the changes map of the tracked action.
     *
     * @param string $action Action name.
     * @param array $new_data New record data.
     * @param array $old_data Old record data.
     *
     * @return array Returns a map with the "added", "changed" and "deleted" values.
     */
    protected function diff(string $action, array $new_data, array $old_data): array
    {
        $new_data = $this->filter_fields($new_data);
        $old_data = $this->filter_fields($old_data);

        switch ($action) {
            case 'created':
                return ['added' => $new_data, 'changed' => [], 'deleted' => []];

            case 'deleted':
                return ['added' => [], 'changed' => [], 'deleted' => $old_data];

            default:
                $changed = [];

                foreach ($new_data as $field => $value) {
                    if (!array_key_exists($field, $old_data)) {
                        continue;
                    }

                    if ($this->normalize($old_data[$field]) === $this->normalize($value)) {
                        continue;
                    }

                    $changed[$field] = ['from' => $old_data[$field], 'to' => $value];
                }

                return ['added' => [], 'changed' => $changed, 'deleted' => []];
        }
    }

    /**
     * Remove sensitive and noisy fields from the provided data.
     *
     * @param array $data Record data.
     *
     * @return array
     */
    protected function filter_fields(array $data): array
    {
        return array_diff_key($data, array_flip(self::SENSITIVE_FIELDS), array_flip(self::NOISY_FIELDS));
    }

    /**
     * Normalize a value so that scalar comparisons are reliable.
     *
     * @param mixed $value Value to normalize.
     *
     * @return mixed
     */
    protected function normalize(mixed $value): mixed
    {
        if (is_array($value)) {
            return json_encode($value);
        }

        if ($value === null) {
            return '';
        }

        return (string) $value;
    }
}
