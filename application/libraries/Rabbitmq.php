<?php defined('BASEPATH') or exit('No direct script access allowed');

/* ----------------------------------------------------------------------------
 * Easy!Appointments - Open Source Web Scheduler
 *
 * @package     EasyAppointments
 * @author      A.Tselegidis <alextselegidis@gmail.com>
 * @copyright   Copyright (c) Alex Tselegidis
 * @license     https://opensource.org/licenses/GPL-3.0 - GPLv3
 * @link        https://easyappointments.org
 * @since       v1.6.0
 * ---------------------------------------------------------------------------- */

use PhpAmqpLib\Channel\AMQPChannel;
use PhpAmqpLib\Connection\AMQPStreamConnection;
use PhpAmqpLib\Message\AMQPMessage;

/**
 * RabbitMQ library.
 *
 * Handles the RabbitMQ messaging related functionality.
 *
 * @package Libraries
 */
class Rabbitmq
{
    /**
     * @var EA_Controller|CI_Controller
     */
    protected EA_Controller|CI_Controller $CI;

    protected ?AMQPStreamConnection $connection = null;

    protected ?AMQPChannel $channel = null;

    /**
     * Notifications constructor.
     */
    public function __construct()
    {
        $this->CI = &get_instance();
    }

    /**
     * Publish a notification message to the configured RabbitMQ queue.
     *
     * The payload is expected to contain the following keys:
     *
     * - "type":    The notification type (e.g. "appointment_saved").
     * - "phone":   The recipient phone number (can be empty).
     * - "email":   The recipient email address (can be empty).
     * - "subject": The notification subject.
     * - "message": The plain-text message that is sent to the recipient.
     *
     * @param array $payload Notification payload.
     *
     * @return bool Returns TRUE on success or FALSE if the message could not be published.
     */
    public function publish_notification(array $payload): bool
    {
        if (empty($payload['email']) && empty($payload['phone'])) {
            log_message('error', 'RabbitMQ - Cannot publish notification without a recipient.');

            return false;
        }

        try {
            $channel = $this->get_channel();

            if ($channel === null) {
                return false;
            }

            $queue = (string) config('rabbitmq_queue', 'notifications');
            $exchange = (string) config('rabbitmq_exchange', '');
            $routing_key = (string) config('rabbitmq_routing_key', $queue);

            $channel->queue_declare($queue, false, true, false, false);

            if ($exchange !== '') {
                $channel->exchange_declare($exchange, 'direct', false, true, false);
                $channel->queue_bind($queue, $exchange, $routing_key);
            }

            $message = new AMQPMessage(
                json_encode($payload, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES),
                [
                    'content_type' => 'application/json',
                    'delivery_mode' => AMQPMessage::DELIVERY_MODE_PERSISTENT,
                ],
            );

            $channel->basic_publish($message, $exchange, $routing_key);

            return true;
        } catch (Throwable $e) {
            log_message('error', 'RabbitMQ - Could not publish notification: ' . $e->getMessage());

            $this->disconnect();

            return false;
        }
    }

    /**
     * Get the active channel, connecting to the broker if necessary.
     */
    private function get_channel(): ?AMQPChannel
    {
        if ($this->connection === null || !$this->connection->isConnected()) {
            $this->connect();
        }

        return $this->channel;
    }

    /**
     * Establish a new connection to the RabbitMQ broker.
     */
    private function connect(): void
    {
        $this->disconnect();

        $this->connection = new AMQPStreamConnection(
            (string) config('rabbitmq_host', 'localhost'),
            (int) config('rabbitmq_port', 5672),
            (string) config('rabbitmq_user', 'guest'),
            (string) config('rabbitmq_password', 'guest'),
            (string) config('rabbitmq_vhost', '/'),
            false,
            'AMQPLAIN',
            null,
            'en_US',
            3.0,
            10.0,
            null,
            false,
            0,
        );

        $this->channel = $this->connection->channel();
    }

    /**
     * Close the active channel and connection.
     */
    private function disconnect(): void
    {
        if ($this->channel !== null && $this->channel->is_open()) {
            $this->channel->close();
        }

        if ($this->connection !== null && $this->connection->isConnected()) {
            $this->connection->close();
        }

        $this->channel = null;
        $this->connection = null;
    }
}