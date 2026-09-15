package queue

import (
	"errors"
	"fmt"
	"net/url"
	"time"
)

var errDisconnected = errors.New("rabbitmq disconnected")

// Config is the RabbitMQ connection config shared by the consumer and the
// notified publisher.
type Config struct {
	Host       string
	Port       int
	User       string
	Password   string
	VHost      string
	Queue      string
	Exchange   string
	RoutingKey string
	Heartbeat  time.Duration
	Prefetch   int
}

func (c Config) URL() string {
	return fmt.Sprintf(
		"amqp://%s:%s@%s:%d/%s",
		url.QueryEscape(c.User),
		url.QueryEscape(c.Password),
		c.Host,
		c.Port,
		url.QueryEscape(c.VHost),
	)
}

func (c Config) withDefaults() Config {
	if c.VHost == "" {
		c.VHost = "/"
	}
	if c.RoutingKey == "" {
		c.RoutingKey = c.Queue
	}
	if c.Heartbeat == 0 {
		c.Heartbeat = 60 * time.Second
	}
	if c.Prefetch <= 0 {
		c.Prefetch = 10
	}
	return c
}
