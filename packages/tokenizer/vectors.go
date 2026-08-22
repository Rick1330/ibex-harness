package tokenizer

// vectorHelloWorld is a shared ground-truth probe string for OpenAI encodings.
const vectorHelloWorld = "Hello world"

// VectorHelloWorld exposes the shared probe string for cross-package tests.
func VectorHelloWorld() string { return vectorHelloWorld }
