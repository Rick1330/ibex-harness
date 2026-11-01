<script setup lang="ts">
import { computed, ref } from "vue"
import {
  ChevronRight,
  CircleHelp,
  Command,
  ExternalLink,
  Lock,
  Search,
} from "@lucide/vue"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { SidebarTrigger } from "@/components/ui/sidebar"
import { findNavigationItem, navigationGroupFor } from "@/lib/navigation"
import { getAgentPreview } from "@/lib/agent-preview"
import { formatUtc } from "@/lib/format"
import CommandMenu from "@/components/console/CommandMenu.vue"
import ThemeToggle from "@/components/console/ThemeToggle.vue"

const route = useRoute()
const config = useRuntimeConfig()
const commandMenu = ref<InstanceType<typeof CommandMenu> | null>(null)
const contextState = useOperatorContext()
const context = computed(() => contextState.data.value ?? null)

const current = computed(() => {
  if (route.path.startsWith("/explore/t/")) {
    return { label: "Trace runs", group: "Investigate", availability: "live" as const }
  }
  if (route.path.startsWith("/explore/r/")) {
    return { label: "Run detail", group: "Investigate", availability: "live" as const }
  }
  const item = findNavigationItem(route.path)
  if (!item) return { label: "Console", group: "Workspace", availability: "live" as const }
  return { label: item.label, group: navigationGroupFor(item), availability: item.availability }
})

const orgInitial = computed(() => (context.value?.org_name ?? "I").slice(0, 1).toUpperCase())
const sessionCrumb = computed(() => {
  const match = route.path.match(/^\/sessions\/([^/]+)$/)
  return match ? decodeURIComponent(match[1]!) : null
})

const agentCrumb = computed(() => {
  const match = route.path.match(/^\/agents\/([^/]+)$/)
  if (!match) return null
  const id = decodeURIComponent(match[1]!)
  return getAgentPreview(id)?.name ?? id
})

function openCommand(): void {
  commandMenu.value?.open()
}
</script>

<template>
  <header
    class="sticky top-0 z-20 flex h-12 shrink-0 items-center gap-3 border-b border-line-subtle bg-canvas/95 px-3 backdrop-blur-sm sm:px-4"
  >
    <SidebarTrigger class="ix-header-button shrink-0" />
    <nav class="flex min-w-0 items-center gap-1.5" aria-label="Breadcrumb">
      <span class="hidden truncate text-xs text-fg-3 lg:inline">{{ current.group }}</span>
      <ChevronRight class="hidden shrink-0 text-fg-3/60 lg:block" :size="13" :stroke-width="1.75" aria-hidden="true" />
      <span class="truncate text-xs font-medium text-fg-1">{{ current.label }}</span>
      <template v-if="sessionCrumb">
        <ChevronRight class="shrink-0 text-fg-3/60" :size="13" :stroke-width="1.75" aria-hidden="true" />
        <span class="truncate font-mono text-[0.6875rem] text-fg-3">{{ sessionCrumb }}</span>
      </template>
      <template v-if="agentCrumb">
        <ChevronRight class="shrink-0 text-fg-3/60" :size="13" :stroke-width="1.75" aria-hidden="true" />
        <span class="truncate font-mono text-[0.6875rem] text-fg-3">{{ agentCrumb }}</span>
      </template>
    </nav>

    <div class="ml-auto flex items-center gap-1">
      <button
        type="button"
        class="ix-command-field hidden md:flex"
        aria-label="Search pages and surfaces"
        @click="openCommand"
      >
        <Search :size="14" :stroke-width="1.75" aria-hidden="true" />
        <span class="truncate">Search or jump</span>
        <kbd class="ix-kbd ml-auto">
          <Command :size="11" :stroke-width="1.9" aria-hidden="true" />K
        </kbd>
      </button>


      <button
        type="button"
        class="ix-header-button md:!hidden"
        aria-label="Search pages and surfaces"
        @click="openCommand"
      >
        <Search :size="16" :stroke-width="1.75" aria-hidden="true" />
      </button>

      <Tooltip>
        <TooltipTrigger as-child>
          <a
            href="https://ibexharness.com/docs/architecture/status-and-evidence"
            target="_blank"
            rel="noreferrer"
            class="ix-header-button hidden sm:inline-flex"
            aria-label="Status and evidence documentation"
          >
            <CircleHelp :size="15" :stroke-width="1.75" aria-hidden="true" />
          </a>
        </TooltipTrigger>
        <TooltipContent side="bottom" :side-offset="6" class="!bg-overlay !text-fg-1 !border !border-line">
          Status and evidence
        </TooltipContent>
      </Tooltip>

      <ThemeToggle />

      <DropdownMenu>
        <DropdownMenuTrigger as-child>
          <button type="button" class="ix-session-trigger" aria-label="Session and organization menu">
            <span class="ix-session-avatar">{{ orgInitial }}</span>
            <span class="hidden min-w-0 text-left xl:block">
              <span class="block max-w-40 truncate text-[0.75rem] font-medium leading-4">
                {{ context?.org_name ?? "Organization" }}
              </span>
              <span class="block max-w-40 truncate font-mono text-[0.625rem] leading-3 text-fg-3">
                {{ context?.role ?? "session" }} · read-only
              </span>
            </span>
          </button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" class="w-72 p-1.5">
          <DropdownMenuLabel class="px-2 py-1.5">
            <span class="block text-xs font-semibold text-fg-1">{{ context?.org_name ?? "Organization context" }}</span>
            <span class="mt-0.5 block font-mono text-[0.8125rem] font-normal text-fg-3">
              {{ context?.org_slug ?? "no verified context" }}
            </span>
          </DropdownMenuLabel>
          <DropdownMenuSeparator />
          <dl v-if="context" class="space-y-1.5 px-2 py-1.5 text-xs">
            <div class="flex items-center justify-between gap-3">
              <dt class="text-fg-3">Role</dt>
              <dd class="capitalize text-fg-1">{{ context.role ?? "—" }}</dd>
            </div>
            <div class="flex items-center justify-between gap-3">
              <dt class="text-fg-3">Status</dt>
              <dd class="capitalize text-fg-1">{{ context.org_status }}</dd>
            </div>
            <div class="flex items-center justify-between gap-3">
              <dt class="text-fg-3">Verified</dt>
              <dd class="font-mono text-[0.8125rem] text-fg-1">{{ formatUtc(context.observed_at) }}</dd>
            </div>
          </dl>
          <div v-else class="px-2 py-2 text-xs leading-4 text-fg-2">
            Organization context is unavailable. No identity is inferred from the URL.
          </div>
          <DropdownMenuSeparator />
          <div class="flex items-center gap-2 px-2 py-1.5 text-[0.8125rem] text-fg-3">
            <Lock :size="16" :stroke-width="1.75" aria-hidden="true" />
            Read-only session · {{ config.public.ibexEnv }}
          </div>
          <DropdownMenuSeparator />
          <DropdownMenuItem as-child>
            <a
              href="https://ibexharness.com/docs"
              target="_blank"
              rel="noreferrer"
              class="flex items-center gap-2"
            >
              <ExternalLink :size="16" :stroke-width="1.75" aria-hidden="true" />
              Documentation
            </a>
          </DropdownMenuItem>
          <DropdownMenuItem as-child>
            <a
              href="https://ibexharness.com/docs/architecture/status-and-evidence"
              target="_blank"
              rel="noreferrer"
              class="flex items-center gap-2"
            >
              <ExternalLink :size="16" :stroke-width="1.75" aria-hidden="true" />
              Status and evidence
            </a>
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
    <CommandMenu ref="commandMenu" />
  </header>
</template>

<style scoped>
.ix-header-button {
  display: inline-flex;
  width: 2rem;
  height: 2rem;
  align-items: center;
  justify-content: center;
  border-radius: 5px;
  color: var(--ix-fg-3);
  transition: color 100ms, background-color 100ms;
}

.ix-header-button:hover {
  background: var(--ix-raised);
  color: var(--ix-fg-1);
}

.ix-command-field {
  width: 17rem;
  height: 2rem;
  align-items: center;
  gap: 0.5rem;
  border: 1px solid var(--ix-line-subtle);
  border-radius: 5px;
  padding: 0 0.625rem;
  background: var(--ix-surface);
  font-size: 0.8125rem;
  color: var(--ix-fg-3);
  transition: border-color 100ms, color 100ms;
}

.ix-command-field:hover {
  border-color: var(--ix-line);
  color: var(--ix-fg-2);
}

.ix-kbd {
  display: inline-flex;
  height: 1.125rem;
  align-items: center;
  gap: 0.125rem;
  border: 1px solid var(--ix-line-subtle);
  border-radius: 4px;
  padding: 0 0.3125rem;
  font-family: var(--font-mono);
  font-size: 0.6875rem;
  color: var(--ix-fg-3);
}

.ix-session-trigger {
  display: flex;
  height: 2rem;
  align-items: center;
  gap: 0.5rem;
  border: 1px solid var(--ix-line-subtle);
  border-radius: 5px;
  padding: 0 0.375rem;
  transition: border-color 100ms, background-color 100ms;
}

.ix-session-trigger:hover {
  border-color: var(--ix-line);
  background: var(--ix-raised);
}

.ix-session-avatar {
  display: inline-flex;
  width: 1.375rem;
  height: 1.375rem;
  flex: none;
  align-items: center;
  justify-content: center;
  border-radius: 4px;
  background: var(--ix-accent-tint);
  font-family: var(--font-mono);
  font-size: 0.6875rem;
  font-weight: 600;
  color: var(--ix-accent);
}
</style>
