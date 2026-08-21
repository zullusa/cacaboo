<?php defined('BASEPATH') or exit('No direct script access allowed');

// Add custom values by settings them to the $config array.
// Example: $config['smtp_host'] = 'smtp.gmail.com';
// @link https://codeigniter.com/user_guide/libraries/email.html

$config['useragent'] = 'CaCaBoo';
$config['protocol'] = 'mail'; // or 'smtp'
$config['mailtype'] = 'text'; // or 'text'
// $config['smtp_debug'] = '0'; // or '1'
// $config['smtp_auth'] = TRUE; //or FALSE for anonymous relay.
// $config['smtp_host'] = '';
// $config['smtp_user'] = '';
// $config['smtp_pass'] = '';
// $config['smtp_crypto'] = 'ssl'; // or 'tls'
// $config['smtp_port'] = 25;
// $config['from_name'] = '';
// $config['from_address'] = '';
// $config['reply_to'] = '';
$config['crlf'] = "\r\n";
$config['newline'] = "\r\n";

// RabbitMQ notification transport.
// When enabled, notification messages are published to the RabbitMQ queue
// instead of being sent directly. On failure the application falls back to the
// direct PHPMailer sending described above.
$rabbitmq_enabled_env = getenv('RABBITMQ_ENABLED');
$config['rabbitmq_enabled'] = $rabbitmq_enabled_env !== false
    ? filter_var($rabbitmq_enabled_env, FILTER_VALIDATE_BOOLEAN)
    : false;
$config['rabbitmq_host'] = getenv('RABBITMQ_HOST') ?: 'rabbitmq';
$config['rabbitmq_port'] = (int) (getenv('RABBITMQ_PORT') ?: 5672);
$config['rabbitmq_user'] = getenv('RABBITMQ_USER') ?: 'guest';
$config['rabbitmq_password'] = getenv('RABBITMQ_PASSWORD') ?: 'guest';
$config['rabbitmq_vhost'] = getenv('RABBITMQ_VHOST') ?: '/';
$config['rabbitmq_queue'] = getenv('RABBITMQ_QUEUE') ?: 'notifications';
$config['rabbitmq_exchange'] = getenv('RABBITMQ_EXCHANGE') ?: 'notifications_exchange';
$config['rabbitmq_routing_key'] = getenv('RABBITMQ_ROUTING_KEY') ?: 'notifications';

// Reminder notifications (same defaults as the reminder worker).
$config['reminder_address'] = getenv('ADDRESS') ?: 'Пушкина,19';
$config['reminder_contact_phone'] = getenv('CONTACT_PHONE') ?: '+74955554433';
$config['reminder_type'] = getenv('REMINDER_TYPE') ?: 'appointment_reminder';
$config['reminder_subject'] = getenv('REMINDER_SUBJECT') ?: 'Напоминание о записи на СТО';
$config['reminder_phone_prefix'] = getenv('REMINDER_PHONE_PREFIX') ?: '+7';
