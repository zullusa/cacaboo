<?php defined('BASEPATH') or exit('No direct script access allowed');

/*
|--------------------------------------------------------------------------
| App Configuration
|--------------------------------------------------------------------------
|
| Declare some of the global config values of Easy!Appointments.
|
*/

$config['version'] = '1.6.0'; // This must be changed manually.

$config['url'] = getenv('BASE_URL') ?: 'http://localhost';

$debug_mode = getenv('DEBUG_MODE');
$config['debug'] = $debug_mode === false ? false : filter_var($debug_mode, FILTER_VALIDATE_BOOLEAN);

$config['cache_busting_token'] = 'TSJ87';
