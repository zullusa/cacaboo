// Package modem holds the vendor-independent contract every modem backend
// implements. Both supported modems are driven through the same two operations —
// sending an SMS and reading the messages the device has stored — so the worker
// and the poller never have to know which firmware they are talking to.
package modem

import "context"

// IncomingSMS is one message read from a modem's message store. It is the
// normalized form of a Huawei `<Message>` entry and of a Keenetic RCI "nv-*" entry.
type IncomingSMS struct {
	// ID is the modem-local message id, needed to delete the message again.
	ID string
	// From is the sender: an operator name or a phone number.
	From string
	// Timestamp is the reception time in the vendor's own format.
	Timestamp string
	// Text is the message body. Delivery reports carry an empty body and are
	// replaced by a human readable description by the backend.
	Text string
}

// Sender delivers a single SMS through a modem.
type Sender interface {
	Send(ctx context.Context, phone, text string) error
}

// Inbox reads and removes the messages stored on a modem.
type Inbox interface {
	ListInbox(ctx context.Context) ([]IncomingSMS, error)
	DeleteSMS(ctx context.Context, id string) error
}

// Client is a modem the worker can send through and the poller can read from.
type Client interface {
	Sender
	Inbox
}
