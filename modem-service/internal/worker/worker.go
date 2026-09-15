package worker

import (
	"context"
	"encoding/json"
	"errors"
	"log"
	"strconv"

	amqp "github.com/rabbitmq/amqp091-go"

	"modem-service/internal/config"
	"modem-service/internal/metrics"
	"modem-service/internal/queue"
)

var (
	errNotAnObject   = errors.New("message is not a JSON object")
	errMissingFields = errors.New("message must contain a phone number and a text")
)

// Message is the domain model of a single SMS, parsed from the queue payload.
// The accepted key aliases mirror the Python sms-service (SmsMessage). Provider
// is the "provider" routing key the sms-service stamps on forwarded messages.
type Message struct {
	Phone         string
	Text          string
	Provider      string
	AppointmentID *int64
	OffsetDays    *int
}

var phoneKeys = []string{"phone_number", "phone", "to", "number", "mobile"}
var textKeys = []string{"message", "text", "body", "content"}
var providerKeys = []string{"provider", "provider_name", "routing_key"}
var idKeys = []string{"appointment_id", "appointmentId", "id"}

// SmsClient delivers a single SMS through the modem. *keenetic.Client is the
// production implementation; tests can substitute a fake.
type SmsClient interface {
	Send(ctx context.Context, phone, text string) error
}

// Worker delivers messages from the provider queue through the Keenetic modem
// and reports successful deliveries to the notified queue.
type Worker struct {
	cfg      *config.Config
	client   SmsClient
	notified *queue.Publisher
	label    string
}

func New(cfg *config.Config, client SmsClient) *Worker {
	return &Worker{
		cfg:    cfg,
		client: client,
		notified: queue.NewPublisher(queue.Config{
			Host:       cfg.RabbitMQHost,
			Port:       cfg.RabbitMQPort,
			User:       cfg.RabbitMQUser,
			Password:   cfg.RabbitMQPassword,
			VHost:      cfg.RabbitMQVHost,
			Queue:      cfg.NotifiedQueue,
			Exchange:   cfg.NotifiedExchange,
			RoutingKey: cfg.NotifiedRoutingKey,
			Heartbeat:  cfg.RabbitMQHeartbeat,
		}),
		label: cfg.Provider,
	}
}

// Consumer provides Ack/Nack on the current channel.
type Consumer interface {
	Ack(tag uint64) error
	Nack(tag uint64, requeue bool) error
}

// Handle processes a single delivery and acknowledges it accordingly.
func (w *Worker) Handle(ctx context.Context, consumer Consumer, d amqp.Delivery) {
	metrics.MessagesDrained.Inc(w.label)

	message, err := ParseMessage(d.Body)
	if err != nil {
		metrics.MessagesInvalid.Inc(w.label)
		_ = consumer.Nack(d.DeliveryTag, false)
		log.Printf("dropping malformed message: %v: %s", err, truncate(string(d.Body)))
		return
	}

	// The queue is shared between provider instances (notifications_others);
	// only the instance whose PROVIDER_FILTER matches the message's provider
	// routing key may deliver it. Non-matching messages are requeued so another
	// instance picks them up, and dropped once they bounce too often.
	if w.cfg.ProviderFilter != "" && message.Provider != w.cfg.ProviderFilter {
		metrics.MessagesSkipped.Inc(w.label)
		if retryCount(d) < w.cfg.MaxRequeue {
			log.Printf(
				"message for provider %q not for this instance (filter=%s), requeueing",
				message.Provider, w.cfg.ProviderFilter,
			)
			_ = consumer.Nack(d.DeliveryTag, true)
			return
		}
		log.Printf(
			"message for provider %q kept bouncing (filter=%s), dropping",
			message.Provider, w.cfg.ProviderFilter,
		)
		_ = consumer.Nack(d.DeliveryTag, false)
		return
	}

	if err := w.client.Send(ctx, message.Phone, message.Text); err != nil {
		metrics.MessagesFailed.Inc(w.label)
		if retryCount(d) < w.cfg.MaxRetries {
			log.Printf("send to %s failed (retry %d/%d): %v", message.Phone, retryCount(d)+1, w.cfg.MaxRetries, err)
			_ = consumer.Nack(d.DeliveryTag, true)
			return
		}
		metrics.MessagesDropped.Inc(w.label)
		log.Printf("send to %s failed permanently, dropping: %v", message.Phone, err)
		_ = consumer.Nack(d.DeliveryTag, false)
		return
	}

	metrics.MessagesSent.Inc(w.label)

	if err := consumer.Ack(d.DeliveryTag); err != nil {
		log.Printf("could not acknowledge delivery %d: %v", d.DeliveryTag, err)
		return
	}

	if message.AppointmentID != nil {
		if err := w.publishNotified(ctx, message); err != nil {
			metrics.PublishErrors.Inc(w.label)
			log.Printf("could not publish notified for appointment %d: %v", *message.AppointmentID, err)
		} else {
			metrics.NotifiedPublished.Inc(w.label)
		}
	}
}

func (w *Worker) publishNotified(ctx context.Context, message *Message) error {
	body := map[string]any{"appointment_id": *message.AppointmentID}
	if message.OffsetDays != nil {
		body["offset_days"] = *message.OffsetDays
	}
	payload, err := json.Marshal(body)
	if err != nil {
		return err
	}
	return w.notified.Publish(ctx, w.cfg.NotifiedRoutingKey, payload)
}

// ParseMessage converts a queue payload into a Message.
func ParseMessage(raw []byte) (*Message, error) {
	var payload map[string]any
	if err := json.Unmarshal(raw, &payload); err != nil {
		return nil, err
	}
	if payload == nil {
		return nil, errNotAnObject
	}

	phone := firstString(payload, phoneKeys...)
	text := firstString(payload, textKeys...)
	if phone == "" || text == "" {
		return nil, errMissingFields
	}

	message := &Message{
		Phone:    phone,
		Text:     text,
		Provider: firstString(payload, providerKeys...),
	}
	if id, ok := firstInt64(payload, idKeys...); ok {
		message.AppointmentID = &id
	}
	if offset, ok := firstInt(payload, "offset_days"); ok {
		message.OffsetDays = &offset
	}
	return message, nil
}

func firstString(payload map[string]any, keys ...string) string {
	for _, key := range keys {
		if v, ok := payload[key]; ok && v != nil {
			if s, ok := v.(string); ok && s != "" {
				return s
			}
		}
	}
	return ""
}

func firstInt64(payload map[string]any, keys ...string) (int64, bool) {
	for _, key := range keys {
		if v, ok := payload[key]; ok && v != nil {
			switch n := v.(type) {
			case float64:
				return int64(n), true
			case string:
				if parsed, err := strconv.ParseInt(n, 10, 64); err == nil {
					return parsed, true
				}
			}
		}
	}
	return 0, false
}

func firstInt(payload map[string]any, key string) (int, bool) {
	if v, ok := payload[key]; ok && v != nil {
		switch n := v.(type) {
		case float64:
			return int(n), true
		case string:
			if parsed, err := strconv.Atoi(n); err == nil {
				return parsed, true
			}
		}
	}
	return 0, false
}

// retryCount extracts the number of previous deliveries from the x-death
// header so requeued messages are dropped after MaxRetries attempts instead of
// cycling forever.
func retryCount(d amqp.Delivery) int {
	entries, ok := d.Headers["x-death"].([]any)
	if !ok {
		return 0
	}
	max := 0
	for _, entry := range entries {
		count := 0
		switch table := entry.(type) {
		case amqp.Table:
			count = tableCount(table)
		case map[string]any:
			count = tableCount(table)
		}
		if count > max {
			max = count
		}
	}
	return max
}

func tableCount(table map[string]any) int {
	switch n := table["count"].(type) {
	case int32:
		return int(n)
	case int64:
		return int(n)
	case int:
		return n
	}
	return 0
}

func truncate(s string) string {
	if len(s) > 300 {
		return s[:300] + "..."
	}
	return s
}
