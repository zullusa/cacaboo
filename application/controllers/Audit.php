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
 * Audit controller.
 *
 * Handles the audit log page and the related search operations.
 *
 * @package Controllers
 */
class Audit extends EA_Controller
{
    /**
     * Audit constructor.
     */
    public function __construct()
    {
        parent::__construct();

        $this->load->model('audit_logs_model');
        $this->load->model('roles_model');

        $this->load->library('accounts');
    }

    /**
     * Render the audit log page.
     */
    public function index(): void
    {
        method('get');

        session(['dest_url' => site_url('audit')]);

        $user_id = session('user_id');

        if (cannot('view', PRIV_SYSTEM_SETTINGS)) {
            if ($user_id) {
                abort(403, 'Forbidden');
            }

            redirect('login');

            return;
        }

        $role_slug = session('role_slug');

        $logs = $this->audit_logs_model->search('', 50, 0, 'create_datetime DESC');

        script_vars([
            'user_id' => $user_id,
            'role_slug' => $role_slug,
            'logs' => $logs,
        ]);

        html_vars([
            'page_title' => lang('audit'),
            'active_menu' => PRIV_SYSTEM_SETTINGS,
            'user_display_name' => $this->accounts->get_user_display_name($user_id),
            'privileges' => $this->roles_model->get_permissions_by_slug($role_slug),
        ]);

        $this->load->view('pages/audit');
    }

    /**
     * Filter audit log entries by the provided keyword.
     */
    public function search(): void
    {
        try {
            method('post');

            if (cannot('view', PRIV_SYSTEM_SETTINGS)) {
                abort(403, 'Forbidden');
            }

            check('keyword', 'string|null');
            check('limit', 'numeric|null');
            check('offset', 'numeric|null');

            $keyword = request('keyword', '');

            $limit = request('limit', 50);

            $offset = (int) request('offset', '0');

            $logs = $this->audit_logs_model->search($keyword, $limit, $offset, 'create_datetime DESC');

            json_response($logs);
        } catch (Throwable $e) {
            json_exception($e);
        }
    }
}
