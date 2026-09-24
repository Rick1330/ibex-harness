"use client"

import { AuthProvider } from "@/components/auth/auth-provider"
import { AuthShell } from "@/components/auth/auth-shell"
import { SignupForm } from "@/components/auth/signup-form"

export default function SignupPage() {
  return (
    <AuthProvider>
      <AuthShell
        footer={
          <span>
            Creates an org-bound operator session · not OIDC / Keycloak
          </span>
        }
      >
        <SignupForm />
      </AuthShell>
    </AuthProvider>
  )
}
