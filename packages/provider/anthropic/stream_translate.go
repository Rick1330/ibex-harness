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

// streamMeta carries identity fields for one translated SSE stream.
type streamMeta struct {
	Model     string
	RequestID string
}

// sseEvent is one parsed Anthropic SSE event.
type sseEvent struct {
	Type string
	Data string
}

// streamTranslatePipe reads Anthropic named SSE and emits OpenAI chat.completion.chunk SSE.
// Backpressure is natural via io.Pipe: the producer blocks when the consumer is slow.
type streamTranslatePipe struct {
	pr         *io.PipeReader
	src        io.ReadCloser
	meta       streamMeta
	closeSrc   sync.Once
	readerDone chan struct{}
}

func newStreamTranslatePipe(src io.ReadCloser, meta streamMeta) *streamTranslatePipe {
	pr, pw := io.Pipe()
	p := &streamTranslatePipe{
		pr:         pr,
		src:        src,
		meta:       meta,
		readerDone: make(chan struct{}),
	}
	go p.run(pw)
	return p
}

func (p *streamTranslatePipe) Read(b []byte) (int, error) { return p.pr.Read(b) }

func (p *streamTranslatePipe) Close() error {
	_ = p.pr.Close()
	p.closeUpstream()
	<-p.readerDone
	return nil
}

func (p *streamTranslatePipe) closeUpstream() {
	p.closeSrc.Do(func() { _ = p.src.Close() })
}

func (p *streamTranslatePipe) run(pw *io.PipeWriter) {
	defer close(p.readerDone)
	defer p.closeUpstream()
	if err := p.translateInto(pw); err != nil && !errors.Is(err, errPipeClosed) {
		_ = pw.CloseWithError(err)
		return
	}
	_ = pw.Close()
}

func (p *streamTranslatePipe) translateInto(pw *io.PipeWriter) error {
	st := newStreamState(p.meta, pw)
	parser := newSSEParser(p.src)
	for {
		ev, err := parser.nextEvent()
		if err == io.EOF {
			return st.finish()
		}
		if err != nil {
			return err
		}
		if err := st.handle(ev); err != nil {
			return err
		}
	}
}

type sseParser struct {
	scanner   *bufio.Scanner
	eventType string
	dataBuf   strings.Builder
}

func newSSEParser(r io.Reader) *sseParser {
	sc := bufio.NewScanner(r)
	sc.Buffer(make([]byte, 0, 64*1024), maxSSELineBytes)
	return &sseParser{scanner: sc}
}

func (p *sseParser) nextEvent() (sseEvent, error) {
	for p.scanner.Scan() {
		ev, done, err := p.handleScanLine(p.scanner.Text())
		if err != nil || done {
			return ev, err
		}
	}
	return p.finishScan()
}

func (p *sseParser) handleScanLine(line string) (sseEvent, bool, error) {
	if line == "" {
		ev, err := p.flush()
		return ev, true, err
	}
	if strings.HasPrefix(line, ":") {
		return sseEvent{Type: "sse_comment", Data: commentPayload(line)}, true, nil
	}
	return sseEvent{}, false, p.ingestLine(line)
}

func commentPayload(line string) string {
	comment := strings.TrimSpace(strings.TrimPrefix(line, ":"))
	if comment == "" {
		return "keepalive"
	}
	return comment
}

func (p *sseParser) finishScan() (sseEvent, error) {
	if err := p.scanner.Err(); err != nil {
		return sseEvent{}, err
	}
	ev, err := p.flush()
	if err != nil {
		return sseEvent{}, err
	}
	if ev.Type == "" && ev.Data == "" {
		return sseEvent{}, io.EOF
	}
	return ev, nil
}

func (p *sseParser) ingestLine(line string) error {
	switch {
	case strings.HasPrefix(line, "event:"):
		p.eventType = strings.TrimSpace(strings.TrimPrefix(line, "event:"))
		return nil
	case strings.HasPrefix(line, "data:"):
		return p.appendData(strings.TrimSpace(strings.TrimPrefix(line, "data:")))
	default:
		return nil
	}
}

func (p *sseParser) appendData(payload string) error {
	if p.dataBuf.Len()+len(payload)+1 > maxSSEEventBytes {
		return &provider.ProviderError{
			ProviderName:   "anthropic",
			StatusCode:     http.StatusBadGateway,
			ProviderErrMsg: "anthropic SSE event exceeds size limit",
		}
	}
	if p.dataBuf.Len() > 0 {
		p.dataBuf.WriteByte('\n')
	}
	p.dataBuf.WriteString(payload)
	return nil
}

func (p *sseParser) flush() (sseEvent, error) {
	data := strings.TrimSpace(p.dataBuf.String())
	et := strings.TrimSpace(p.eventType)
	p.eventType = ""
	p.dataBuf.Reset()
	if et == "" && data == "" {
		return sseEvent{}, nil
	}
	if et == "" {
		et = "message"
	}
	return sseEvent{Type: et, Data: data}, nil
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

func newStreamState(meta streamMeta, pw *io.PipeWriter) *streamState {
	msgID := meta.RequestID
	if msgID == "" {
		msgID = newFallbackCompletionID()
	}
	return &streamState{msgID: msgID, model: meta.Model, created: time.Now().Unix(), pw: pw}
}

func (st *streamState) finish() error {
	if !st.finishSent {
		if err := st.writeFinish("stop"); err != nil {
			return err
		}
	}
	return st.writeRaw("data: " + doneSentinel + "\n\n")
}

func (st *streamState) handle(ev sseEvent) error {
	switch ev.Type {
	case "error":
		return mapStreamError(ev.Data)
	case "message_start":
		return st.onMessageStart(ev)
	case "content_block_delta":
		return st.onContentDelta(ev)
	case "message_delta":
		return st.onMessageDelta(ev)
	case "ping":
		return st.writeRaw(": ping\n\n")
	case "sse_comment":
		return st.writeRaw(": " + ev.Data + "\n\n")
	case "message_stop", "content_block_start", "content_block_stop":
		return nil
	default:
		return nil
	}
}

func (st *streamState) onMessageStart(ev sseEvent) error {
	var payload struct {
		Message struct {
			ID    string `json:"id"`
			Model string `json:"model"`
		} `json:"message"`
	}
	if err := json.Unmarshal([]byte(ev.Data), &payload); err == nil {
		if payload.Message.ID != "" {
			st.msgID = payload.Message.ID
		}
		if payload.Message.Model != "" {
			st.model = payload.Message.Model
		}
	}
	return st.ensureRole()
}

func (st *streamState) onContentDelta(ev sseEvent) error {
	var payload struct {
		Delta struct {
			Type string `json:"type"`
			Text string `json:"text"`
		} `json:"delta"`
	}
	if err := json.Unmarshal([]byte(ev.Data), &payload); err != nil {
		return nil
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

func (st *streamState) onMessageDelta(ev sseEvent) error {
	var payload struct {
		Delta struct {
			StopReason string `json:"stop_reason"`
		} `json:"delta"`
	}
	if err := json.Unmarshal([]byte(ev.Data), &payload); err != nil || payload.Delta.StopReason == "" {
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
