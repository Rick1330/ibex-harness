export type OperatorEventStreamState = "connecting" | "connected" | "unavailable"

export function useOperatorEventStream(enabled: () => boolean) {
  const state = ref<OperatorEventStreamState>(enabled() ? "connecting" : "unavailable")
  const connectedAt = ref<number | null>(null)
  const lastAttemptAt = ref<number | null>(null)
  const attempts = ref(0)
  const endpoint = "/api/operator/events/stream"
  let source: EventSource | null = null

  function connect(): void {
    if (source || !enabled()) return
    state.value = "connecting"
    lastAttemptAt.value = Date.now()
    attempts.value += 1
    source = new EventSource(endpoint)
    source.onopen = () => {
      state.value = "connected"
      connectedAt.value = Date.now()
    }
    source.onerror = () => {
      if (source?.readyState === EventSource.CLOSED) {
        state.value = "unavailable"
        connectedAt.value = null
      } else {
        state.value = "connecting"
      }
    }
  }

  function disconnect(): void {
    source?.close()
    source = null
    connectedAt.value = null
  }

  function reconnect(): void {
    disconnect()
    state.value = "connecting"
    connect()
  }

  onMounted(connect)
  onBeforeUnmount(disconnect)

  watch(enabled, (isEnabled) => {
    if (isEnabled) {
      connect()
    } else {
      disconnect()
      state.value = "unavailable"
    }
  })

  return { state, connectedAt, lastAttemptAt, attempts, endpoint, connect, reconnect, disconnect }
}
