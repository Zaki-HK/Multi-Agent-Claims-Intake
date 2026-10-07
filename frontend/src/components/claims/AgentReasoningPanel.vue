<script setup>
import { computed } from 'vue'
import { percent, humanize } from '../../composables/useClaims'
import AppIcon from '../AppIcon.vue'
const props = defineProps({ assessment: Object })
const stages = [
  { key: 'intake', field: 'intake_result', label: 'Multimodal intake' },
  { key: 'triage', field: 'triage_result', label: 'Triage & priority' },
  { key: 'duplicate', field: 'duplicate_check', label: 'Duplicate detection' },
  { key: 'policy', field: 'policy_check_result', label: 'Policy & coverage' },
  { key: 'medical', field: 'medical_codes', label: 'Medical reference matching' },
  { key: 'fraud', field: 'fraud_signals', label: 'Fraud screening' },
  { key: 'summary', field: 'summary', label: 'Assessment summary' },
]
const nodes = computed(() =>
  stages.map((stage) => {
    const raw = props.assessment?.[stage.field]
    const trace = props.assessment?.agent_reasoning_trace?.[stage.key]
    const output = raw && typeof raw === 'object' && Object.keys(raw).length ? raw : trace
    return {
      ...stage,
      output,
      complete:
        typeof raw === 'string' ? Boolean(raw) : Boolean(output && Object.keys(output).length),
    }
  }),
)
</script>
<template>
  <div class="panel">
    <div class="section-heading">
      <div>
        <h2>Agent assessments</h2>
        <p>Supporting facts and uncertainty at each step.</p>
      </div>
    </div>
    <details v-for="(node, index) in nodes" :key="node.key" class="agent-step">
      <summary>
        <span class="agent-number">{{ String(index + 1).padStart(2, '0') }}</span
        ><span>{{ node.label }}</span
        ><small>{{ node.complete ? 'Completed' : 'Awaiting assessment' }}</small
        ><AppIcon :name="node.complete ? 'success' : 'clock'" :size="16" /><AppIcon
          name="down"
          :size="15"
          class="chevron"
        />
      </summary>
      <div class="agent-body" v-if="node.complete">
        <p v-if="node.output?.rationale">{{ node.output.rationale }}</p>
        <p v-else-if="node.key === 'summary'">{{ assessment.summary }}</p>
        <p v-if="node.output?.confidence !== undefined">
          Assessment confidence: <strong>{{ percent(node.output.confidence) }}</strong>
        </p>
        <p v-if="node.key === 'policy'">
          Coverage: <strong>{{ humanize(node.output?.coverage_status) }}</strong>
        </p>
        <ul v-if="node.output?.missing_information?.length">
          <li v-for="item in node.output.missing_information" :key="item">{{ item }}</li>
        </ul>
        <ul v-if="node.output?.red_flags?.length">
          <li v-for="flag in node.output.red_flags" :key="flag.evidence_id">
            {{ flag.explanation }}
          </li>
        </ul>
        <div
          v-for="citation in node.output?.citations || []"
          :key="citation.citation_id"
          class="citation"
        >
          <strong>{{ citation.section_title }}</strong
          ><small
            >{{ citation.source_filename }} · Pages
            {{ citation.page_numbers?.join(', ') || citation.page_number || 'unavailable' }}</small
          ><small class="mono">{{ citation.citation_id }}</small>
          <blockquote>{{ citation.text }}</blockquote>
        </div>
        <details>
          <summary>View structured assessment</summary>
          <pre>{{ JSON.stringify(node.output || { summary: assessment.summary }, null, 2) }}</pre>
        </details>
      </div>
      <div v-else class="agent-body">This stage has not produced an assessment yet.</div>
    </details>
  </div>
</template>
