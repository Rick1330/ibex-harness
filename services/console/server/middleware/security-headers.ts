export default defineEventHandler((event) => {
  setResponseHeader(event, "X-Content-Type-Options", "nosniff")
  setResponseHeader(event, "X-Frame-Options", "DENY")
  setResponseHeader(event, "Referrer-Policy", "no-referrer")
  setResponseHeader(event, "Permissions-Policy", "camera=(), microphone=(), geolocation=()")

  const path = getRequestURL(event).pathname
  if (!path.startsWith("/_nuxt/")) {
    setResponseHeader(event, "Cache-Control", "private, no-store")
    setResponseHeader(event, "Vary", "Cookie")
  }
})
