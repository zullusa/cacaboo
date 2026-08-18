<?php defined('BASEPATH') or exit('No direct script access allowed');

/* ----------------------------------------------------------------------------
 * Easy!Appointments - Online Appointment Scheduler
 *
 * @package     EasyAppointments
 * @author      A.Tselegidis <alextselegidis@gmail.com>
 * @copyright   Copyright (c) Alex Tselegidis
 * @license     https://opensource.org/licenses/GPL-3.0 - GPLv3
 * @link        https://easyappointments.org
 * @since       v1.1.0
 * ---------------------------------------------------------------------------- */

/**
 * Installation controller.
 *
 * Handles the installation related operations.
 *
 * @package Controllers
 */
class Installation extends EA_Controller
{
    /**
     * Installation constructor.
     */
    public function __construct()
    {
        parent::__construct();

        $this->load->model('admins_model');
        $this->load->model('settings_model');
        $this->load->model('services_model');
        $this->load->model('providers_model');

        $this->load->library('instance');
    }

    /**
     * Display the installation page.
     */
    public function index(): void
    {
        method('get');

        if (is_app_installed()) {
            redirect();
            return;
        }

        $this->force_russian_language();

        $this->load->view('pages/installation', [
            'base_url' => config('base_url'),
        ]);
    }

    /**
     * Make sure the installation page is always rendered in Russian.
     */
    private function force_russian_language(): void
    {
        config([
            'language' => 'russian',
            'language_code' => 'ru',
        ]);

        $this->lang->load('translations', 'russian');
    }

    /**
     * Installs Easy!Appointments on the server.
     */
    public function perform(): void
    {
        try {
            method('post');

            if (is_app_installed()) {
                return;
            }

            check('admin', 'array');
            check('company', 'array');

            $admin = request('admin');
            $company = request('company');

            // Validate admin data
            if (empty($admin) || !is_array($admin)) {
                throw new InvalidArgumentException('Invalid admin data provided.');
            }

            // Validate required admin fields
            if (
                empty($admin['first_name']) ||
                empty($admin['last_name']) ||
                empty($admin['email']) ||
                empty($admin['username']) ||
                empty($admin['password'])
            ){
                throw new InvalidArgumentException('Missing required admin fields.');
            }

            // Validate email format
            if (!filter_var($admin['email'], FILTER_VALIDATE_EMAIL)) {
                throw new InvalidArgumentException('Invalid admin email format.');
            }

            // Validate username format (alphanumeric, underscore, dash, @, dot)
            if (!preg_match('/^[a-zA-Z0-9_@.\-]{3,50}$/', $admin['username'])) {
                throw new InvalidArgumentException(
                    'Invalid username format. Use 3-50 alphanumeric characters, underscores, dashes, @ or dots.',
                );
            }

            // Validate password strength
            if (strlen($admin['password']) < 8) {
                throw new InvalidArgumentException('Password must be at least 8 characters long.');
            }

            // Validate company data
            if (empty($company) || !is_array($company)) {
                throw new InvalidArgumentException('Invalid company data provided.');
            }

            // Validate required company fields
            if (empty($company['company_name']) || empty($company['company_email'])) {
                throw new InvalidArgumentException('Missing required company fields.');
            }

            // Validate company email format
            if (!filter_var($company['company_email'], FILTER_VALIDATE_EMAIL)) {
                throw new InvalidArgumentException('Invalid company email format.');
            }

            // Validate company link if provided
            if (!empty($company['company_link']) && !filter_var($company['company_link'], FILTER_VALIDATE_URL)) {
                throw new InvalidArgumentException('Invalid company link URL format.');
            }

            // Sanitize string inputs
            $admin['first_name'] = strip_tags(trim($admin['first_name']));
            $admin['last_name'] = strip_tags(trim($admin['last_name']));

            if (!empty($admin['phone_number'])) {
                $admin['phone_number'] = strip_tags(trim($admin['phone_number']));
            }

            $company['company_name'] = strip_tags(trim($company['company_name']));

            $this->instance->migrate();

            // Insert admin
            $admin['timezone'] = 'Europe/Moscow';
            $admin['settings']['username'] = $admin['username'];
            $admin['settings']['password'] = $admin['password'];
            $admin['settings']['notifications'] = true;
            $admin['settings']['calendar_view'] = CALENDAR_VIEW_DEFAULT;
            unset($admin['username'], $admin['password']);
            $admin['id'] = $this->admins_model->save($admin);

            session([
                'user_id' => $admin['id'],
                'user_email' => $admin['email'],
                'role_slug' => DB_SLUG_ADMIN,
                'language' => $admin['language'],
                'timezone' => $admin['timezone'],
                'username' => $admin['settings']['username'],
            ]);

            // Save company settings
            setting([
                'company_name' => $company['company_name'],
                'company_email' => $company['company_email'],
                'company_link' => $company['company_link'],
            ]);

            // Services
            $service_work_id = $this->services_model->save([
                'name' => 'В РАБОТУ',
                'duration' => '60',
                'price' => '0',
                'currency' => '',
                'slot_interval' => 120,
                'color' => '#abe9a4',
                'attendants_number' => '1',
                'is_private' => '0',
            ]);

            $service_first_id = $this->services_model->save([
                'name' => 'ПЕРВИЧКА',
                'duration' => '60',
                'price' => '0',
                'currency' => '',
                'slot_interval' => 120,
                'color' => '#ebe07c',
                'attendants_number' => '1',
                'is_private' => '0',
            ]);

            // Provider
            $this->providers_model->save([
                'name' => 'STO',
                'services' => [$service_work_id, $service_first_id],
            ]);

            json_response([
                'success' => true,
            ]);
        } catch (Throwable $e) {
            json_exception($e);
        }
    }
}
