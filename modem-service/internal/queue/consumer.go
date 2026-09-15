package queue

import (
	"context"
	"log"
	"sync"
	"time"

	amqp "github.com/rabbitmq/amqp091-go"
)

// Consumer pulls messages off the provider queue (e.g. notifications_beeline)
// and keeps running across broker restarts: the connection is re-established
// with a backoff whenever it drops.
type Consumer struct {
	cfg Config

	mu   sync.Mutex
	conn *amqp.Connection
	ch   *amqp.Channel
}

func NewConsumer(cfg Config) *Consumer {
	cfg = cfg.withDefaults()
	return &Consumer{cfg: cfg}
}

// Run consumes messages and passes each Delivery to handler until ctx is
// cancelled. The handler is responsible for Ack/Nack/Reject on the delivery.
func (c *Consumer) Run(ctx context.Context, handler func(context.Context, amqp.Delivery)) error {
	backoff := time.Second
	for {
		if err := c.connect(ctx); err != nil {
			log.Printf("rabbitmq connect failed: %v; retrying in %s", err, backoff)
			if !sleepCtx(ctx, backoff) {
				return ctx.Err()
			}
			backoff = minDuration(backoff*2, 30*time.Second)
			continue
		}
		backoff = time.Second

		ch, conn := c.chanAndConn()

		notify := make(chan *amqp.Error, 2)
		ch.NotifyClose(notify)
		conn.NotifyClose(notify)

		deliveries, err := ch.Consume(c.cfg.Queue, "", false, false, false, false, nil)
		if err != nil {
			log.Printf("rabbitmq consume failed: %v; reconnecting", err)
			c.close()
			continue
		}
		log.Printf("consuming queue %q (host=%s)", c.cfg.Queue, c.cfg.Host)

		handled := make(chan struct{})
		go func() {
			defer close(handled)
			for {
				select {
				case d, ok := <-deliveries:
					if !ok {
						return
					}
					handler(ctx, d)
				case <-ctx.Done():
					return
				case <-notify:
					return
				}
			}
		}()

		select {
		case <-ctx.Done():
			c.close()
			<-handled
			return ctx.Err()
		case <-notify:
			log.Printf("rabbitmq connection/channel closed; reconnecting")
			c.close()
			<-handled
		}
	}
}

// Ack acknowledges a delivery on the current channel.
func (c *Consumer) Ack(tag uint64) error {
	c.mu.Lock()
	defer c.mu.Unlock()
	if c.ch == nil {
		return errDisconnected
	}
	return c.ch.Ack(tag, false)
}

// Nack rejects a delivery, optionally requeueing it.
func (c *Consumer) Nack(tag uint64, requeue bool) error {
	c.mu.Lock()
	defer c.mu.Unlock()
	if c.ch == nil {
		return errDisconnected
	}
	return c.ch.Nack(tag, false, requeue)
}

func (c *Consumer) chanAndConn() (*amqp.Channel, *amqp.Connection) {
	c.mu.Lock()
	defer c.mu.Unlock()
	return c.ch, c.conn
}

func (c *Consumer) connect(ctx context.Context) error {
	c.close()

	conn, err := amqp.DialConfig(c.cfg.URL(), amqp.Config{Heartbeat: c.cfg.Heartbeat})
	if err != nil {
		return err
	}

	ch, err := conn.Channel()
	if err != nil {
		_ = conn.Close()
		return err
	}

	if err := ch.Qos(c.cfg.Prefetch, 0, false); err != nil {
		_ = ch.Close()
		_ = conn.Close()
		return err
	}

	if _, err := ch.QueueDeclare(c.cfg.Queue, true, false, false, false, nil); err != nil {
		_ = ch.Close()
		_ = conn.Close()
		return err
	}

	if c.cfg.Exchange != "" {
		if err := ch.ExchangeDeclare(c.cfg.Exchange, "direct", true, false, false, false, nil); err != nil {
			_ = ch.Close()
			_ = conn.Close()
			return err
		}
		if err := ch.QueueBind(c.cfg.Queue, c.cfg.RoutingKey, c.cfg.Exchange, false, nil); err != nil {
			_ = ch.Close()
			_ = conn.Close()
			return err
		}
	}

	c.mu.Lock()
	c.conn = conn
	c.ch = ch
	c.mu.Unlock()
	return nil
}

func (c *Consumer) close() {
	c.mu.Lock()
	defer c.mu.Unlock()
	if c.ch != nil {
		_ = c.ch.Close()
		c.ch = nil
	}
	if c.conn != nil {
		_ = c.conn.Close()
		c.conn = nil
	}
}

func sleepCtx(ctx context.Context, d time.Duration) bool {
	t := time.NewTimer(d)
	defer t.Stop()
	select {
	case <-ctx.Done():
		return false
	case <-t.C:
		return true
	}
}

func minDuration(a, b time.Duration) time.Duration {
	if a < b {
		return a
	}
	return b
}
