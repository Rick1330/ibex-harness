<script setup lang="ts">
import { BookOpen, ChevronDown, ExternalLink } from "@lucide/vue"
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
} from "@/components/ui/sidebar"
import { footerNavigation, platformNavigation, primaryNavigation, type NavItem } from "@/lib/navigation"

const route = useRoute()

function isActive(to: string): boolean {
  if (to === "/") return route.path === "/"
  return route.path === to || route.path.startsWith(`${to}/`)
}

function itemClass(item: NavItem): string[] {
  return [isActive(item.to) ? "nav-active" : "nav-live"]
}
</script>

<template>
  <Sidebar collapsible="offcanvas" class="console-sidebar">
    <SidebarHeader class="border-b border-sidebar-border px-2.5 py-2.5">
      <NuxtLink
        to="/"
        class="flex min-w-0 items-center gap-2.5 rounded-md px-0.5 py-0.5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        aria-label="IBEX Console overview"
      >
        <span class="brand-mark">
          <img src="/brand/ibex-mark-light.png" alt="" class="size-6 dark:hidden" >
          <img src="/brand/ibex-mark-dark.png" alt="" class="hidden size-6 dark:block" >
        </span>
        <span class="min-w-0">
          <span class="block truncate text-[0.9375rem] leading-5 font-semibold tracking-tight text-fg-1">IBEX Console</span>
          <span class="block truncate text-[0.6875rem] leading-3.5 text-fg-3">Operator workspace</span>
        </span>
      </NuxtLink>
    </SidebarHeader>

    <SidebarContent class="ix-sidebar-scroll">
      <SidebarGroup v-for="group in primaryNavigation" :key="group.label" class="py-1">
        <details open class="group/nav">
          <summary class="ix-nav-group">
            <ChevronDown
              :size="12"
              :stroke-width="1.9"
              class="ix-nav-chevron"
              aria-hidden="true"
            />
            <span>{{ group.label }}</span>
          </summary>
          <SidebarGroupContent>
            <SidebarMenu class="gap-px">
              <SidebarMenuItem v-for="item in group.items" :key="item.to">
                <SidebarMenuButton
                  as-child
                  :is-active="isActive(item.to)"
                  :tooltip="item.label"
                  class="ix-nav-item h-[1.875rem]"
                  :class="itemClass(item)"
                >
                  <NuxtLink :to="item.to">
                    <component :is="item.icon" :size="15" :stroke-width="1.75" aria-hidden="true" />
                    <span>{{ item.label }}</span>
                  </NuxtLink>
                </SidebarMenuButton>
              </SidebarMenuItem>
            </SidebarMenu>
          </SidebarGroupContent>
        </details>
      </SidebarGroup>

      <SidebarGroup class="py-1">
        <details class="group/nav">
          <summary class="ix-nav-group">
            <ChevronDown
              :size="12"
              :stroke-width="1.9"
              class="ix-nav-chevron"
              aria-hidden="true"
            />
            <span>Platform tier</span>
            <span class="ix-tier-badge">Preview</span>
          </summary>
          <SidebarGroupContent>
            <p class="ix-tier-note">
              Not part of the memory/context console. Promotion needs a design partner and an owning contract.
            </p>
            <SidebarMenu class="gap-px">
              <SidebarMenuItem v-for="item in platformNavigation" :key="item.to">
                <SidebarMenuButton
                  as-child
                  :is-active="isActive(item.to)"
                  :tooltip="item.label"
                  class="ix-nav-item h-[1.875rem]"
                  :class="itemClass(item)"
                >
                  <NuxtLink :to="item.to">
                    <component :is="item.icon" :size="15" :stroke-width="1.75" aria-hidden="true" />
                    <span>{{ item.label }}</span>
                  </NuxtLink>
                </SidebarMenuButton>
              </SidebarMenuItem>
            </SidebarMenu>
          </SidebarGroupContent>
        </details>
      </SidebarGroup>
    </SidebarContent>

    <SidebarFooter class="border-t border-sidebar-border px-2.5 py-2.5">
      <p class="mb-1.5 flex items-center gap-1.5 px-2 font-mono text-[0.5625rem] tracking-[0.06em] text-fg-3 uppercase">
        <span class="size-1 rounded-full bg-ok" aria-hidden="true" />
        Local · read-only
      </p>
      <div class="space-y-0.5">
        <a
          v-for="link in footerNavigation"
          :key="link.href"
          :href="link.href"
          target="_blank"
          rel="noreferrer"
          class="flex min-h-7 items-center gap-2 rounded-md px-2 text-[0.75rem] text-fg-3 transition-colors hover:bg-sidebar-accent hover:text-fg-1"
        >
          <BookOpen v-if="link.label === 'Documentation'" :size="14" :stroke-width="1.75" aria-hidden="true" />
          <span v-else class="size-2 rounded-full bg-accent" aria-hidden="true" />
          <span>{{ link.label.replace(" and ", " & ") }}</span>
          <ExternalLink class="ml-auto text-fg-3/70" :size="13" :stroke-width="1.75" aria-hidden="true" />
        </a>
      </div>
    </SidebarFooter>
  </Sidebar>
</template>

<style scoped>
.brand-mark {
  display: inline-flex;
  width: 1.75rem;
  height: 1.75rem;
  flex: none;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--sidebar-border);
  border-radius: 6px;
  background: var(--sidebar-accent);
}

.ix-nav-group {
  display: flex;
  height: 1.5rem;
  cursor: pointer;
  list-style: none;
  align-items: center;
  gap: 0.25rem;
  padding: 0 0.5rem;
  font-size: 0.6875rem;
  font-weight: 500;
  color: var(--ix-fg-3);
  user-select: none;
}

.ix-nav-group::-webkit-details-marker {
  display: none;
}

.ix-nav-chevron {
  flex: none;
  transform: rotate(-90deg);
  transition: transform 150ms ease;
}

details[open] > .ix-nav-group .ix-nav-chevron {
  transform: rotate(0deg);
}

.ix-nav-group:hover {
  color: var(--ix-fg-2);
}

.ix-tier-badge {
  margin-left: auto;
  border: 1px solid var(--sidebar-border);
  border-radius: 999px;
  padding: 0 0.375rem;
  font-family: var(--font-mono, ui-monospace, monospace);
  font-size: 0.5rem;
  line-height: 1rem;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--ix-fg-3);
}

.ix-tier-note {
  padding: 0 0.5rem 0.375rem;
  font-size: 0.625rem;
  line-height: 0.9375rem;
  color: var(--ix-fg-3);
}

.ix-nav-group:focus-visible {
  outline: 2px solid var(--ix-accent);
  outline-offset: 1px;
  border-radius: 4px;
}

.ix-nav-item {
  padding: 0 0.5rem;
  font-size: 0.75rem;
  font-weight: 500;
  color: var(--sidebar-foreground);
  transition: background-color 120ms, color 120ms;
}

.ix-nav-item.nav-live {
  color: var(--ix-fg-2);
}

.ix-nav-item:hover {
  color: var(--sidebar-accent-foreground);
}

.ix-nav-item.nav-active {
  background: color-mix(in srgb, var(--ix-accent) 9%, var(--sidebar-accent));
  color: var(--ix-accent);
  font-weight: 600;
  box-shadow: inset 2px 0 0 var(--ix-accent);
}

.ix-nav-item.nav-active :deep(svg) {
  color: var(--ix-accent);
}

:deep([data-slot="sidebar-menu-button"]) {
  border-radius: 6px;
}
</style>
