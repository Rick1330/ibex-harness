<script setup lang="ts">
import { ref } from "vue"
import { Check, Copy, X } from "@lucide/vue"
import ConsolePageHeader from "@/components/console/ConsolePageHeader.vue"
import GovernStatTile from "@/components/console/govern/primitives/GovernStatTile.vue"
import AgentStatusPill from "../AgentStatusPill.vue"
import { formatGovernNumber, formatGovernStamp } from "@/lib/govern-format"
import type { PublicOperatorAgent } from "~~/shared/operator/public"

const props = defineProps<{ agent: PublicOperatorAgent; returnTo: string }>()

const copyState = ref<"idle" | "copied" | "failed">("idle")

async function copyId(): Promise<void> {
  if (!import.meta.client) return
  try {
    await navigator.clipboard.writeText(props.agent.id)
    copyState.value = "copied"
  } catch {
    copyState.value = "failed"
  }
  setTimeout(() => {
    copyState.value = "idle"
  }, 2000)
}

function providerLabel(): string {
  if (!props.agent.default_provider) return "Not set"
  return props.agent.default_model
    ? `${props.agent.default_provider} · ${props.agent.default_model}`
    : props.agent.default_provider
}
</script>

<template>
  <div class="flex min-w-0 flex-col gap-5">
    <ConsolePageHeader
      :title="agent.name"
      :definition="agent.description ?? 'Agent profile from the operator read model.'"
      state="live"
      :verdict="`Status: ${agent.status}`"
      contract="operator.agents.v1"
      scope="Organization"
      range="Agent record"
      :observed="agent.updated_at"
      :caveat="'Health, budget, environment, owner, and drift are not part of this contract and are not shown.'"
    >
      <template #back>
        <NuxtLink :to="returnTo" class="mb-2 inline-flex text-xs text-fg-3 hover:text-fg-1">
          ← Back to agents
        </NuxtLink>
      </template>
      <template #actions>
        <AgentStatusPill :status="agent.status" />
      </template>
    </ConsolePageHeader>

    <section class="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4" aria-label="Agent usage counters">
      <GovernStatTile
        label="Sessions"
        :value="formatGovernNumber(agent.total_sessions)"
        helper="Recorded in the operator projection"
      />
      <GovernStatTile
        label="Memories"
        :value="formatGovernNumber(agent.total_memories)"
        helper="Attributed to this agent"
      />
      <GovernStatTile
        label="Tokens used"
        :value="formatGovernNumber(agent.total_tokens_used)"
        helper="Cumulative across sessions"
      />
      <GovernStatTile
        label="Last active"
        :value="formatGovernStamp(agent.last_active_at)"
        helper="Reported by the agent record"
      />
    </section>

    <section class="grid grid-cols-1 gap-4 lg:grid-cols-3" aria-label="Agent profile">
      <div class="rounded-lg border border-line-subtle bg-surface p-4 lg:col-span-2">
        <h2 class="ix-heading text-fg-1">Identity</h2>
        <dl class="mt-3 grid grid-cols-1 gap-x-8 gap-y-3 sm:grid-cols-2">
          <div>
            <dt class="ix-label">Slug</dt>
            <dd class="mt-0.5 font-mono text-xs text-fg-1">{{ agent.slug }}</dd>
          </div>
          <div>
            <dt class="ix-label">Agent ID</dt>
            <dd class="mt-0.5 flex min-w-0 items-center gap-2">
              <span class="truncate font-mono text-xs text-fg-1">{{ agent.id }}</span>
              <button
                type="button"
                class="inline-flex shrink-0 items-center gap-1 text-[0.6875rem] text-fg-3 hover:text-fg-1"
                :aria-label="
                  copyState === 'copied'
                    ? 'Agent ID copied'
                    : copyState === 'failed'
                      ? 'Copy failed; select the agent ID and copy it manually'
                      : 'Copy agent ID'
                "
                @click="copyId"
              >
                <Check v-if="copyState === 'copied'" :size="12" :stroke-width="2" aria-hidden="true" />
                <X v-else-if="copyState === 'failed'" :size="12" :stroke-width="2" aria-hidden="true" />
                <Copy v-else :size="12" :stroke-width="2" aria-hidden="true" />
                {{ copyState === "copied" ? "Copied" : copyState === "failed" ? "Copy failed" : "Copy" }}
              </button>
            </dd>
          </div>
          <div>
            <dt class="ix-label">Provider and model</dt>
            <dd class="mt-0.5 text-xs text-fg-1">{{ providerLabel() }}</dd>
          </div>
          <div>
            <dt class="ix-label">Status</dt>
            <dd class="mt-1"><AgentStatusPill :status="agent.status" /></dd>
          </div>
          <div>
            <dt class="ix-label">Created</dt>
            <dd class="mt-0.5 font-mono text-xs text-fg-1">{{ formatGovernStamp(agent.created_at) }}</dd>
          </div>
          <div>
            <dt class="ix-label">Updated</dt>
            <dd class="mt-0.5 font-mono text-xs text-fg-1">{{ formatGovernStamp(agent.updated_at) }}</dd>
          </div>
        </dl>
      </div>

      <div class="rounded-lg border border-line-subtle bg-surface p-4">
        <h2 class="ix-heading text-fg-1">Tags</h2>
        <p v-if="agent.tags.length === 0" class="mt-2 text-xs text-fg-3">No tags on this agent.</p>
        <ul v-else class="mt-2 flex flex-wrap gap-1.5" aria-label="Agent tags">
          <li
            v-for="tag in agent.tags"
            :key="tag"
            class="rounded-full border border-line bg-raised px-2 py-0.5 font-mono text-[0.6875rem] text-fg-2"
          >
            {{ tag }}
          </li>
        </ul>
      </div>
    </section>
  </div>
</template>
