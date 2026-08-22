package tokenizer

import "errors"

var (
	// ErrMissingTokenizer is returned when a catalog family has no registry impl.
	ErrMissingTokenizer = errors.New("missing tokenizer implementation")
	// ErrDuplicateFamily is returned when two tokenizers claim the same family.
	ErrDuplicateFamily = errors.New("duplicate tokenizer family")
	// ErrUnknownFamily is returned for unrecognized family keys.
	ErrUnknownFamily = errors.New("unknown tokenizer family")
	// ErrTextTooLong is returned when input exceeds MaxCountTextBytes.
	ErrTextTooLong = errors.New("text exceeds tokenizer input limit")
	// ErrModelNotInCatalog is returned by CountForModel when model is absent.
	ErrModelNotInCatalog = errors.New("model not in capability catalog")
)
