"use client"

import * as React from "react"
import { Suspense } from "react"
import { toast } from "sonner"

import { useAuth } from "@/components/auth/auth-provider"
import { TierQuotaCard } from "@/components/org/tier-quota-card"
import { listTable } from "@/components/explore/table-styles"
import { ListPageHeader } from "@/components/list/filter-bar"
import { StatusDot } from "@/components/list/status-dot"
import { AuditPanel, useAuditTabSync } from "@/components/settings/audit-panel"
import { ProvidersPanel } from "@/components/settings/providers-panel"
import { TokensPanel } from "@/components/settings/tokens-panel"
import { WebhooksPanel } from "@/components/settings/webhooks-panel"
import {
  DashboardShell,
  pagePad,
  panelClass,
} from "@/components/sessions/dashboard-shell"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { SETTINGS_V2, evaluateGate, gateMessage } from "@/lib/settings/fixtures"
import type {
  GateBlock,
  OrgSettingsJsonb,
  SettingsPageV2,
} from "@/lib/settings/types"
import { cn } from "@/lib/utils"

function SettingsWorkbench() {
  const { openStepUp } = useAuth()
  const [data, setData] = React.useState(SETTINGS_V2)
  const [settings, setSettings] = React.useState(data.settings)
  const [cidr, setCidr] = React.useState("")
  const [deleteStep, setDeleteStep] = React.useState(0)
  const { tab, setTab } = useAuditTabSync("org")

  const caller = data.caller
  const ssoAllowed = data.org.tier_limits.sso_enabled
  const activeHolds = data.legal_holds.filter((h) => h.active).length

  /** Step-up gated actions — one-shot token via shell modal, then discard. */
  const requireStepUp = (action: () => void) => {
    openStepUp(() => action())
  }

  return (
    <div className={pagePad}>
      <ListPageHeader
        title="Settings / Org"
        description="organizations.settings · ADR-0009 bitmap · 4.P.3 privacy (done)"
      />

      {activeHolds > 0 ? (
        <div className="rounded-md border border-destructive/40 bg-destructive/5 px-3 py-2.5 text-[12px]">
          <span className="font-medium">
            Deletion is blocked org-wide while {activeHolds} legal hold(s) are
            active.
          </span>
        </div>
      ) : null}

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList className="mb-3 h-auto flex-wrap">
          <TabsTrigger value="org">Org profile</TabsTrigger>
          <TabsTrigger value="members">Members</TabsTrigger>
          <TabsTrigger value="security">Security</TabsTrigger>
          <TabsTrigger value="tokens">API Tokens</TabsTrigger>
          <TabsTrigger value="providers">Providers</TabsTrigger>
          <TabsTrigger value="webhooks">Webhooks</TabsTrigger>
          <TabsTrigger value="privacy">Privacy & legal hold</TabsTrigger>
          <TabsTrigger value="audit">Audit log</TabsTrigger>
        </TabsList>

        <TabsContent value="org" className="space-y-4">
          <Card className={panelClass}>
            <CardContent className="px-4 py-4">
              <TierQuotaCard org={data.org} showComparison={false} />
            </CardContent>
          </Card>
          <OrgSettingsPanel
            settings={settings}
            setSettings={setSettings}
            cidr={cidr}
            setCidr={setCidr}
            ssoAllowed={ssoAllowed}
            tierRetention={data.org.tier_limits.audit_log_retention_days}
            driftAllowed={data.org.tier_limits.drift_detection_enabled}
            federationAllowed={data.org.tier_limits.federation_enabled}
            embedding={data.embedding}
            saveBlock={evaluateGate(caller, { bit: "OrgSettingsWrite" })}
            onSave={() =>
              toast.success("Settings saved", {
                description: "organizations.settings JSONB updated",
              })
            }
          />
        </TabsContent>

        <TabsContent value="members" className="space-y-4">
          <MembersTable
            members={data.members}
            onClearLock={(id) => {
              setData((prev) => ({
                ...prev,
                members: prev.members.map((m) =>
                  m.user_id === id
                    ? { ...m, failed_login_attempts: 0, locked_until: null }
                    : m,
                ),
              }))
              toast.success("Lockout cleared")
            }}
          />
        </TabsContent>

        <TabsContent value="security" className="space-y-4">
          <SecurityTab
            data={data}
            ssoAllowed={ssoAllowed}
            onRevokeSession={(id) => {
              setData((prev) => ({
                ...prev,
                sessions: prev.sessions.filter((s) => s.session_id !== id),
              }))
              toast.success("Session revoked", {
                description: "Audit: token.revoke / session-kill",
              })
            }}
          />
        </TabsContent>

        <TabsContent value="tokens" className="space-y-4">
          <TokensPanel
            data={data}
            onChange={(tokens) => setData((prev) => ({ ...prev, tokens }))}
          />
        </TabsContent>

        <TabsContent value="providers" className="space-y-4">
          <ProvidersPanel
            data={data}
            onChange={(providers) =>
              setData((prev) => ({ ...prev, providers }))
            }
          />
        </TabsContent>

        <TabsContent value="webhooks" className="space-y-4">
          <WebhooksPanel
            data={data}
            onChange={(webhooks) => setData((prev) => ({ ...prev, webhooks }))}
          />
        </TabsContent>

        <TabsContent value="privacy" className="space-y-4">
          <PrivacyTab
            data={data}
            deleteStep={deleteStep}
            onPlaceHold={() => {
              requireStepUp(() => {
                const block = evaluateGate(caller, {
                  bit: "LegalHoldManage",
                  requiresStepUp: true,
                })
                if (block && block.kind === "permission") {
                  toast.error(gateMessage(block))
                  return
                }
                setData((prev) => ({
                  ...prev,
                  legal_holds: [
                    {
                      hold_id: `lh_${Date.now()}`,
                      reason: "Manual hold",
                      created_at: new Date().toISOString(),
                      created_by: "operator@example.invalid",
                      active: true,
                    },
                    ...prev.legal_holds,
                  ],
                }))
                toast.success("Legal hold placed")
              })
            }}
            onClearHold={(id) => {
              requireStepUp(() => {
                setData((prev) => ({
                  ...prev,
                  legal_holds: prev.legal_holds.map((h) =>
                    h.hold_id === id ? { ...h, active: false } : h,
                  ),
                }))
                toast.success("Hold cleared")
              })
            }}
            onStartDelete={() => {
              if (activeHolds > 0) {
                toast.error("Blocked by active legal hold(s)")
                return
              }
              requireStepUp(() => setDeleteStep(1))
            }}
            onAdvanceDelete={() => setDeleteStep((s) => Math.min(3, s + 1))}
          />
        </TabsContent>

        <TabsContent value="audit" className="space-y-4">
          <AuditPanel
            entries={data.audit}
            caller={caller}
            retentionDays={data.org.tier_limits.audit_log_retention_days}
            tier={data.org.tier}
            onExportLogged={(entry) =>
              setData((prev) => ({
                ...prev,
                audit: [entry, ...prev.audit],
              }))
            }
          />
        </TabsContent>
      </Tabs>
    </div>
  )
}

function OrgSettingsPanel({
  settings,
  setSettings,
  cidr,
  setCidr,
  ssoAllowed,
  tierRetention,
  driftAllowed,
  federationAllowed,
  embedding,
  saveBlock,
  onSave,
}: {
  settings: OrgSettingsJsonb
  setSettings: React.Dispatch<React.SetStateAction<OrgSettingsJsonb>>
  cidr: string
  setCidr: (v: string) => void
  ssoAllowed: boolean
  tierRetention: number
  driftAllowed: boolean
  federationAllowed: boolean
  embedding: SettingsPageV2["embedding"]
  saveBlock: GateBlock
  onSave: () => void
}) {
  const addCidr = () => {
    const v = cidr.trim()
    if (!/^\d{1,3}(\.\d{1,3}){3}\/\d{1,2}$/.test(v)) {
      toast.error("Invalid CIDR")
      return
    }
    setSettings((s) => ({
      ...s,
      ip_allowlist: [...s.ip_allowlist, v],
    }))
    setCidr("")
  }

  return (
    <Card className={panelClass}>
      <CardHeader className="border-b border-border/60 px-4 py-3">
        <CardTitle className="text-[13px] font-medium">
          organizations.settings
        </CardTitle>
        <p className="text-[12px] text-muted-foreground">
          Real toggles — not free-text JSON editing
        </p>
      </CardHeader>
      <CardContent className="space-y-4 px-4 py-3 text-[12px]">
        <ToggleRow
          label="mfa_required"
          checked={settings.mfa_required}
          onChange={(v) => setSettings((s) => ({ ...s, mfa_required: v }))}
        />
        <div>
          <div className="font-medium">ip_allowlist</div>
          <p className="text-muted-foreground">
            Syntax-validated CIDRs. Enforcement of allowlisting at the edge is
            not claimed here beyond validation.
          </p>
          <div className="mt-1 flex flex-wrap gap-1">
            {settings.ip_allowlist.map((c) => (
              <button
                key={c}
                type="button"
                className="rounded border border-border px-1.5 py-0.5 font-mono text-[11px]"
                onClick={() =>
                  setSettings((s) => ({
                    ...s,
                    ip_allowlist: s.ip_allowlist.filter((x) => x !== c),
                  }))
                }
              >
                {c} ×
              </button>
            ))}
          </div>
          <div className="mt-2 flex gap-2">
            <Input
              value={cidr}
              onChange={(e) => setCidr(e.target.value)}
              placeholder="203.0.113.0/24"
              className="h-7 w-44 font-mono text-[12px]"
            />
            <Button
              size="sm"
              variant="outline"
              className="h-7"
              onClick={addCidr}
            >
              Add
            </Button>
          </div>
        </div>

        <div>
          <div className="font-medium">sso_domain</div>
          {!ssoAllowed ? (
            <p className="mt-0.5 text-muted-foreground">
              SSO disabled on this tier (sso_enabled=false) — field visible with
              upgrade prompt, not hidden.
            </p>
          ) : null}
          <Input
            value={settings.sso_domain ?? ""}
            disabled={!ssoAllowed}
            onChange={(e) =>
              setSettings((s) => ({
                ...s,
                sso_domain: e.target.value || null,
              }))
            }
            placeholder="acme.com"
            className="mt-1 h-7 max-w-xs font-mono text-[12px]"
            title={!ssoAllowed ? "Upgrade to enterprise for SSO" : undefined}
          />
        </div>

        <div>
          <div className="font-medium">data_retention_days</div>
          <div className="mt-0.5 flex items-center gap-2">
            <Input
              type="number"
              value={settings.data_retention_days}
              onChange={(e) =>
                setSettings((s) => ({
                  ...s,
                  data_retention_days: Number(e.target.value),
                }))
              }
              className="h-7 w-24 font-mono"
            />
            <span className="text-muted-foreground">
              tier audit_log_retention_days = {tierRetention}
            </span>
          </div>
        </div>

        <ToggleRow
          label="memory_extraction_enabled"
          checked={settings.memory_extraction_enabled}
          onChange={(v) =>
            setSettings((s) => ({ ...s, memory_extraction_enabled: v }))
          }
        />
        <ToggleRow
          label="drift_detection_enabled"
          checked={settings.drift_detection_enabled}
          disabled={!driftAllowed}
          disabledReason={
            !driftAllowed ? "Tier does not include drift_detection" : undefined
          }
          onChange={(v) =>
            setSettings((s) => ({ ...s, drift_detection_enabled: v }))
          }
        />
        <ToggleRow
          label="federation_enabled"
          checked={settings.federation_enabled}
          disabled={!federationAllowed}
          disabledReason={
            !federationAllowed ? "Tier does not include federation" : undefined
          }
          onChange={(v) =>
            setSettings((s) => ({ ...s, federation_enabled: v }))
          }
        />

        <div className="rounded-md border border-border/70 px-3 py-2">
          <div className="font-medium">Embedding profile (read-only)</div>
          <p className="text-muted-foreground">
            Deployment profile — contact support to change.
          </p>
          <div className="mt-1 font-mono text-[12px]">
            {embedding.profile} · dim {embedding.dimension} ·{" "}
            {embedding.model_id}
          </div>
        </div>

        <GatedButton block={saveBlock} label="Save settings" onClick={onSave} />
      </CardContent>
    </Card>
  )
}

function ToggleRow({
  label,
  checked,
  onChange,
  disabled,
  disabledReason,
}: {
  label: string
  checked: boolean
  onChange: (v: boolean) => void
  disabled?: boolean
  disabledReason?: string
}) {
  return (
    <label
      className={cn(
        "flex items-center justify-between gap-3 rounded-md border border-border/60 px-3 py-2",
        disabled && "opacity-60",
      )}
      title={disabledReason}
    >
      <span className="font-mono text-[12px]">{label}</span>
      <input
        type="checkbox"
        checked={checked}
        disabled={disabled}
        onChange={(e) => onChange(e.target.checked)}
      />
    </label>
  )
}

function MembersTable({
  members,
  onClearLock,
}: {
  members: SettingsPageV2["members"]
  onClearLock: (id: string) => void
}) {
  return (
    <Card className={panelClass}>
      <CardHeader className="border-b border-border/60 px-4 py-3">
        <CardTitle className="text-[13px] font-medium">
          Members & roles
        </CardTitle>
      </CardHeader>
      <CardContent className="overflow-x-auto px-0 py-0">
        <table className={listTable.table}>
          <thead>
            <tr className={listTable.headRow}>
              <th className={listTable.head}>Member</th>
              <th className={listTable.head}>role</th>
              <th className={listTable.head}>status</th>
              <th className={listTable.head}>last login</th>
              <th className={listTable.head}>MFA</th>
              <th className={listTable.head}>lockout</th>
              <th className={listTable.head} />
            </tr>
          </thead>
          <tbody>
            {members.map((m) => {
              const sso = m.sso_provider != null
              return (
                <tr key={m.user_id} className={listTable.row}>
                  <td className={listTable.cell}>
                    <div className={listTable.primary}>{m.name}</div>
                    <div className={listTable.meta}>{m.email}</div>
                    {sso ? (
                      <div className="text-[10px] text-muted-foreground">
                        SSO {m.sso_provider} · no password reset
                      </div>
                    ) : null}
                  </td>
                  <td className={cn(listTable.cell, listTable.mono)}>
                    {m.role}
                  </td>
                  <td className={listTable.cell}>
                    <StatusDot
                      tone={
                        m.status === "active"
                          ? "ok"
                          : m.status === "invited"
                            ? "info"
                            : "muted"
                      }
                      label={m.status}
                    />
                  </td>
                  <td
                    className={cn(listTable.cell, listTable.meta, "font-mono")}
                  >
                    {m.last_login_at
                      ? `${m.last_login_at.slice(0, 16)} · ${m.last_login_ip}`
                      : "—"}
                  </td>
                  <td className={listTable.cell}>
                    {m.mfa_enabled ? "on" : "off"}
                  </td>
                  <td className={cn(listTable.cell, "font-mono text-[11px]")}>
                    {m.locked_until
                      ? `${m.failed_login_attempts} fails · until ${m.locked_until.slice(11, 16)}`
                      : m.failed_login_attempts > 0
                        ? `${m.failed_login_attempts} fails`
                        : "—"}
                  </td>
                  <td className={listTable.cell}>
                    <div className="flex gap-1">
                      {m.locked_until ? (
                        <Button
                          size="sm"
                          variant="outline"
                          className="h-7"
                          onClick={() => onClearLock(m.user_id)}
                        >
                          Clear lock
                        </Button>
                      ) : null}
                      {!sso && m.status === "active" ? (
                        <Button size="sm" variant="ghost" className="h-7">
                          Reset password
                        </Button>
                      ) : null}
                    </div>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </CardContent>
    </Card>
  )
}

function SecurityTab({
  data,
  ssoAllowed,
  onRevokeSession,
}: {
  data: SettingsPageV2
  ssoAllowed: boolean
  onRevokeSession: (id: string) => void
}) {
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card className={panelClass}>
        <CardHeader className="border-b border-border/60 px-4 py-3">
          <CardTitle className="text-[13px] font-medium">TOTP</CardTitle>
          <p className="text-[12px] text-muted-foreground">
            Enrollment uses BeginTotpEnrollment → ConfirmTotpEnrollment. No
            backup-codes endpoint in the reviewed TOTP service — not implied.
          </p>
        </CardHeader>
        <CardContent className="space-y-3 px-4 py-3 text-[12px]">
          {data.caller.step_up_active ? (
            <StatusDot
              tone="ok"
              label={`step-up active · expires ${data.caller.step_up_expires_at?.slice(11, 16)}Z`}
            />
          ) : (
            <StatusDot tone="warn" label="no step-up session" />
          )}
          <p className="rounded-md border border-border/60 px-3 py-2 text-muted-foreground">
            AuthService enrollment is deferred; no credential or enrollment
            action is available in this shell.
          </p>
          <p className="text-muted-foreground">
            High-impact actions (promote, revoke, legal hold) open the
            in-context step-up modal — not a full-page redirect.
          </p>
        </CardContent>
      </Card>

      <Card className={panelClass}>
        <CardHeader className="border-b border-border/60 px-4 py-3">
          <CardTitle className="text-[13px] font-medium">
            Enterprise SSO
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-2 px-4 py-3 text-[12px]">
          {!ssoAllowed ? (
            <p className="text-muted-foreground">
              Disabled — tier_limits.sso_enabled is false. Upgrade to
              enterprise. OIDC/Keycloak login is out of scope for ADR-0079 this
              build.
            </p>
          ) : (
            <>
              <div>
                IdP: <span className="font-mono">Okta</span>
              </div>
              <table className={listTable.table}>
                <thead>
                  <tr className={listTable.headRow}>
                    <th className={listTable.head}>Group</th>
                    <th className={listTable.head}>Role</th>
                  </tr>
                </thead>
                <tbody>
                  <tr className={listTable.row}>
                    <td className={listTable.cell}>ibex-admins</td>
                    <td className={listTable.cell}>admin</td>
                  </tr>
                  <tr className={listTable.row}>
                    <td className={listTable.cell}>ibex-ops</td>
                    <td className={listTable.cell}>member</td>
                  </tr>
                </tbody>
              </table>
              <Button size="sm" variant="outline" className="h-7">
                Test SSO connection
              </Button>
            </>
          )}
        </CardContent>
      </Card>

      <Card className={cn(panelClass, "lg:col-span-2")}>
        <CardHeader className="border-b border-border/60 px-4 py-3">
          <CardTitle className="text-[13px] font-medium">
            Active sessions
          </CardTitle>
        </CardHeader>
        <CardContent className="px-0 py-0">
          <table className={listTable.table}>
            <thead>
              <tr className={listTable.headRow}>
                <th className={listTable.head}>Device</th>
                <th className={listTable.head}>IP</th>
                <th className={listTable.head}>last seen</th>
                <th className={listTable.head} />
              </tr>
            </thead>
            <tbody>
              {data.sessions.map((s) => (
                <tr key={s.session_id} className={listTable.row}>
                  <td className={listTable.cell}>
                    {s.device}
                    {s.current ? (
                      <span className="ml-1 text-[10px] text-muted-foreground">
                        current
                      </span>
                    ) : null}
                  </td>
                  <td className={cn(listTable.cell, listTable.mono)}>{s.ip}</td>
                  <td
                    className={cn(listTable.cell, listTable.meta, "font-mono")}
                  >
                    {s.last_seen_at.replace("T", " ").slice(0, 16)}
                  </td>
                  <td className={listTable.cell}>
                    {!s.current ? (
                      <Button
                        size="sm"
                        variant="outline"
                        className="h-7"
                        onClick={() => onRevokeSession(s.session_id)}
                      >
                        Revoke
                      </Button>
                    ) : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </CardContent>
      </Card>
    </div>
  )
}

function PrivacyTab({
  data,
  deleteStep,
  onPlaceHold,
  onClearHold,
  onStartDelete,
  onAdvanceDelete,
}: {
  data: SettingsPageV2
  deleteStep: number
  onPlaceHold: () => void
  onClearHold: (id: string) => void
  onStartDelete: () => void
  onAdvanceDelete: () => void
}) {
  return (
    <div className="space-y-4">
      <Card className={panelClass}>
        <CardHeader className="border-b border-border/60 px-4 py-3">
          <CardTitle className="text-[13px] font-medium">
            Legal holds (4.P.3 done)
          </CardTitle>
          <p className="text-[12px] text-muted-foreground">
            LegalHoldManage bit 49 + step-up
          </p>
        </CardHeader>
        <CardContent className="space-y-3 px-4 py-3">
          <Button size="sm" className="h-7" onClick={onPlaceHold}>
            Place hold
          </Button>
          <table className={listTable.table}>
            <thead>
              <tr className={listTable.headRow}>
                <th className={listTable.head}>hold_id</th>
                <th className={listTable.head}>reason</th>
                <th className={listTable.head}>status</th>
                <th className={listTable.head} />
              </tr>
            </thead>
            <tbody>
              {data.legal_holds.map((h) => (
                <tr key={h.hold_id} className={listTable.row}>
                  <td className={cn(listTable.cell, listTable.mono)}>
                    {h.hold_id}
                  </td>
                  <td className={listTable.cell}>{h.reason}</td>
                  <td className={listTable.cell}>
                    <StatusDot
                      tone={h.active ? "error" : "ok"}
                      label={h.active ? "active" : "cleared"}
                    />
                  </td>
                  <td className={listTable.cell}>
                    {h.active ? (
                      <Button
                        size="sm"
                        variant="outline"
                        className="h-7"
                        onClick={() => onClearHold(h.hold_id)}
                      >
                        Clear
                      </Button>
                    ) : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="rounded-md border border-amber-500/40 bg-amber-500/5 px-3 py-2 text-[12px]">
            Residual (#853): ClickHouse MergeTree TTL can still age rows during
            an active legal hold — documented gap, not a green checkmark.
          </div>
        </CardContent>
      </Card>

      <Card className={panelClass}>
        <CardHeader className="border-b border-border/60 px-4 py-3">
          <CardTitle className="text-[13px] font-medium">
            Capture policies
          </CardTitle>
        </CardHeader>
        <CardContent className="px-4 py-3">
          <ul className="space-y-2 text-[12px]">
            {data.capture_policies.map((p) => (
              <li
                key={p.category}
                className="rounded-md border border-border/70 px-3 py-2"
              >
                <div className="flex justify-between gap-2">
                  <span className="font-mono">{p.category}</span>
                  <span className="font-mono text-foreground">{p.mode}</span>
                </div>
                <p className="mt-0.5 text-muted-foreground">{p.explanation}</p>
              </li>
            ))}
          </ul>
        </CardContent>
      </Card>

      <Card className={panelClass}>
        <CardHeader className="border-b border-border/60 px-4 py-3">
          <CardTitle className="text-[13px] font-medium">
            Org deletion saga
          </CardTitle>
          <p className="text-[12px] text-muted-foreground">
            Per-store receipts (F4-019) — never a single “deleted ✓”. Billing
            history reserved for NON_ERASABLE_STORES (retained post-deletion
            when wired).
          </p>
        </CardHeader>
        <CardContent className="space-y-3 px-4 py-3 text-[12px]">
          {deleteStep === 0 ? (
            <Button
              size="sm"
              variant="destructive"
              className="h-7"
              onClick={onStartDelete}
            >
              Start org deletion…
            </Button>
          ) : null}
          {deleteStep >= 1 ? (
            <div className="space-y-2">
              <p>Step {deleteStep}/3 — confirm scope, step-up, run saga</p>
              <table className={listTable.table}>
                <thead>
                  <tr className={listTable.headRow}>
                    <th className={listTable.head}>store</th>
                    <th className={listTable.head}>receipt</th>
                  </tr>
                </thead>
                <tbody>
                  {data.deletion_demo_receipts.map((r) => (
                    <tr key={r.store} className={listTable.row}>
                      <td className={cn(listTable.cell, listTable.mono)}>
                        {r.store}
                      </td>
                      <td className={listTable.cell}>
                        <StatusDot
                          tone={
                            r.status === "verified"
                              ? "ok"
                              : r.status === "store_unreachable"
                                ? "error"
                                : "muted"
                          }
                          label={r.status}
                        />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {deleteStep < 3 ? (
                <Button size="sm" className="h-7" onClick={onAdvanceDelete}>
                  Advance
                </Button>
              ) : (
                <Button size="sm" variant="outline" className="h-7">
                  Download deletion certificate
                </Button>
              )}
            </div>
          ) : null}
        </CardContent>
      </Card>
    </div>
  )
}

function GatedButton({
  block,
  label,
  onClick,
}: {
  block: GateBlock
  label: string
  onClick: () => void
}) {
  return (
    <Button
      size="sm"
      className="h-7"
      disabled={block != null}
      title={block ? gateMessage(block) : undefined}
      onClick={onClick}
    >
      {label}
      {block ? (
        <span className="ml-1.5 max-w-[160px] truncate text-[10px] opacity-80">
          · {gateMessage(block)}
        </span>
      ) : null}
    </Button>
  )
}

export default function SettingsPage() {
  return (
    <DashboardShell>
      <Suspense
        fallback={
          <div className={pagePad}>
            <p className="text-[13px] text-muted-foreground">
              Loading settings…
            </p>
          </div>
        }
      >
        <SettingsWorkbench />
      </Suspense>
    </DashboardShell>
  )
}
