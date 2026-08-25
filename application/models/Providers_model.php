<?php defined('BASEPATH') or exit('No direct script access allowed');

/* ----------------------------------------------------------------------------
 * Easy!Appointments - Online Appointment Scheduler
 *
 * @package     EasyAppointments
 * @author      A.Tselegidis <alextselegidis@gmail.com>
 * @copyright   Copyright (c) Alex Tselegidis
 * @license     https://opensource.org/licenses/GPL-3.0 - GPLv3
 * @link        https://easyappointments.org
 * @since       v1.0.0
 * ---------------------------------------------------------------------------- */

/**
 * Providers model.
 *
 * Handles all the database operations of the provider resource.
 *
 * Providers are standalone entities (they are NOT system users). Each provider only has a name and a list of assigned
 * services. All the remaining attributes that are still expected by the rest of the application (email, settings,
 * working plan, timezone, ...) are provided as compatibility shims so that existing consumers keep working without
 * any additional changes.
 *
 * @package Models
 */
class Providers_model extends EA_Model
{
    /**
     * @var array
     */
    protected array $casts = [
        'id' => 'integer',
    ];

    /**
     * @var array
     */
    protected array $api_resource = [
        'id' => 'id',
        'name' => 'name',
        'firstName' => 'first_name',
        'lastName' => 'last_name',
        'email' => 'email',
        'services' => 'services',
    ];

    /**
     * Save (insert or update) a provider.
     *
     * @param array $provider Associative array with the provider data.
     *
     * @return int Returns the provider ID.
     *
     * @throws InvalidArgumentException
     * @throws Exception
     */
    public function save(array $provider): int
    {
        $this->validate($provider);

        if (empty($provider['id'])) {
            return $this->insert($provider);
        } else {
            return $this->update($provider);
        }
    }

    /**
     * Validate the provider data.
     *
     * @param array $provider Associative array with the provider data.
     *
     * @throws InvalidArgumentException
     */
    public function validate(array $provider): void
    {
        // If a provider ID is provided then check whether the record really exists in the database.
        if (!empty($provider['id'])) {
            $count = $this->db->get_where('providers', ['id' => $provider['id']])->num_rows();

            if (!$count) {
                throw new InvalidArgumentException(
                    'The provided provider ID does not exist in the database: ' . $provider['id'],
                );
            }
        }

        // The provider name is the only required field.
        if (empty($provider['name'])) {
            throw new InvalidArgumentException('The provider name is required: ' . print_r($provider, true));
        }

        // Validate provider services.
        if (!empty($provider['services'])) {
            // Make sure the provided service entries are numeric values.
            foreach ($provider['services'] as $service_id) {
                if (!is_numeric($service_id)) {
                    throw new InvalidArgumentException(
                        'The provided provider services are invalid: ' . print_r($provider, true),
                    );
                }
            }
        }
    }

    /**
     * Get all providers that match the provided criteria.
     *
     * @param array|string|null $where Where conditions
     * @param int|null $limit Record limit.
     * @param int|null $offset Record offset.
     * @param string|null $order_by Order by.
     *
     * @return array Returns an array of providers.
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

        $providers = $this->db->get('providers', $limit, $offset)->result_array();

        foreach ($providers as &$provider) {
            $this->decorate($provider);
        }

        return $providers;
    }

    /**
     * Get the provider settings.
     *
     * Providers do not have their own settings anymore. The returned values are compatibility shims so that the
     * rest of the application (availability, calendar, sync, ...) keeps working. The working plan comes from the
     * company business logic and the exceptions from the dedicated working plan exceptions table.
     *
     * @param int $provider_id Provider ID.
     */
    public function get_settings(int $provider_id): array
    {
        $settings = [
            'username' => '',
            'notifications' => false,
            'calendar_view' => CALENDAR_VIEW_DEFAULT,
            'google_sync' => false,
            'google_token' => null,
            'google_calendar' => null,
            'caldav_sync' => false,
            'caldav_url' => '',
            'caldav_username' => '',
            'caldav_password' => '',
            'sync_future_days' => 5,
            'sync_past_days' => 5,
            'working_plan' => setting('company_working_plan'),
        ];

        // Get working plan exceptions from the dedicated table in array format.
        $this->load->model('working_plan_exceptions_model');
        $exceptions = $this->working_plan_exceptions_model->get_all_by_provider($provider_id);
        $settings['working_plan_exceptions'] = json_encode($exceptions);

        return $settings;
    }

    /**
     * Get the provider service IDs.
     *
     * @param int $provider_id Provider ID.
     */
    public function get_service_ids(int $provider_id): array
    {
        $service_provider_connections = $this->db
            ->get_where('services_providers', ['id_users' => $provider_id])
            ->result_array();

        $service_ids = [];

        foreach ($service_provider_connections as $service_provider_connection) {
            $service_ids[] = (int) $service_provider_connection['id_services'];
        }

        return $service_ids;
    }

    /**
     * Insert a new provider into the database.
     *
     * @param array $provider Associative array with the provider data.
     *
     * @return int Returns the provider ID.
     *
     * @throws RuntimeException|Exception
     */
    protected function insert(array $provider): int
    {
        $provider['create_datetime'] = date('Y-m-d H:i:s');
        $provider['update_datetime'] = date('Y-m-d H:i:s');

        $service_ids = $provider['services'] ?? [];

        unset($provider['services'], $provider['settings']);

        if (!$this->db->insert('providers', $provider)) {
            throw new RuntimeException('Could not insert provider.');
        }

        $provider['id'] = $this->db->insert_id();

        $this->set_service_ids($provider['id'], $service_ids);

        return $provider['id'];
    }

    /**
     * Save the provider settings.
     *
     * Providers no longer have their own settings. This method is kept as a compatibility no-op so that existing
     * callers (e.g. the Google sync and business settings flows) do not break. Working plan exceptions are still
     * persisted to the dedicated table so that the calendar table view keeps working.
     *
     * @param int $provider_id Provider ID.
     * @param array $settings Associative array with the settings data.
     */
    public function set_settings(int $provider_id, array $settings): void
    {
        if (empty($settings)) {
            return;
        }

        foreach ($settings as $name => $value) {
            // Working plan exceptions are stored in a separate table.
            if ($name === 'working_plan_exceptions') {
                $this->load->model('working_plan_exceptions_model');

                $exceptions = json_decode($value, true);

                if (!$exceptions) {
                    $exceptions = [];
                }

                // Get existing exception IDs for this provider.
                $existing_exceptions = $this->db
                    ->select('id')
                    ->from('working_plan_exceptions')
                    ->where('id_users_provider', $provider_id)
                    ->get()
                    ->result_array();

                $existing_ids = array_column($existing_exceptions, 'id');
                $new_ids = [];

                // Save or update exceptions.
                foreach ($exceptions as $exception) {
                    $exception_id = $this->save_working_plan_exception($provider_id, $exception);
                    $new_ids[] = $exception_id;
                }

                // Delete exceptions that were not in the new list.
                $ids_to_delete = array_diff($existing_ids, $new_ids);
                if (!empty($ids_to_delete)) {
                    $this->db->where_in('id', $ids_to_delete)->delete('working_plan_exceptions');
                }

                continue;
            }
        }
    }

    /**
     * Set the value of a provider setting.
     *
     * Providers no longer have their own settings so this method is a compatibility no-op.
     *
     * @param int $provider_id Provider ID.
     * @param string $name Setting name.
     * @param mixed|null $value Setting value.
     */
    public function set_setting(int $provider_id, string $name, mixed $value = null): void
    {
        //
    }

    /**
     * Update an existing provider.
     *
     * @param array $provider Associative array with the provider data.
     *
     * @return int Returns the provider ID.
     *
     * @throws RuntimeException|Exception
     */
    protected function update(array $provider): int
    {
        $provider['update_datetime'] = date('Y-m-d H:i:s');

        $service_ids = $provider['services'] ?? [];

        unset($provider['services'], $provider['settings']);

        if (!$this->db->update('providers', $provider, ['id' => $provider['id']])) {
            throw new RuntimeException('Could not update provider.');
        }

        $this->set_service_ids($provider['id'], $service_ids);

        return $provider['id'];
    }

    /**
     * Save the provider service IDs.
     *
     * @param int $provider_id Provider ID.
     * @param array $service_ids Service IDs.
     */
    public function set_service_ids(int $provider_id, array $service_ids): void
    {
        // Re-insert the provider-service connections.
        $this->db->delete('services_providers', ['id_users' => $provider_id]);

        foreach ($service_ids as $service_id) {
            $service_provider_connection = [
                'id_users' => $provider_id,
                'id_services' => $service_id,
            ];

            $this->db->insert('services_providers', $service_provider_connection);
        }
    }

    /**
     * Remove an existing provider from the database.
     *
     * The related appointments, services_providers, working plan exceptions and secretaries_providers records are
     * removed by the ON DELETE CASCADE foreign keys.
     *
     * @param int $provider_id Provider ID.
     *
     * @throws RuntimeException
     */
    public function delete(int $provider_id): void
    {
        $this->db->delete('providers', ['id' => $provider_id]);
    }

    /**
     * Get a specific field value from the database.
     *
     * @param int $provider_id Provider ID.
     * @param string $field Name of the value to be returned.
     *
     * @return mixed Returns the selected provider value from the database.
     *
     * @throws InvalidArgumentException
     */
    public function value(int $provider_id, string $field): mixed
    {
        if (empty($field)) {
            throw new InvalidArgumentException('The field argument is cannot be empty.');
        }

        if (empty($provider_id)) {
            throw new InvalidArgumentException('The provider ID argument cannot be empty.');
        }

        // Check whether the provider exists.
        $query = $this->db->get_where('providers', ['id' => $provider_id]);

        if (!$query->num_rows()) {
            throw new InvalidArgumentException(
                'The provided provider ID was not found in the database: ' . $provider_id,
            );
        }

        // Check if the required field is part of the provider data.
        $provider = $query->row_array();

        $this->cast($provider);

        if (!array_key_exists($field, $provider)) {
            throw new InvalidArgumentException('The requested field was not found in the provider data: ' . $field);
        }

        return $provider[$field];
    }

    /**
     * Get the value of a provider setting.
     *
     * Providers no longer have their own settings so the requested value is a compatibility shim. The working plan
     * is always the company working plan and every other setting is returned as disabled.
     *
     * @param int $provider_id Provider ID.
     * @param string $name Setting name.
     *
     * @return string Returns the value of the requested setting.
     */
    public function get_setting(int $provider_id, string $name): string
    {
        $settings = $this->get_settings($provider_id);

        return $settings[$name] ?? '';
    }

    /**
     * Save a new or existing working plan exception.
     *
     * @param int $provider_id Provider ID.
     * @param array $working_plan_exception Associative array with the working plan exception data (startDate, endDate, startTime, endTime, breaks, id).
     *
     * @return int Returns the exception ID.
     *
     * @throws Exception
     */
    public function save_working_plan_exception(int $provider_id, array $working_plan_exception): int
    {
        // Validate the working plan exception data.
        $start_date = $working_plan_exception['startDate'] ?? null;
        $end_date = $working_plan_exception['endDate'] ?? $start_date;
        $start_time = $working_plan_exception['startTime'] ?? null;
        $end_time = $working_plan_exception['endTime'] ?? null;
        $breaks = $working_plan_exception['breaks'] ?? [];
        $id = $working_plan_exception['id'] ?? null;

        if (empty($start_date) || empty($end_date)) {
            throw new InvalidArgumentException('Start date and end date are required for working plan exception.');
        }

        if (strtotime($start_date) > strtotime($end_date)) {
            throw new InvalidArgumentException('Working plan exception start date must be before or equal to end date.');
        }

        // If start_time and end_time are provided, validate them.
        if (!empty($start_time) && !empty($end_time)) {
            $start = date('H:i', strtotime($start_time));
            $end = date('H:i', strtotime($end_time));

            if ($start > $end) {
                throw new InvalidArgumentException('Working plan exception start time must be before end time.');
            }
        }

        // Make sure the provider record exists.
        if ($this->db->get_where('providers', ['id' => $provider_id])->num_rows() === 0) {
            throw new InvalidArgumentException('Provider ID was not found in the database: ' . $provider_id);
        }

        $this->load->model('working_plan_exceptions_model');

        $exception_data = [
            'start_date' => $start_date,
            'end_date' => $end_date,
            'id_users_provider' => $provider_id,
            'start_time' => !empty($start_time) ? date('H:i', strtotime($start_time)) : null,
            'end_time' => !empty($end_time) ? date('H:i', strtotime($end_time)) : null,
            'breaks' => !empty($breaks) ? json_encode($breaks) : null,
        ];

        if ($id) {
            $exception_data['id'] = $id;
        }

        return $this->working_plan_exceptions_model->save($exception_data);
    }

    /**
     * Get a specific provider from the database.
     *
     * @param int $provider_id The ID of the record to be returned.
     *
     * @return array Returns an array with the provider data.
     *
     * @throws InvalidArgumentException
     */
    public function find(int $provider_id): array
    {
        $provider = $this->db->get_where('providers', ['id' => $provider_id])->row_array();

        if (!$provider) {
            throw new InvalidArgumentException(
                'The provided provider ID was not found in the database: ' . $provider_id,
            );
        }

        $this->decorate($provider);

        return $provider;
    }

    /**
     * Delete a provider working plan exception.
     *
     * @param string $date The working plan exception date (in YYYY-MM-DD format).
     * @param int $provider_id The selected provider record id.
     *
     * @throws Exception If $provider_id argument is invalid.
     */
    public function delete_working_plan_exception(int $provider_id, string $date): void
    {
        $this->load->model('working_plan_exceptions_model');

        $this->working_plan_exceptions_model->delete_by_provider_and_date($provider_id, $date);
    }

    /**
     * Get all the provider records that are assigned to at least one service.
     *
     * @param bool $without_private Only include the public providers (kept for compatibility, providers have no
     * privacy flag anymore).
     *
     * @return array Returns an array of providers.
     */
    public function get_available_providers(bool $without_private = false): array
    {
        $providers = $this->db
            ->select('providers.*')
            ->from('providers')
            ->join('services_providers', 'services_providers.id_users = providers.id', 'inner')
            ->order_by('name ASC')
            ->group_by('providers.id')
            ->get()
            ->result_array();

        foreach ($providers as &$provider) {
            $this->decorate($provider);
        }

        return $providers;
    }

    /**
     * Get the query builder interface, configured for use with the providers table.
     *
     * @return CI_DB_query_builder
     */
    public function query(): CI_DB_query_builder
    {
        return $this->db->from('providers');
    }

    /**
     * Search providers by the provided keyword.
     *
     * @param string $keyword Search keyword.
     * @param int|null $limit Record limit.
     * @param int|null $offset Record offset.
     * @param string|null $order_by Order by.
     *
     * @return array Returns an array of providers.
     */
    public function search(string $keyword, ?int $limit = null, ?int $offset = null, ?string $order_by = null): array
    {
        $providers = $this->db
            ->select()
            ->from('providers')
            ->group_start()
            ->like('name', $keyword)
            ->group_end()
            ->limit($limit)
            ->offset($offset)
            ->order_by($this->quote_order_by($order_by), '', FALSE)
            ->get()
            ->result_array();

        foreach ($providers as &$provider) {
            $this->decorate($provider);
        }

        return $providers;
    }

    /**
     * Get providers as options for dropdowns.
     *
     * @param array|string|null $where Where conditions.
     *
     * @return array Returns an array of options with 'value' and 'label' keys.
     */
    public function to_options(array|string|null $where = null): array
    {
        if ($where !== null) {
            $this->db->where($where);
        }

        $providers = $this->db
            ->select('id, name')
            ->from('providers')
            ->order_by('name')
            ->get()
            ->result_array();

        $options = [];

        foreach ($providers as $provider) {
            $options[] = [
                'value' => (int) $provider['id'],
                'label' => $provider['name'],
            ];
        }

        return $options;
    }

    /**
     * Load related resources to a provider.
     *
     * @param array $provider Associative array with the provider data.
     * @param array $resources Resource names to be attached ("services" supported).
     *
     * @throws InvalidArgumentException
     */
    public function load(array &$provider, array $resources): void
    {
        if (empty($provider) || empty($resources)) {
            return;
        }

        foreach ($resources as $resource) {
            $provider['services'] = match ($resource) {
                'services' => $this->db
                    ->select('services.*')
                    ->from('services')
                    ->join('services_providers', 'services_providers.id_services = services.id', 'inner')
                    ->where('services_providers.id_users', $provider['id'])
                    ->get()
                    ->result_array(),
                default => throw new InvalidArgumentException(
                    'The requested provider relation is not supported: ' . $resource,
                ),
            };
        }
    }

    /**
     * Convert the database provider record to the equivalent API resource.
     *
     * @param array $provider Provider data.
     */
    public function api_encode(array &$provider): void
    {
        $encoded_resource = [
            'id' => array_key_exists('id', $provider) ? (int) $provider['id'] : null,
            'name' => $provider['name'] ?? null,
            'firstName' => $provider['first_name'] ?? $provider['name'] ?? null,
            'lastName' => $provider['last_name'] ?? '',
            'email' => $provider['email'] ?? '',
        ];

        if (array_key_exists('services', $provider)) {
            $encoded_resource['services'] = $provider['services'];
        }

        if (array_key_exists('settings', $provider)) {
            $encoded_resource['settings'] = [
                'username' => $provider['settings']['username'] ?? '',
                'notifications' => filter_var($provider['settings']['notifications'] ?? false, FILTER_VALIDATE_BOOLEAN),
                'calendarView' => $provider['settings']['calendar_view'] ?? CALENDAR_VIEW_DEFAULT,
                'googleSync' => filter_var($provider['settings']['google_sync'] ?? false, FILTER_VALIDATE_BOOLEAN),
                'googleToken' => $provider['settings']['google_token'] ?? null,
                'googleCalendar' => $provider['settings']['google_calendar'] ?? null,
                'caldavSync' => filter_var($provider['settings']['caldav_sync'] ?? false, FILTER_VALIDATE_BOOLEAN),
                'caldavUrl' => $provider['settings']['caldav_url'] ?? '',
                'caldavUsername' => $provider['settings']['caldav_username'] ?? '',
                'caldavPassword' => $provider['settings']['caldav_password'] ?? '',
                'syncFutureDays' => (int) ($provider['settings']['sync_future_days'] ?? 5),
                'syncPastDays' => (int) ($provider['settings']['sync_past_days'] ?? 5),
                'workingPlan' => array_key_exists('working_plan', $provider['settings'])
                    ? json_decode($provider['settings']['working_plan'], true)
                    : null,
                'workingPlanExceptions' => array_key_exists('working_plan_exceptions', $provider['settings'])
                    ? json_decode($provider['settings']['working_plan_exceptions'], true)
                    : [],
            ];
        }

        $provider = $encoded_resource;
    }

    /**
     * Convert the API resource to the equivalent database provider record.
     *
     * @param array $provider API resource.
     * @param array|null $base Base provider data to be overwritten with the provided values (useful for updates).
     */
    public function api_decode(array &$provider, ?array $base = null): void
    {
        $decoded_resource = $base ?: [];

        if (array_key_exists('id', $provider)) {
            $decoded_resource['id'] = $provider['id'];
        }

        if (array_key_exists('name', $provider)) {
            $decoded_resource['name'] = $provider['name'];
        } elseif (array_key_exists('firstName', $provider)) {
            $decoded_resource['name'] = trim(($provider['firstName'] ?? '') . ' ' . ($provider['lastName'] ?? ''));
        }

        if (array_key_exists('services', $provider)) {
            $decoded_resource['services'] = $provider['services'];
        }

        $provider = $decoded_resource;
    }

    /**
     * Quickly check if a service is assigned to a provider.
     *
     * @param int $provider_id
     * @param int $service_id
     *
     * @return bool
     */
    public function is_service_supported(int $provider_id, int $service_id): bool
    {
        $provider = $this->find($provider_id);

        return in_array($service_id, $provider['services']);
    }

    /**
     * Decorate a provider record with the compatibility shims that are still expected by the rest of the application.
     *
     * @param array $provider Provider data (passed by reference).
     */
    protected function decorate(array &$provider): void
    {
        $this->cast($provider);

        $provider['first_name'] = $provider['name'];
        $provider['last_name'] = '';
        $provider['email'] = '';
        $provider['timezone'] = setting('default_timezone');
        $provider['settings'] = $this->get_settings($provider['id']);
        $provider['services'] = $this->get_service_ids($provider['id']);
    }
}