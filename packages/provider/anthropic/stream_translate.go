package anthropic

import (
	"bufio"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"strings"
	"sync"
	"time"

	"github.com/Rick1330/ibex-harness/packages/provider"
)

const (
	doneSentinel      = "[DONE]"
	maxSSELineBytes   = 1 << 20 // 1 MiB per SSE line (Scanner hard cap)
	maxSSEEventBytes  = 2 << 20 // 2 MiB assembled event data payload
	openAIChunkObject = "chat.completion.chunk"
)

// errPipeClosed is returned when the consumer closes the translate pipe intentionally.
var errPipeClosed = errors.New("anthropic stream translate pipe closed")

// streamTranslatePipe reads Anthropic named SSE and emits OpenAI chat.completion.chunk SSE.
// Backpressure is natural via io.Pipe: the producer blocks when the consumer is slow.
type streamTranslatePipe struct {
	pr         *io.PipeReader
	src        io.ReadCloser
	model      string
	requestID  string
	closeSrc   sync.Once
	readerDone chan struct{}
}

func newStreamTranslatePipe(src io.ReadCloser, model, requestID string) *streamTranslatePipe {
	pr, pw := io.Pipe()
	p := &streamTranslatePipe{
		pr:         pr,
		src:        src,
		model:      model,
		requestID:  requestID,
		readerDone: make(chan struct{}),
	}
	go p.run(pw)
	return p
}

func (p *streamTranslatePipe) Read(b []byte) (int, error) { return p.pr.Read(b) }

func (p *streamTranslatePipe) Close() error {
	// Closing the pipe reader unblocks any Write in run with a short error.
	_ = p.pr.Close()
	p.closeUpstream()
	<-p.readerDone
	return nil
}

func (p *streamTranslatePipe) closeUpstream() {
	p.closeSrc.Do(func() {
		_ = p.src.Close()
	})
}

func (p *streamTranslatePipe) run(pw *io.PipeWriter) {
	defer close(p.readerDone)
	defer p.closeUpstream()

	var runErr error
	defer func() {
		if runErr != nil && !errors.Is(runErr, errPipeClosed) {
			_ = pw.CloseWithError(runErr)
			return
		}
		_ = pw.Close()
	}()

	scanner := bufio.NewScanner(p.src)
	scanner.Buffer(make([]byte, 0, 64*1024), maxSSELineBytes)

	st := streamState{
		msgID:   p.requestID,
		model:   p.model,
		created: time.Now().Unix(),
		pw:      pw,
	}
	if st.msgID == "" {
		st.msgID = "chatcmpl-anthropic"
	}

	var eventType string
	var dataBuf strings.Builder

	flushEvent := func() error {
		data := strings.TrimSpace(dataBuf.String())
		et := strings.TrimSpace(eventType)
		eventType = ""
		dataBuf.Reset()
		if et == "" && data == "" {
			return nil
		}
		if et == "" {
			et = "message"
		}
		return st.handle(et, data)
	}

	for scanner.Scan() {
		line := scanner.Text()
		switch {
		case line == "":
			if err := flushEvent(); err != nil {
				runErr = err
				return
			}
		case strings.HasPrefix(line, ":"):
			// SSE comment / keepalive
			continue
		case strings.HasPrefix(line, "event:"):
			eventType = strings.TrimSpace(strings.TrimPrefix(line, "event:"))
		case strings.HasPrefix(line, "data:"):
			payload := strings.TrimSpace(strings.TrimPrefix(line, "data:"))
			if dataBuf.Len()+len(payload)+1 > maxSSEEventBytes {
				runErr = &provider.ProviderError{
					ProviderName:   "anthropic",
					StatusCode:     http.StatusBadGateway,
					ProviderErrMsg: "anthropic SSE event exceeds size limit",
				}
				return
			}
			if dataBuf.Len() > 0 {
				dataBuf.WriteByte('\n')
			}
			dataBuf.WriteString(payload)
		default:
			// Ignore unknown SSE fields (id:, retry:, etc.)
		}
	}
	if err := scanner.Err(); err != nil {
		runErr = err
		return
	}
	if err := flushEvent(); err != nil {
		runErr = err
		return
	}
	if !st.finishSent {
		if err := st.writeFinish("stop"); err != nil {
			runErr = err
			return
		}
	}
	if err := st.writeRaw("data: " + doneSentinel + "\n\n"); err != nil {
		runErr = err
		return
	}
}

// streamState is owned exclusively by the producer goroutine.
type streamState struct {
	msgID      string
	model      string
	created    int64
	roleSent   bool
	finishSent bool
	pw         *io.PipeWriter
}

func (st *streamState) handle(eventType, data string) error {
	switch eventType {
	case "error":
		return mapStreamError(data)
	case "message_start":
		return st.onMessageStart(data)
	case "content_block_delta":
		return st.onContentDelta(data)
	case "message_delta":
		return st.onMessageDelta(data)
	case "message_stop", "content_block_start", "content_block_stop", "ping":
		return nil
	default:
		return nil
	}
}

func (st *streamState) onMessageStart(data string) error {
	var payload struct {
		Message struct {
			ID    string `json:"id"`
			Model string `json:"model"`
		} `json:"message"`
	}
	if err := json.Unmarshal([]byte(data), &payload); err == nil {
		if payload.Message.ID != "" {
			st.msgID = payload.Message.ID
		}
		if payload.Message.Model != "" {
			st.model = payload.Message.Model
		}
	}
	return st.ensureRole()
}

func (st *streamState) onContentDelta(data string) error {
	var payload struct {
		Delta struct {
			Type string `json:"type"`
			Text string `json:"text"`
		} `json:"delta"`
	}
	if err := json.Unmarshal([]byte(data), &payload); err != nil {
		return nil // best-effort: skip malformed deltas
	}
	if payload.Delta.Type != "" && payload.Delta.Type != "text_delta" {
		return nil
	}
	if payload.Delta.Text == "" {
		return nil
	}
	if err := st.ensureRole(); err != nil {
		return err
	}
	return st.writeChunk(openAIStreamChunk{
		ID:      st.msgID,
		Object:  openAIChunkObject,
		Created: st.created,
		Model:   st.model,
		Choices: []openAIStreamChoice{{
			Index: 0,
			Delta: openAIStreamDelta{Content: payload.Delta.Text},
		}},
	})
}

func (st *streamState) onMessageDelta(data string) error {
	var payload struct {
		Delta struct {
			StopReason string `json:"stop_reason"`
		} `json:"delta"`
	}
	if err := json.Unmarshal([]byte(data), &payload); err != nil {
		return nil
	}
	if payload.Delta.StopReason == "" {
		return nil
	}
	return st.writeFinish(mapStopReason(payload.Delta.StopReason))
}

func (st *streamState) ensureRole() error {
	if st.roleSent {
		return nil
	}
	st.roleSent = true
	return st.writeChunk(openAIStreamChunk{
		ID:      st.msgID,
		Object:  openAIChunkObject,
		Created: st.created,
		Model:   st.model,
		Choices: []openAIStreamChoice{{
			Index: 0,
			Delta: openAIStreamDelta{Role: "assistant"},
		}},
	})
}

func (st *streamState) writeFinish(reason string) error {
	st.finishSent = true
	return st.writeChunk(openAIStreamChunk{
		ID:      st.msgID,
		Object:  openAIChunkObject,
		Created: st.created,
		Model:   st.model,
		Choices: []openAIStreamChoice{{
			Index:        0,
			FinishReason: strPtr(reason),
		}},
	})
}

func mapStreamError(data string) error {
	var payload struct {
		Error struct {
			Type    string `json:"type"`
			Message string `json:"message"`
		} `json:"error"`
	}
	msg := "anthropic stream error"
	status := http.StatusBadGateway
	if err := json.Unmarshal([]byte(data), &payload); err == nil {
		if payload.Error.Message != "" {
			msg = truncateErrMsg(payload.Error.Message)
		}
		switch payload.Error.Type {
		case "overloaded_error":
			status = statusOverloaded
		case "rate_limit_error":
			status = http.StatusTooManyRequests
		}
	}
	return &provider.ProviderError{
		ProviderName:   "anthropic",
		StatusCode:     status,
		ProviderErrMsg: msg,
		ProviderBody:   []byte(data),
	}
}

func (st *streamState) writeChunk(chunk openAIStreamChunk) error {
	raw, err := json.Marshal(chunk)
	if err != nil {
		return err
	}
	return st.writeRaw("data: " + string(raw) + "\n\n")
}

func (st *streamState) writeRaw(s string) error {
	_, err := io.WriteString(st.pw, s)
	if err == nil {
		return nil
	}
	// Consumer closed the pipe (client disconnect / Body.Close): stop quietly.
	if errors.Is(err, io.ErrClosedPipe) {
		return errPipeClosed
	}
	return err
}

func truncateErrMsg(msg string) string {
	const max = 512
	if len(msg) <= max {
		return msg
	}
	return msg[:max]
}

type openAIStreamChunk struct {
	ID      string               `json:"id"`
	Object  string               `json:"object"`
	Created int64                `json:"created"`
	Model   string               `json:"model"`
	Choices []openAIStreamChoice `json:"choices"`
}

type openAIStreamChoice struct {
	Index        int               `json:"index"`
	Delta        openAIStreamDelta `json:"delta"`
	FinishReason *string           `json:"finish_reason"`
}

type openAIStreamDelta struct {
	Role    string `json:"role,omitempty"`
	Content string `json:"content,omitempty"`
}

func strPtr(s string) *string { return &s }
