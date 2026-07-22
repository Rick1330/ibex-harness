package http

import "net/http"

// flushIfSupported flushes w when the underlying ResponseWriter supports http.Flusher.
func flushIfSupported(w http.ResponseWriter) {
	if f, ok := w.(http.Flusher); ok {
		f.Flush()
	}
}
