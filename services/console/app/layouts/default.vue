<script setup lang="ts">
import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar"

const config = useRuntimeConfig()
const hydrated = ref(false)

onMounted(() => {
  hydrated.value = true
})
</script>

<template>
  <SidebarProvider :data-console-hydrated="hydrated ? 'true' : undefined">
    <a
      href="#console-main"
      class="sr-only z-50 rounded-md border border-line bg-surface px-3 py-2 text-sm text-fg-1 focus:not-sr-only focus:fixed focus:left-3 focus:top-3"
    >
      Skip to content
    </a>
    <AppSidebar />
    <SidebarInset class="min-w-0 overflow-x-clip bg-canvas p-1.5 sm:p-2">
      <div class="flex min-h-0 min-w-0 flex-1 flex-col overflow-clip rounded-xl border border-line-subtle bg-canvas">
        <ConsoleHeader />
        <PreviewBanner />
        <div id="console-main" class="flex min-w-0 flex-1 flex-col overflow-x-clip">
          <div class="flex w-full flex-1 flex-col px-4 py-5 sm:px-5 lg:px-6 lg:py-6">
            <slot />
          </div>
        </div>
        <footer class="border-t border-line-subtle px-4 py-3 sm:px-5 lg:px-6">
          <div class="flex w-full flex-wrap items-center justify-between gap-2 text-[0.6875rem] text-fg-3">
            <span class="flex items-center gap-2">
              <span class="font-mono uppercase tracking-[0.12em]">IBEX Harness</span>
              <span aria-hidden="true">·</span>
              <span>{{ config.public.ibexEnv }}</span>
              <span aria-hidden="true">·</span>
              <span>Read-only console</span>
            </span>
            <nav class="flex items-center gap-4" aria-label="Footer">
              <a
                href="https://ibexharness.com/docs/architecture/status-and-evidence"
                target="_blank"
                rel="noreferrer"
                class="underline-offset-4 hover:text-fg-1 hover:underline"
              >
                Status &amp; evidence
              </a>
              <a
                href="https://ibexharness.com/docs"
                target="_blank"
                rel="noreferrer"
                class="underline-offset-4 hover:text-fg-1 hover:underline"
              >
                Docs
              </a>
            </nav>
          </div>
        </footer>
      </div>
    </SidebarInset>
  </SidebarProvider>
</template>
