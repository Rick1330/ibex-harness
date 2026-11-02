<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue"
import {
  ChevronRight,
  Laptop,
  Lock,
  Plus,
  RotateCw,
  ShieldCheck,
  UserPlus,
} from "@lucide/vue"
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet"
import ConsolePageHeader from "@/components/console/ConsolePageHeader.vue"
import GovernFilterBar from "@/components/console/govern/primitives/GovernFilterBar.vue"
import GovernFilterSelect from "@/components/console/govern/primitives/GovernFilterSelect.vue"
import GovernLockedAction from "@/components/console/govern/primitives/GovernLockedAction.vue"
import GovernTabBar from "@/components/console/govern/primitives/GovernTabBar.vue"
import KpiRow from "@/components/console/KpiRow.vue"
import RelativeTime from "@/components/console/RelativeTime.vue"
import {
  ACCESS_CAPABILITIES,
  ACCESS_KEYS,
  ACCESS_MATRIX,
  ACCESS_MEMBERS,
  ACCESS_ROLES,
  ACCESS_SESSIONS,
  accessCounts,
  accessKeyRotationLabel,
  type AccessKey,
  type AccessMember,
  type AccessSession,
} from "@/lib/access-preview"
import type { AccessKeyStateFilter, AccessMemberStateFilter, AccessState, AccessTab } from "@/lib/access-query"
import { formatGovernStamp, GOVERN_NOW } from "@/lib/govern-format"

const props = defineProps<{ state: AccessState }>()
const emit = defineEmits<{ update: [state: AccessState] }>()

const counts = accessCounts()
const searchRef = ref<InstanceType<typeof GovernFilterBar> | null>(null)
const activeIndex = ref(-1)

function update(patch: Partial<AccessState>): void {
  emit("update", { ...props.state, ...patch })
}

function setTab(tab: string): void {
  update({ tab: tab as AccessTab, item: "" })
  activeIndex.value = -1
}

const tabBadges = computed<Record<string, string>>(() => ({
  keys: String(ACCESS_KEYS.length),
  members: String(ACCESS_MEMBERS.length),
  sessions: String(ACCESS_SESSIONS.length),
  roles: String(ACCESS_ROLES.length),
}))

const kpis = computed(() => [
  {
    label: "Active keys",
    value: String(counts.activeKeys),
    helper: `${counts.liveKeys} live · ${counts.testKeys} test`,
  },
  {
    label: "Members",
    value: String(counts.members),
    helper: counts.pendingInvites ? `${counts.pendingInvites} invitation pending` : "No pending invitations",
  },
  {
    label: "Active sessions",
    value: String(counts.activeSessions),
    helper: counts.pendingMfa ? `${counts.pendingMfa} pending MFA` : "Every session verified",
  },
  {
    label: "Rotation overdue",
    value: String(counts.overdueKeys),
    helper: counts.overdueKeys ? "memory:write scope" : "Every key inside its window",
    tone: counts.overdueKeys ? ("warning" as const) : ("default" as const),
  },
])

const keyStateOptions = [
  { value: "all", label: "All keys" },
  { value: "active", label: "Active" },
  { value: "overdue", label: "Due rotation" },
  { value: "revoked", label: "Revoked" },
]

const memberStateOptions = [
  { value: "all", label: "All members" },
  { value: "active", label: "Active" },
  { value: "invited", label: "Invited" },
]

function matches(query: string, ...values: (string | null | undefined)[]): boolean {
  const needle = query.trim().toLowerCase()
  if (!needle) return true
  return values.some((value) => (value ?? "").toLowerCase().includes(needle))
}

const filteredKeys = computed(() =>
  ACCESS_KEYS.filter(
    (key) =>
      (props.state.keyState === "all" || key.state === props.state.keyState) &&
      matches(props.state.q, key.prefix, key.createdBy, key.scopes.join(" "), key.environment),
  ),
)

const filteredMembers = computed(() =>
  ACCESS_MEMBERS.filter(
    (member) =>
      (props.state.memberState === "all" || member.status === props.state.memberState) &&
      matches(props.state.q, member.name, member.email, member.role, member.scope),
  ),
)

const filteredSessions = computed(() =>
  ACCESS_SESSIONS.filter((session) =>
    matches(props.state.q, session.actor, session.device, session.origin, session.mfa, session.state),
  ),
)

const resultCount = computed(() => {
  switch (props.state.tab) {
    case "keys":
      return filteredKeys.value.length
    case "members":
      return filteredMembers.value.length
    case "sessions":
      return filteredSessions.value.length
    default:
      return ACCESS_ROLES.length
  }
})

const resultLabel = computed(() => {
  const noun =
    props.state.tab === "keys"
      ? "key"
      : props.state.tab === "members"
        ? "member"
        : props.state.tab === "sessions"
          ? "session"
          : "role"
  return `${resultCount.value} ${resultCount.value === 1 ? noun : `${noun}s`}`
})

const selectedKey = computed(() => ACCESS_KEYS.find((key) => key.id === props.state.item) ?? null)
const selectedMember = computed(() => ACCESS_MEMBERS.find((member) => member.id === props.state.item) ?? null)
const selectedSession = computed(() => ACCESS_SESSIONS.find((session) => session.id === props.state.item) ?? null)
const drawerOpen = computed(() => Boolean(selectedKey.value || selectedMember.value || selectedSession.value))

function openItem(id: string): void {
  update({ item: id })
}

function closeDrawer(): void {
  update({ item: "" })
}

function rowIds(): string[] {
  if (props.state.tab === "keys") return filteredKeys.value.map((key) => key.id)
  if (props.state.tab === "members") return filteredMembers.value.map((member) => member.id)
  if (props.state.tab === "sessions") return filteredSessions.value.map((session) => session.id)
  return []
}

function moveSelection(delta: number): void {
  const ids = rowIds()
  if (!ids.length) return
  const current = ids.indexOf(props.state.item)
  const next = current < 0 ? (delta > 0 ? 0 : ids.length - 1) : (current + delta + ids.length) % ids.length
  activeIndex.value = next
  const id = ids[next]
  if (id) update({ item: id })
  void nextTick(() => document.querySelector<HTMLElement>(`[data-access-row="${id}"]`)?.focus())
}

function onGlobalKeydown(event: KeyboardEvent): void {
  const target = event.target as HTMLElement | null
  const inField =
    target instanceof HTMLElement &&
    (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.tagName === "SELECT" || target.isContentEditable)

  if (event.key === "/" && !inField && !event.metaKey && !event.ctrlKey) {
    event.preventDefault()
    searchRef.value?.focus()
    return
  }
  if (event.key === "Escape" && drawerOpen.value) {
    event.preventDefault()
    closeDrawer()
    return
  }
  if (inField) return
  if (event.key === "j") {
    event.preventDefault()
    moveSelection(1)
  } else if (event.key === "k") {
    event.preventDefault()
    moveSelection(-1)
  } else if (event.key === "Enter" && activeIndex.value >= 0) {
    event.preventDefault()
    const id = rowIds()[activeIndex.value]
    if (id) openItem(id)
  }
}

onMounted(() => window.addEventListener("keydown", onGlobalKeydown))
onBeforeUnmount(() => window.removeEventListener("keydown", onGlobalKeydown))

watch(
  () => props.state.tab,
  () => {
    activeIndex.value = -1
  },
)

const aboutNotes = [
  {
    lead: "Keys are shown by prefix only.",
    body: "The console never requests or renders secret material. A new secret is shown once at creation and never again.",
  },
  {
    lead: "Rotation is a window, not a suggestion.",
    body: "A key past its rotation window stays usable until it is revoked. The console flags it; it does not rotate or revoke on its own.",
  },
  {
    lead: "Role checks are server-side.",
    body: "The capability matrix describes the intended boundary. It is not a claim that this read-only console can exercise any of those capabilities.",
  },
]

const caveat = computed(() =>
  counts.overdueKeys
    ? `${counts.overdueKeys} live key is past its 30-day rotation window. Rotation and revocation require a privileged write contract.`
    : null,
)

const primaryAction = computed(() => {
  if (props.state.tab === "members") return { label: "Invite member", icon: UserPlus }
  if (props.state.tab === "keys") return { label: "Create key", icon: Plus }
  return null
})

function roleCapabilities(roleIndex: number): string {
  return ACCESS_CAPABILITIES.filter((_, index) => ACCESS_MATRIX[roleIndex]?.[index]).join(" · ")
}

function keyTone(state: AccessKey["state"]): string {
  if (state === "overdue") return "ix-status-pill ix-status-pill-warn"
  if (state === "revoked") return "ix-status-pill"
  return "ix-status-pill ix-status-pill-ok"
}

function memberTone(status: AccessMember["status"]): string {
  return status === "invited" ? "ix-status-pill ix-status-pill-warn" : "ix-status-pill ix-status-pill-ok"
}

function sessionTone(session: AccessSession): string {
  return session.mfa === "verified" ? "ix-status-pill ix-status-pill-ok" : "ix-status-pill ix-status-pill-warn"
}
</script>

<template>
  <div class="mx-auto flex w-full max-w-[100rem] min-w-0 flex-1 flex-col gap-4 overflow-x-hidden pb-2">
    <ConsolePageHeader
      title="Access"
      definition="Keys, sessions, and roles that can reach this organization — and what each one is allowed to do."
      state="illustrative"
      verdict="Preview renders six keys, four members, four sessions, and a static role matrix. The access, identity, and key-management contracts are not connected, so no live credential or session state is claimed."
      contract="operator.access.keys.v1 + members.v1 [NEEDS-BACKEND]"
      scope="org_demo_42 · organization"
      range="Current access state · fixture clock"
      coverage="0% live · illustrative only"
      :caveat="caveat"
      :notes="aboutNotes"
    >
      <template #actions>
        <GovernLockedAction
          v-if="primaryAction"
          :label="primaryAction.label"
          :icon="primaryAction.icon"
          variant="primary"
        />
      </template>
    </ConsolePageHeader>

    <KpiRow :items="kpis" />

    <GovernTabBar
      :tabs="[
        { id: 'keys', label: 'Keys' },
        { id: 'members', label: 'Members' },
        { id: 'sessions', label: 'Sessions' },
        { id: 'roles', label: 'Roles' },
      ]"
      :model-value="state.tab"
      :badges="tabBadges"
      aria-label="Access views"
      @update:model-value="setTab"
    />

    <GovernFilterBar
      v-if="state.tab !== 'roles'"
      ref="searchRef"
      :model-value="state.q"
      :label="`Search ${state.tab}`"
      :placeholder="
        state.tab === 'keys'
          ? 'Search prefix, scope, or creator'
          : state.tab === 'members'
            ? 'Search name, email, role, or scope'
            : 'Search actor, device, origin, or MFA state'
      "
      :result-text="resultLabel"
      :active="Boolean(state.q) || state.keyState !== 'all' || state.memberState !== 'all'"
      @update:model-value="update({ q: $event })"
      @clear="update({ q: '', keyState: 'all', memberState: 'all' })"
      @submit="update({ q: state.q })"
    >
      <template #filters>
        <GovernFilterSelect
          v-if="state.tab === 'keys'"
          label="State"
          :model-value="state.keyState"
          :options="keyStateOptions"
          default-value="all"
          @update:model-value="update({ keyState: $event as AccessKeyStateFilter })"
        />
        <GovernFilterSelect
          v-if="state.tab === 'members'"
          label="Status"
          :model-value="state.memberState"
          :options="memberStateOptions"
          default-value="all"
          @update:model-value="update({ memberState: $event as AccessMemberStateFilter })"
        />
      </template>
    </GovernFilterBar>

    <div v-if="state.tab === 'keys'" class="flex flex-col gap-2 lg:hidden">
      <article
        v-for="key in filteredKeys"
        :key="key.id"
        :aria-label="`Open key ${key.prefix}`"
        tabindex="0"
        class="rounded-lg border border-line-subtle bg-surface p-3 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
        @click="openItem(key.id)"
        @keydown.enter.prevent="openItem(key.id)"
      >
        <div class="flex items-start justify-between gap-2">
          <div class="min-w-0">
            <p class="truncate font-mono text-xs text-fg-1">{{ key.prefix }}</p>
            <p class="mt-0.5 font-mono text-[0.625rem] text-fg-3">created {{ formatGovernStamp(key.createdAt) }}</p>
          </div>
          <span class="shrink-0" :class="keyTone(key.state)">{{ accessKeyRotationLabel(key) }}</span>
        </div>
        <p class="mt-2 truncate font-mono text-[0.6875rem] text-fg-2">{{ key.scopes.join(" · ") }}</p>
        <p class="mt-1 text-[0.6875rem] text-fg-3">{{ key.createdBy }} · last used <RelativeTime :value="key.lastUsedAt" :now="GOVERN_NOW" /></p>
      </article>
      <p v-if="!filteredKeys.length" class="rounded-lg border border-dashed border-line-subtle px-4 py-8 text-center text-xs text-fg-3">
        No keys match this view.
      </p>
    </div>

    <section v-if="state.tab === 'keys'" class="console-panel hidden min-w-0 overflow-hidden lg:block">
      <div class="overflow-x-auto" tabindex="0" aria-label="Access keys table">
        <table class="ix-table min-w-[46rem]">
          <thead>
            <tr>
              <th scope="col">Prefix</th>
              <th scope="col" class="w-64">Scopes</th>
              <th scope="col" class="w-32">Created by</th>
              <th scope="col" class="w-28">Last used</th>
              <th scope="col" class="w-28">Rotation</th>
              <th scope="col" class="w-10"><span class="sr-only">Open</span></th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="key in filteredKeys"
              :key="key.id"
              :data-access-row="key.id"
              :data-selected="state.item === key.id"
              tabindex="0"
              class="cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-accent"
              @click="openItem(key.id)"
              @keydown.enter.prevent="openItem(key.id)"
            >
              <td>
                <div class="min-w-0">
                  <p class="flex items-center gap-2 font-mono text-xs text-fg-1">
                    {{ key.prefix }}
                    <span class="ix-status-pill" :class="key.environment === 'live' ? 'ix-status-pill-accent' : ''">{{ key.environment }}</span>
                  </p>
                  <p class="mt-0.5 font-mono text-[0.6875rem] text-fg-3">created {{ formatGovernStamp(key.createdAt) }}</p>
                </div>
              </td>
              <td class="truncate font-mono text-[0.75rem]">{{ key.scopes.join(" · ") }}</td>
              <td class="truncate text-xs">{{ key.createdBy }}</td>
              <td><RelativeTime :value="key.lastUsedAt" :now="GOVERN_NOW" /></td>
              <td>
                <span :class="keyTone(key.state)">{{ accessKeyRotationLabel(key) }}</span>
              </td>
              <td class="text-right">
                <ChevronRight :size="14" :stroke-width="1.8" class="text-fg-3" aria-hidden="true" />
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-if="!filteredKeys.length" class="px-4 py-10 text-center text-xs text-fg-3">
        No keys match this view.
      </div>
      <footer class="flex flex-wrap items-center justify-between gap-2 border-t border-line-subtle px-3 py-2 text-[0.6875rem] text-fg-3">
        <span>Secrets are shown once at creation and never again. Copy is a deliberate step-up action.</span>
        <span class="font-mono tabular-nums">{{ counts.activeKeys }} active · {{ counts.overdueKeys }} overdue · {{ counts.revokedKeys }} revoked</span>
      </footer>
    </section>

    <div v-if="state.tab === 'members'" class="flex flex-col gap-2 lg:hidden">
      <article
        v-for="member in filteredMembers"
        :key="member.id"
        :aria-label="`Open member ${member.name}`"
        tabindex="0"
        class="rounded-lg border border-line-subtle bg-surface p-3 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
        @click="openItem(member.id)"
        @keydown.enter.prevent="openItem(member.id)"
      >
        <div class="flex items-start justify-between gap-2">
          <div class="min-w-0">
            <p class="truncate text-xs font-medium text-fg-1">{{ member.name }}</p>
            <p class="mt-0.5 truncate font-mono text-[0.625rem] text-fg-3">{{ member.email }}</p>
          </div>
          <span class="shrink-0" :class="memberTone(member.status)">{{ member.status }}</span>
        </div>
        <p class="mt-2 text-[0.6875rem] text-fg-2">{{ member.role }} · <span class="font-mono">{{ member.scope }}</span></p>
        <p class="mt-1 text-[0.6875rem] text-fg-3">
          <span v-if="member.mfaVerifiedAt">MFA <RelativeTime :value="member.mfaVerifiedAt" :now="GOVERN_NOW" /> · </span>
          <span v-else class="text-warn">MFA pending · </span>
          last active <RelativeTime :value="member.lastActiveAt" :now="GOVERN_NOW" />
        </p>
      </article>
      <p v-if="!filteredMembers.length" class="rounded-lg border border-dashed border-line-subtle px-4 py-8 text-center text-xs text-fg-3">
        No members match this view.
      </p>
    </div>

    <section v-if="state.tab === 'members'" class="console-panel hidden min-w-0 overflow-hidden lg:block">
      <div class="overflow-x-auto" tabindex="0" aria-label="Access members table">
        <table class="ix-table min-w-[46rem]">
          <thead>
            <tr>
              <th scope="col">Member</th>
              <th scope="col" class="w-24">Role</th>
              <th scope="col" class="w-28">Scope</th>
              <th scope="col" class="w-24">Status</th>
              <th scope="col" class="w-32">MFA / session</th>
              <th scope="col" class="w-28">Last active</th>
              <th scope="col" class="w-10"><span class="sr-only">Open</span></th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="member in filteredMembers"
              :key="member.id"
              :data-access-row="member.id"
              :data-selected="state.item === member.id"
              tabindex="0"
              class="cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-accent"
              @click="openItem(member.id)"
              @keydown.enter.prevent="openItem(member.id)"
            >
              <td>
                <div class="min-w-0">
                  <p class="truncate text-xs font-medium text-fg-1">{{ member.name }}</p>
                  <p class="mt-0.5 truncate font-mono text-[0.6875rem] text-fg-3">{{ member.email }}</p>
                </div>
              </td>
              <td class="text-xs">{{ member.role }}</td>
              <td class="font-mono text-xs">{{ member.scope }}</td>
              <td><span :class="memberTone(member.status)">{{ member.status }}</span></td>
              <td>
                <span v-if="member.mfaVerifiedAt" class="font-mono text-[0.75rem] text-fg-2">
                  <RelativeTime :value="member.mfaVerifiedAt" :now="GOVERN_NOW" /> · verified
                </span>
                <span v-else class="font-mono text-[0.75rem] text-warn">pending</span>
              </td>
              <td><RelativeTime :value="member.lastActiveAt" :now="GOVERN_NOW" /></td>
              <td class="text-right">
                <ChevronRight :size="14" :stroke-width="1.8" class="text-fg-3" aria-hidden="true" />
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-if="!filteredMembers.length" class="px-4 py-10 text-center text-xs text-fg-3">
        No members match this view.
      </div>
    </section>

    <div v-if="state.tab === 'sessions'" class="flex flex-col gap-2 lg:hidden">
      <article
        v-for="session in filteredSessions"
        :key="session.id"
        :aria-label="`Open session for ${session.actor}`"
        tabindex="0"
        class="rounded-lg border border-line-subtle bg-surface p-3 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
        @click="openItem(session.id)"
        @keydown.enter.prevent="openItem(session.id)"
      >
        <div class="flex items-start justify-between gap-2">
          <div class="min-w-0">
            <p class="truncate text-xs font-medium text-fg-1">{{ session.actor }}</p>
            <p class="mt-0.5 truncate text-[0.6875rem] text-fg-3">{{ session.device }}</p>
          </div>
          <span class="shrink-0" :class="sessionTone(session)">{{ session.mfa }}</span>
        </div>
        <p class="mt-2 font-mono text-[0.6875rem] text-fg-2">{{ session.origin ?? "—" }}</p>
        <p class="mt-1 text-[0.6875rem] text-fg-3">last seen <RelativeTime :value="session.lastSeenAt" :now="GOVERN_NOW" /> · {{ session.state }}</p>
      </article>
      <p v-if="!filteredSessions.length" class="rounded-lg border border-dashed border-line-subtle px-4 py-8 text-center text-xs text-fg-3">
        No sessions match this view.
      </p>
    </div>

    <section v-if="state.tab === 'sessions'" class="console-panel hidden min-w-0 overflow-hidden lg:block">
      <div class="overflow-x-auto" tabindex="0" aria-label="Access sessions table">
        <table class="ix-table min-w-[42rem]">
          <thead>
            <tr>
              <th scope="col">Actor</th>
              <th scope="col">Device</th>
              <th scope="col" class="w-36">Origin</th>
              <th scope="col" class="w-28">MFA</th>
              <th scope="col" class="w-28">Last seen</th>
              <th scope="col" class="w-24">State</th>
              <th scope="col" class="w-10"><span class="sr-only">Open</span></th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="session in filteredSessions"
              :key="session.id"
              :data-access-row="session.id"
              :data-selected="state.item === session.id"
              tabindex="0"
              class="cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-accent"
              @click="openItem(session.id)"
              @keydown.enter.prevent="openItem(session.id)"
            >
              <td class="text-xs font-medium text-fg-1">{{ session.actor }}</td>
              <td class="text-xs">{{ session.device }}</td>
              <td class="font-mono text-[0.75rem]">{{ session.origin ?? "—" }}</td>
              <td><span :class="sessionTone(session)">{{ session.mfa }}</span></td>
              <td><RelativeTime :value="session.lastSeenAt" :now="GOVERN_NOW" /></td>
              <td><span class="ix-status-pill">{{ session.state }}</span></td>
              <td class="text-right">
                <ChevronRight :size="14" :stroke-width="1.8" class="text-fg-3" aria-hidden="true" />
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-if="!filteredSessions.length" class="px-4 py-10 text-center text-xs text-fg-3">
        No sessions match this view.
      </div>
      <footer class="border-t border-line-subtle px-3 py-2 text-[0.6875rem] text-fg-3">
        Session list is read-only. Sign-out and MFA reset require a privileged write contract.
      </footer>
    </section>

    <div v-if="state.tab === 'roles'" class="flex flex-col gap-2 lg:hidden">
      <article v-for="(role, roleIndex) in ACCESS_ROLES" :key="role" class="rounded-lg border border-line-subtle bg-surface p-3">
        <h3 class="text-xs font-medium text-fg-1">{{ role }}</h3>
        <p class="mt-1.5 text-[0.6875rem] leading-4 text-fg-3">
          {{ roleCapabilities(roleIndex) }}
        </p>
      </article>
    </div>

    <section v-if="state.tab === 'roles'" class="console-panel hidden min-w-0 overflow-hidden lg:block">
      <div class="overflow-x-auto" tabindex="0" aria-label="Role capability matrix">
        <table class="ix-table min-w-[52rem]">
          <thead>
            <tr>
              <th scope="col" class="w-40">Role</th>
              <th v-for="capability in ACCESS_CAPABILITIES" :key="capability" scope="col" class="w-28">{{ capability }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(role, roleIndex) in ACCESS_ROLES" :key="role">
              <td class="font-medium text-fg-1">{{ role }}</td>
              <td v-for="(capability, capabilityIndex) in ACCESS_CAPABILITIES" :key="capability">
                <span v-if="ACCESS_MATRIX[roleIndex]?.[capabilityIndex]" class="ix-status-pill ix-status-pill-ok">allow</span>
                <span v-else class="font-mono text-[0.75rem] text-fg-off">—</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <footer class="flex flex-wrap items-center justify-between gap-2 border-t border-line-subtle px-3 py-2 text-[0.6875rem] text-fg-3">
        <span>Reading metadata is separate from reading sensitive content. Viewer access never implies content access.</span>
        <span class="font-mono tabular-nums">{{ ACCESS_ROLES.length }} roles · {{ ACCESS_CAPABILITIES.length }} capabilities</span>
      </footer>
    </section>

    <Sheet :open="drawerOpen" @update:open="(open) => { if (!open) closeDrawer() }">
      <SheetContent class="w-full sm:max-w-md">
        <SheetHeader class="gap-1">
          <SheetTitle class="text-base">
            <template v-if="selectedKey">Key {{ selectedKey.prefix }}</template>
            <template v-else-if="selectedMember">{{ selectedMember.name }}</template>
            <template v-else-if="selectedSession">{{ selectedSession.actor }} session</template>
          </SheetTitle>
          <SheetDescription class="text-xs">
            <template v-if="selectedKey">Prefix, scopes, rotation, and provenance.</template>
            <template v-else-if="selectedMember">Role, scope, MFA, and last activity.</template>
            <template v-else>Device, origin, MFA, and last activity.</template>
          </SheetDescription>
        </SheetHeader>

        <div v-if="selectedKey" class="space-y-4 px-4">
          <dl class="space-y-2 text-xs">
            <div class="flex items-start justify-between gap-3 border-b border-line-subtle pb-2">
              <dt class="text-fg-3">State</dt>
              <dd><span :class="keyTone(selectedKey.state)">{{ selectedKey.state }}</span></dd>
            </div>
            <div class="flex items-start justify-between gap-3 border-b border-line-subtle pb-2">
              <dt class="text-fg-3">Environment</dt>
              <dd class="font-mono">{{ selectedKey.environment }}</dd>
            </div>
            <div class="flex items-start justify-between gap-3 border-b border-line-subtle pb-2">
              <dt class="text-fg-3">Scopes</dt>
              <dd class="max-w-[60%] text-right font-mono text-[0.6875rem] leading-4">{{ selectedKey.scopes.join(" · ") }}</dd>
            </div>
            <div class="flex items-start justify-between gap-3 border-b border-line-subtle pb-2">
              <dt class="text-fg-3">Created</dt>
              <dd class="text-right"><span>{{ formatGovernStamp(selectedKey.createdAt) }}</span><span class="block text-fg-3">by {{ selectedKey.createdBy }}</span></dd>
            </div>
            <div class="flex items-start justify-between gap-3 border-b border-line-subtle pb-2">
              <dt class="text-fg-3">Last used</dt>
              <dd><span>{{ formatGovernStamp(selectedKey.lastUsedAt) }}</span><span class="block text-right text-fg-3"><RelativeTime :value="selectedKey.lastUsedAt" :now="GOVERN_NOW" /></span></dd>
            </div>
            <div class="flex items-start justify-between gap-3">
              <dt class="text-fg-3">Rotation</dt>
              <dd>{{ accessKeyRotationLabel(selectedKey) }}</dd>
            </div>
          </dl>
          <div class="flex flex-wrap gap-2 border-t border-line-subtle pt-3">
            <GovernLockedAction label="Rotate key" :icon="RotateCw" />
            <GovernLockedAction label="Revoke key" :icon="Lock" variant="destructive" />
          </div>
        </div>

        <div v-else-if="selectedMember" class="space-y-4 px-4">
          <dl class="space-y-2 text-xs">
            <div class="flex items-start justify-between gap-3 border-b border-line-subtle pb-2">
              <dt class="text-fg-3">Email</dt>
              <dd class="font-mono">{{ selectedMember.email }}</dd>
            </div>
            <div class="flex items-start justify-between gap-3 border-b border-line-subtle pb-2">
              <dt class="text-fg-3">Role</dt>
              <dd>{{ selectedMember.role }}</dd>
            </div>
            <div class="flex items-start justify-between gap-3 border-b border-line-subtle pb-2">
              <dt class="text-fg-3">Scope</dt>
              <dd class="font-mono">{{ selectedMember.scope }}</dd>
            </div>
            <div class="flex items-start justify-between gap-3 border-b border-line-subtle pb-2">
              <dt class="text-fg-3">Status</dt>
              <dd><span :class="memberTone(selectedMember.status)">{{ selectedMember.status }}</span></dd>
            </div>
            <div class="flex items-start justify-between gap-3 border-b border-line-subtle pb-2">
              <dt class="text-fg-3">MFA</dt>
              <dd>
                <span v-if="selectedMember.mfaVerifiedAt">{{ formatGovernStamp(selectedMember.mfaVerifiedAt) }}</span>
                <span v-else class="text-warn">pending</span>
              </dd>
            </div>
            <div class="flex items-start justify-between gap-3">
              <dt class="text-fg-3">Last active</dt>
              <dd><RelativeTime :value="selectedMember.lastActiveAt" :now="GOVERN_NOW" /></dd>
            </div>
          </dl>
          <div class="flex flex-wrap gap-2 border-t border-line-subtle pt-3">
            <GovernLockedAction label="Change role" :icon="ShieldCheck" />
            <GovernLockedAction label="Remove member" :icon="Lock" variant="destructive" />
          </div>
        </div>

        <div v-else-if="selectedSession" class="space-y-4 px-4">
          <dl class="space-y-2 text-xs">
            <div class="flex items-start justify-between gap-3 border-b border-line-subtle pb-2">
              <dt class="text-fg-3">Device</dt>
              <dd>{{ selectedSession.device }}</dd>
            </div>
            <div class="flex items-start justify-between gap-3 border-b border-line-subtle pb-2">
              <dt class="text-fg-3">Origin</dt>
              <dd class="font-mono">{{ selectedSession.origin ?? "—" }}</dd>
            </div>
            <div class="flex items-start justify-between gap-3 border-b border-line-subtle pb-2">
              <dt class="text-fg-3">MFA</dt>
              <dd><span :class="sessionTone(selectedSession)">{{ selectedSession.mfa }}</span></dd>
            </div>
            <div class="flex items-start justify-between gap-3 border-b border-line-subtle pb-2">
              <dt class="text-fg-3">Last seen</dt>
              <dd><RelativeTime :value="selectedSession.lastSeenAt" :now="GOVERN_NOW" /></dd>
            </div>
            <div class="flex items-start justify-between gap-3">
              <dt class="text-fg-3">State</dt>
              <dd>{{ selectedSession.state }}</dd>
            </div>
          </dl>
          <div class="flex flex-wrap gap-2 border-t border-line-subtle pt-3">
            <GovernLockedAction label="Sign out session" :icon="Laptop" variant="destructive" />
          </div>
        </div>
      </SheetContent>
    </Sheet>
  </div>
</template>
