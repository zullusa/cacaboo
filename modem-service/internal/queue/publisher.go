package queue

import (
	"context"
	"sync"

	amqp "github.com/rabbitmq/amqp091-go"
)

// Publisher publishes messages to the notified feedback queue, recreating the
// connection on demand. It mirrors the RabbitMqNotifiedPublisher used by the
// Python sms-service: a durable queue, and a durable direct exchange binding
// when an exchange is configured.
type Publisher struct {
	cfg Config

	mu   sync.Mutex
	conn *amqp.Connection
	ch   *amqp.Channel
}

func NewPublisher(cfg Config) *Publisher {
	cfg = cfg.withDefaults()
	return &Publisher{cfg: cfg}
}

// Publish sends body to RoutingKey (defaults to the queue name).
func (p *Publisher) Publish(ctx context.Context, routingKey string, body []byte) error {
	p.mu.Lock()
	defer p.mu.Unlock()

	if err := p.ensure(); err != nil {
		return err
	}

	return p.ch.PublishWithContext(
		ctx,
		p.cfg.Exchange,
		routingKey,
		false,
		false,
		amqp.Publishing{
			ContentType:  "application/json",
			DeliveryMode: amqp.Persistent,
			Body:         body,
		},
	)
}

func (p *Publisher) ensure() error {
	if p.conn != nil && !p.conn.IsClosed() && p.ch != nil {
		return nil
	}

	conn, err := amqp.DialConfig(p.cfg.URL(), amqp.Config{Heartbeat: p.cfg.Heartbeat})
	if err != nil {
		return err
	}

	ch, err := conn.Channel()
	if err != nil {
		_ = conn.Close()
		return err
	}

	if _, err := ch.QueueDeclare(p.cfg.Queue, true, false, false, false, nil); err != nil {
		_ = ch.Close()
		_ = conn.Close()
		return err
	}

	if p.cfg.Exchange != "" {
		if err := ch.ExchangeDeclare(p.cfg.Exchange, "direct", true, false, false, false, nil); err != nil {
			_ = ch.Close()
			_ = conn.Close()
			return err
		}
		if err := ch.QueueBind(p.cfg.Queue, p.cfg.RoutingKey, p.cfg.Exchange, false, nil); err != nil {
			_ = ch.Close()
			_ = conn.Close()
			return err
		}
	}

	if p.conn != nil {
		_ = p.conn.Close()
	}
	if p.ch != nil {
		_ = p.ch.Close()
	}
	p.conn = conn
	p.ch = ch
	return nil
}
