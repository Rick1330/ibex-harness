"use client"

import { Suspense } from "react"

import { AuthProvider } from "@/components/auth/auth-provider"
import { AuthShell } from "@/components/auth/auth-shell"
import { LoginForm } from "@/components/auth/login-form"

export default function LoginPage() {
  return (
    <AuthProvider>
      <AuthShell
        footer={
          <span>RS256 sessions · refresh rotation · CSRF double-submit</span>
        }
      >
        <Suspense fallback={null}>
          <LoginForm />
        </Suspense>
      </AuthShell>
    </AuthProvider>
  )
}
