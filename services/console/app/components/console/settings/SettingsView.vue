<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted } from "vue"
import {
  Bot,
  Building2,
  Check,
  Database,
  Globe2,
  Lock,
  Palette,
  Pencil,
  ScanSearch,
  Server,
  ShieldCheck,
  TriangleAlert,
} from "@lucide/vue"
import ConsolePageHeader from "@/components/console/ConsolePageHeader.vue"
import GovernLockedAction from "@/components/console/govern/primitives/GovernLockedAction.vue"
import GovernTabBar from "@/components/console/govern/primitives/GovernTabBar.vue"
import SettingsGroup from "@/components/console/SettingsGroup.vue"
import SettingsRow from "@/components/console/settings/SettingsRow.vue"
import {
  SETTINGS_AGENT_DEFAULTS,
  SETTINGS_AUTHORITY,
  SETTINGS_CATEGORIES,
  SETTINGS_DANGER,
  SETTINGS_ENVIRONMENTS,
  SETTINGS_EVIDENCE,
  SETTINGS_ORGANIZATION,
  SETTINGS_ORIGINS,
  SETTINGS_PRIVACY,
  SETTINGS_RETENTION,
  firstSectionForCategory,
  nextSettingsCategory,
  settingsCategoryFor,
  type SettingsCategory,
  type SettingsSection,
} from "@/lib/settings-preview"

const props = defineProps<{ section: SettingsSection }>()
const emit = defineEmits<{ update: [section: SettingsSection] }>()

const colorMode = useColorMode()

const SECTIONS: Record<SettingsSection, { label: string; icon: unknown; definition: string }> = {
  organization: {
    label: "Organization",
    icon: Building2,
    definition: "Identity, region, and plan boundary. Every value names its owner and the audit event that recorded it.",
  },
  environments: {
    label: "Environments",
    icon: Globe2,
    definition: "Labels that scope runs and policies. They are configuration, not free-form tags.",
  },
  "agent-defaults": {
    label: "Agent defaults",
    icon: Bot,
    definition: "The model, context, memory, and drift defaults a new agent inherits unless it declares its own.",
  },
  "data-mode": {
    label: "Data mode",
    icon: Database,
    definition: "What this console may claim right now and which sources are actually connected.",
  },
  "read-only": {
    label: "Read-only",
    icon: Lock,
    definition: "The enforced write boundary. No mutation path exists in this console.",
  },
  retention: {
    label: "Retention",
    icon: Database,
    definition: "Separate windows for separate evidence. Analytics TTL is not canonical evidence retention.",
  },
  privacy: {
    label: "Privacy and redaction",
    icon: ScanSearch,
    definition: "What is captured, when personal data is detected, and what happens before it is stored or returned.",
  },
  "evidence-relay": {
    label: "Evidence and relay",
    icon: ShieldCheck,
    definition: "Canonical authority versus derived projection. A projection never certifies billing or deletion.",
  },
  display: {
    label: "Display",
    icon: Palette,
    definition: "Density and time presentation. These preferences never change tenant scope.",
  },
  "api-origin": {
    label: "API and origin health",
    icon: Server,
    definition: "The delivery path behind these settings. Reachability is not evidence certification.",
  },
  "danger-zone": {
    label: "Danger zone",
    icon: TriangleAlert,
    definition: "High-impact actions stay unavailable without confirmation, approval, rollback, and audit.",
  },
}

const category = computed<SettingsCategory>(() => settingsCategoryFor(props.section))
const activeSections = computed<SettingsSection[]>(() => {
  const entry = SETTINGS_CATEGORIES.find((item) => item.id === category.value)
  return entry ? [...(entry.sections as readonly SettingsSection[])] : ["organization"]
})

const tabs = SETTINGS_CATEGORIES.map((entry) => ({ id: entry.id, label: entry.label }))

type Row = {
  label: string
  hint?: string
  value?: string
  owner?: string
  changedAt?: string
  audit?: string
  enabled?: boolean
  tone?: "default" | "ok" | "warn" | "crit" | "neutral"
  actionLabel?: string
}

function rowsFor(section: SettingsSection): Row[] {
  switch (section) {
    case "organization":
      return SETTINGS_ORGANIZATION
    case "agent-defaults":
      return SETTINGS_AGENT_DEFAULTS
    case "retention":
      return SETTINGS_RETENTION
    case "privacy":
      return SETTINGS_PRIVACY
    case "environments":
      return SETTINGS_ENVIRONMENTS.map((environment) => ({
        label: environment.name,
        hint: environment.traffic,
        value: environment.state,
        owner: environment.owner,
        changedAt: environment.changedAt,
        tone: environment.state === "active" ? "ok" : "neutral",
      }))
    case "data-mode":
    case "read-only":
      return SETTINGS_AUTHORITY.map((item) => ({
        label: item.label,
        hint: item.detail,
        value: item.value,
        tone: item.tone,
      }))
    case "evidence-relay":
      return SETTINGS_EVIDENCE.map((item) => ({
        label: item.label,
        hint: item.detail,
        value: item.value,
        owner: item.owner,
        changedAt: item.changedAt,
      }))
    case "api-origin":
      return SETTINGS_ORIGINS.map((origin) => ({
        label: origin.name,
        hint: `${origin.endpoint} · ${origin.detail}`,
        value: origin.state,
        tone: origin.state === "degraded" ? "warn" : "ok",
      }))
    case "danger-zone":
      return SETTINGS_DANGER.map((item) => ({
        label: item.label,
        hint: item.reason,
        actionLabel: item.actionLabel,
      }))
    default:
      return []
  }
}

const aboutNotes = [
  {
    lead: "Configuration is evidence.",
    body: "Every changed value names its owner, the time it changed, and the audit event that recorded it. A value without that trail is not treated as authoritative.",
  },
  {
    lead: "Read-only is enforced, not decorative.",
    body: "There is no mutation path in this console. Edit, rotate, and delete controls are present so the missing contract is visible, but they cannot fire.",
  },
  {
    lead: "Display never grants authority.",
    body: "Theme, density, number format, and timezone are presentation preferences. They never change tenant scope or expand what an operator may read.",
  },
]

function selectCategory(next: string): void {
  const entry = SETTINGS_CATEGORIES.find((item) => item.id === next)
  const first = entry?.sections[0] as SettingsSection | undefined
  if (first && first !== props.section) emit("update", first)
}

function onKeydown(event: KeyboardEvent): void {
  const target = event.target as HTMLElement | null
  const inField =
    target instanceof HTMLElement &&
    (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.tagName === "SELECT" || target.isContentEditable)
  if (inField || event.metaKey || event.ctrlKey || event.altKey) return
  if (event.key === "[") {
    event.preventDefault()
    emit("update", firstSectionForCategory(nextSettingsCategory(category.value, -1)))
  } else if (event.key === "]") {
    event.preventDefault()
    emit("update", firstSectionForCategory(nextSettingsCategory(category.value, 1)))
  }
}

onMounted(() => window.addEventListener("keydown", onKeydown))
onBeforeUnmount(() => window.removeEventListener("keydown", onKeydown))

function setTheme(theme: "light" | "dark" | "system"): void {
  colorMode.preference = theme
}
</script>

<template>
  <div class="mx-auto flex w-full max-w-[72rem] min-w-0 flex-1 flex-col gap-5 pb-8">
    <ConsolePageHeader
      title="Settings"
      definition="How this organization is configured, who owns each value, and which changes are blocked without a write contract."
      state="illustrative"
      verdict="Every value on this page is a recorded preview fixture. The settings, identity, and audit contracts are not connected, so no configuration here is live organization state."
      contract="operator.settings.organization.v1 [NEEDS-BACKEND]"
      scope="org_demo_42 · organization"
      range="Current configuration · fixture clock"
      coverage="0% live · illustrative only"
      :notes="aboutNotes"
    />

    <GovernTabBar
      :tabs="tabs"
      :model-value="category"
      aria-label="Settings categories"
      @update:model-value="selectCategory"
    />

    <div class="flex flex-col gap-7">
      <SettingsGroup
        v-for="entry in activeSections"
        :id="`settings-${entry}`"
        :key="entry"
        :title="SECTIONS[entry].label"
        :definition="SECTIONS[entry].definition"
      >
        <template v-if="entry !== 'display' && entry !== 'danger-zone'" #actions>
          <GovernLockedAction label="Edit" :icon="Pencil" size="sm" />
        </template>

        <div v-if="entry === 'display'" class="divide-y divide-line-subtle">
          <div class="flex flex-wrap items-start justify-between gap-4 px-4 py-3.5">
            <div class="min-w-0 flex-1">
              <p class="text-xs font-medium text-fg-1">Theme</p>
              <p class="mt-0.5 text-[0.6875rem] leading-4 text-fg-3">A local presentation preference. It never changes tenant scope.</p>
            </div>
            <div class="flex h-8 items-center gap-1 rounded-md border border-line-subtle bg-raised p-0.5">
              <button
                v-for="option in ([
                  { id: 'light', label: 'Light' },
                  { id: 'dark', label: 'Dark' },
                  { id: 'system', label: 'System' },
                ] as const)"
                :key="option.id"
                type="button"
                class="flex h-7 items-center justify-center rounded px-2.5 text-xs transition-colors"
                :class="colorMode.preference === option.id ? 'bg-surface text-fg-1' : 'text-fg-3 hover:text-fg-1'"
                :aria-pressed="colorMode.preference === option.id"
                @click="setTheme(option.id)"
              >
                <Check v-if="colorMode.preference === option.id" :size="12" :stroke-width="2" class="mr-1" aria-hidden="true" />
                {{ option.label }}
              </button>
            </div>
          </div>
          <SettingsRow label="Density" hint="Compact is the console default." value="Compact" />
          <SettingsRow label="Time format" hint="Absolute timestamps use 24-hour UTC." value="24-hour UTC" />
          <SettingsRow label="Number format" hint="Used for counts and money outside mono cells." value="en-US" />
        </div>

        <div v-else class="divide-y divide-line-subtle">
          <SettingsRow
            v-for="row in rowsFor(entry)"
            :key="row.label"
            :label="row.label"
            :hint="row.hint"
            :value="row.value"
            :owner="row.owner"
            :changed-at="row.changedAt"
            :audit="row.audit"
            :enabled="row.enabled"
            :tone="row.tone"
            :show-lock="entry !== 'danger-zone'"
          >
            <GovernLockedAction
              v-if="row.actionLabel"
              :label="row.actionLabel"
              :icon="Lock"
              variant="destructive"
              size="sm"
            />
          </SettingsRow>
          <div
            v-if="entry === 'danger-zone'"
            class="flex items-start gap-2 border-t border-crit/25 bg-crit-tint/40 px-4 py-2.5 text-[0.6875rem] leading-4 text-fg-3"
          >
            <TriangleAlert :size="12" :stroke-width="1.8" class="mt-0.5 shrink-0 text-crit" aria-hidden="true" />
            No destructive control is enabled without confirmation, approval, rollback, and audit.
          </div>
        </div>
      </SettingsGroup>
    </div>
  </div>
</template>
