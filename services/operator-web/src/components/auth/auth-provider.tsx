"use client"

import * as React from "react"
import { useRouter } from "next/navigation"

import {
  loadSession,
  logout as apiLogout,
  refreshOperatorSession,
  setAuthDemoFlags,
} from "@/lib/auth/api"
import type {
  AuthShellBanner,
  OperatorSession,
  SessionCookies,
  StepUpToken,
} from "@/lib/auth/types"

type AuthContextValue = {
  ready: boolean
  session: OperatorSession | null
  cookies: SessionCookies | null
  banner: AuthShellBanner
  setBanner: (b: AuthShellBanner) => void
  setSession: (session: OperatorSession, cookies: SessionCookies) => void
  logout: (reason?: "security" | "manual") => void
  tryRefresh: () => Promise<boolean>
  pendingStepUp: StepUpToken | null
  setPendingStepUp: (t: StepUpToken | null) => void
  /** Open step-up; onSuccess receives the one-shot token then clear. */
  openStepUp: (onSuccess: (token: string) => void) => void
  closeStepUp: () => void
  stepUpOpen: boolean
  /** Called by StepUpModal after CreateStepUpToken succeeds. */
  resolveStepUp: (token: string) => void
}

const AuthContext = React.createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const router = useRouter()
  const [ready, setReady] = React.useState(false)
  const [session, setSessionState] = React.useState<OperatorSession | null>(
    null,
  )
  const [cookies, setCookies] = React.useState<SessionCookies | null>(null)
  const [banner, setBanner] = React.useState<AuthShellBanner>(null)
  const [pendingStepUp, setPendingStepUp] = React.useState<StepUpToken | null>(
    null,
  )
  const [stepUpOpen, setStepUpOpen] = React.useState(false)
  const successRef = React.useRef<((token: string) => void) | null>(null)

  React.useEffect(() => {
    const stored = loadSession()
    if (stored) {
      setSessionState(stored.session)
      setCookies(stored.cookies)
    }
    setReady(true)
    ;(
      window as unknown as { __ibexSetAuthFlags?: typeof setAuthDemoFlags }
    ).__ibexSetAuthFlags = setAuthDemoFlags
  }, [])

  const setSession = React.useCallback(
    (s: OperatorSession, c: SessionCookies) => {
      setSessionState(s)
      setCookies(c)
    },
    [],
  )

  const logout = React.useCallback(
    (reason: "security" | "manual" = "manual") => {
      apiLogout()
      setSessionState(null)
      setCookies(null)
      setPendingStepUp(null)
      router.replace(
        reason === "security" ? "/login?reason=security" : "/login",
      )
    },
    [router],
  )

  const tryRefresh = React.useCallback(async () => {
    if (!cookies) return false
    try {
      const result = await refreshOperatorSession(cookies.ibex_csrf)
      setSessionState(result.session)
      setCookies(result.cookies)
      setBanner(null)
      return true
    } catch (e) {
      const code =
        e && typeof e === "object" && "code" in e
          ? String((e as { code: string }).code)
          : ""
      if (code === "auth_unavailable") {
        setBanner({
          kind: "degraded",
          message:
            "Can't refresh session right now — Auth unreachable. Retrying in background.",
        })
        return false
      }
      logout("security")
      return false
    }
  }, [cookies, logout])

  const openStepUp = React.useCallback((onSuccess: (token: string) => void) => {
    successRef.current = onSuccess
    setStepUpOpen(true)
  }, [])

  const closeStepUp = React.useCallback(() => {
    setStepUpOpen(false)
    successRef.current = null
  }, [])

  const resolveStepUp = React.useCallback((token: string) => {
    const cb = successRef.current
    successRef.current = null
    setStepUpOpen(false)
    setPendingStepUp(null)
    cb?.(token)
  }, [])

  const value: AuthContextValue = {
    ready,
    session,
    cookies,
    banner,
    setBanner,
    setSession,
    logout,
    tryRefresh,
    pendingStepUp,
    setPendingStepUp,
    openStepUp,
    closeStepUp,
    stepUpOpen,
    resolveStepUp,
  }

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const ctx = React.useContext(AuthContext)
  if (!ctx) throw new Error("useAuth must be used within AuthProvider")
  return ctx
}

export function useAuthOptional() {
  return React.useContext(AuthContext)
}
