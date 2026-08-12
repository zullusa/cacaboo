<?php defined('BASEPATH') or exit('No direct script access allowed');

/*
|--------------------------------------------------------------------------
| Google Calendar - Internal Configuration
|--------------------------------------------------------------------------
|
| Declare some of the global config values of the Google Calendar
| synchronization feature.
|
| These values serve as fallback when database settings are not available.
| The primary configuration should be done through the admin UI at
| Settings > Integrations > Google Calendar.
|
*/

$google_sync_feature = getenv('GOOGLE_SYNC_FEATURE');
$config['google_sync_feature'] = $google_sync_feature === false
    ? false
    : filter_var($google_sync_feature, FILTER_VALIDATE_BOOLEAN);

$config['google_client_id'] = getenv('GOOGLE_CLIENT_ID') ?: '';

$config['google_client_secret'] = getenv('GOOGLE_CLIENT_SECRET') ?: '';
