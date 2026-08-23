package http

import (
	"strings"
	"testing"
	"unicode/utf8"

	"github.com/stretchr/testify/require"
)

func TestUnit_PrototypeWindow_CrossChunkDoesNotLeak(t *testing.T) {
	t.Parallel()
	w := mustPrototypeWindow(t, PrototypeWindowConfig{HoldbackRunes: 64})

	emit, err := w.Feed("hello SECR")
	require.NoError(t, err)
	require.NotContains(t, emit, "SECRET")
	require.NotContains(t, emit, "SECR") // still inside holdback

	emit, err = w.Feed("ET999 world")
	require.NoError(t, err)
	combined := emit
	emit, err = w.Flush()
	require.NoError(t, err)
	combined += emit

	require.Contains(t, combined, prototypeRedactToken)
	require.NotContains(t, combined, "SECRET999")
	require.Contains(t, combined, "hello")
	require.Contains(t, combined, "world")
}

func TestUnit_PrototypeWindow_Scenarios(t *testing.T) {
	t.Parallel()
	cases := []struct {
		name     string
		holdback int
		chunks   []string
		wantAll  string
		wantErr  error
	}{
		{
			name: "empty chunks", holdback: 64,
			chunks: []string{"", "hi", ""}, wantAll: "hi",
		},
		{
			name: "no secret passthrough", holdback: 64,
			chunks: []string{"abc", "def"}, wantAll: "abcdef",
		},
		{
			name: "secret in single chunk", holdback: 64,
			chunks: []string{"x SECRET1 y"}, wantAll: "x [REDACTED] y",
		},
		{
			name: "utf8 cut safe", holdback: 64,
			chunks: []string{"日本語SECRET2テスト"}, wantAll: "日本語[REDACTED]テスト",
		},
		{
			name: "split mid-secret", holdback: 64,
			chunks: []string{"a SECRET", "12 b"}, wantAll: "a [REDACTED] b",
		},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			w := mustPrototypeWindow(t, PrototypeWindowConfig{HoldbackRunes: tc.holdback})
			var out strings.Builder
			for _, c := range tc.chunks {
				emit, err := w.Feed(c)
				if tc.wantErr != nil {
					require.ErrorIs(t, err, tc.wantErr)
					return
				}
				require.NoError(t, err)
				out.WriteString(emit)
			}
			emit, err := w.Flush()
			require.NoError(t, err)
			out.WriteString(emit)
			require.Equal(t, tc.wantAll, out.String())
		})
	}
}

func TestUnit_PrototypeWindow_OverflowFailClosed(t *testing.T) {
	t.Parallel()
	w := mustPrototypeWindow(t, PrototypeWindowConfig{HoldbackRunes: 14, MaxBufferRunes: 20})
	_, err := w.Feed(strings.Repeat("a", 15))
	require.NoError(t, err)
	before := w.RetainedRunes()
	require.LessOrEqual(t, before, 20)
	_, err = w.Feed(strings.Repeat("b", 10))
	require.ErrorIs(t, err, ErrPrototypeBufferOverflow)
	require.Equal(t, before, w.RetainedRunes()) // failed Feed must not mutate buffer
}

func TestUnit_PrototypeWindow_InvalidConfig(t *testing.T) {
	t.Parallel()
	cases := []PrototypeWindowConfig{
		{HoldbackRunes: 5, MaxBufferRunes: 100}, // below max pattern
		{HoldbackRunes: 64, MaxBufferRunes: 10}, // holdback > max
		{HoldbackRunes: -1, MaxBufferRunes: 100},
	}
	for _, cfg := range cases {
		_, err := NewPrototypeWindowBuffer(cfg)
		require.ErrorIs(t, err, ErrPrototypeInvalidConfig)
	}
}

func TestUnit_PrototypeWindow_FlushEmitsHoldbackTail(t *testing.T) {
	t.Parallel()
	w := mustPrototypeWindow(t, PrototypeWindowConfig{HoldbackRunes: 64})
	emit, err := w.Feed(strings.Repeat("x", 100))
	require.NoError(t, err)
	require.Equal(t, 100-64, utf8.RuneCountInString(emit))
	require.Equal(t, 64, w.RetainedRunes())
	tail, err := w.Flush()
	require.NoError(t, err)
	require.Equal(t, 64, utf8.RuneCountInString(tail))
	require.Equal(t, 0, w.RetainedRunes())
}

func TestUnit_PrototypeWindow_IncompletePatternAtEndEmitted(t *testing.T) {
	t.Parallel()
	// Incomplete "SECR" cannot match; Flush must emit it (no silent drop).
	w := mustPrototypeWindow(t, PrototypeWindowConfig{HoldbackRunes: 64})
	_, err := w.Feed("SECR")
	require.NoError(t, err)
	out, err := w.Flush()
	require.NoError(t, err)
	require.Equal(t, "SECR", out)
}

func TestUnit_PrototypeWindow_NotWiredIntoStreamForward(t *testing.T) {
	t.Parallel()
	// Guardrail: production forwardSSEStream must not reference the prototype types.
	// Compile-time: PrototypeWindowBuffer is unused by stream_forward.go (no call sites).
	// Runtime smoke: constructing a buffer must not require router/bootstrap.
	w, err := NewPrototypeWindowBuffer(PrototypeWindowConfig{})
	require.NoError(t, err)
	require.NotNil(t, w)
}

func mustPrototypeWindow(t *testing.T, cfg PrototypeWindowConfig) *PrototypeWindowBuffer {
	t.Helper()
	w, err := NewPrototypeWindowBuffer(cfg)
	require.NoError(t, err)
	return w
}
