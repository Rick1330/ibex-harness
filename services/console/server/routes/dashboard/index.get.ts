import { getRequestURL, sendRedirect } from "h3"

export default defineEventHandler((event) => {
  return sendRedirect(event, `/${getRequestURL(event).search}`, 308)
})
