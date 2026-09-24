"use client"

import { AuthProvider } from "@/components/auth/auth-provider"
import { AuthShell } from "@/components/auth/auth-shell"
import { TotpEnrollmentForm } from "@/components/auth/totp-enrollment-form"

export default function EnrollTotpPage() {
  return (
    <AuthProvider>
      <AuthShell
        footer={<span>BeginTotpEnrollment → ConfirmTotpEnrollment</span>}
      >
        <TotpEnrollmentForm />
      </AuthShell>
    </AuthProvider>
  )
}
