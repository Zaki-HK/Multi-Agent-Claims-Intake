<script setup>
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useClaimsStore } from '../stores/claims'
import { usePolling, dateTime, percent, number, humanize } from '../composables/useClaims'
import { evidenceUrl } from '../composables/useApi'
import AppIcon from '../components/AppIcon.vue'
import StatusBadge from '../components/StatusBadge.vue'
import ErrorAlert from '../components/ErrorAlert.vue'
import EmptyState from '../components/EmptyState.vue'
import MarkdownReport from '../components/MarkdownReport.vue'
import AgentReasoningPanel from '../components/claims/AgentReasoningPanel.vue'
import ClaimTimeline from '../components/claims/ClaimTimeline.vue'
import ReviewActionBar from '../components/reviews/ReviewActionBar.vue'
const route = useRoute()
const router = useRouter()
const store = useClaimsStore()
store.serial++
store.detail = null
store.timeline = []
store.history = []
const id = String(route.params.id)
const tabs = [
  { value: 'assessment', label: 'Assessment' },
  { value: 'evidence', label: 'Original submission' },
  { value: 'report', label: 'Report' },
  { value: 'review', label: 'Human review' },
]
const tab = computed(() =>
  tabs.some((item) => item.value === route.query.tab) ? route.query.tab : 'assessment',
)
function changeTab(value) {
  router.replace({ query: { ...route.query, tab: value } })
}
const claim = computed(() => store.detail)
const assessment = computed(() => claim.value?.assessment)
const reasons = computed(
  () => assessment.value?.agent_reasoning_trace?.supervisor?.review_reasons || [],
)
const finalDecision = computed(() => assessment.value?.agent_reasoning_trace?.decision)
const failure = computed(() => assessment.value?.agent_reasoning_trace?.pipeline_error)
const canRetry = computed(
  () => claim.value?.status === 'triaged' || (claim.value?.status === 'escalated' && failure.value),
)
const actionError = ref('')
const notice = ref('')
const retrying = ref(false)
const { refresh } = usePolling((signal) => store.fetchDetail(id, signal), {
  interval: 5000,
  enabled: () =>
    !claim.value || ['submitted', 'intake', 'processing', 'under_review'].includes(claim.value.status),
})
const extracted = computed(() => [
  ['Claimant', claim.value?.claimant_name],
  ['Policy number', claim.value?.policy_number],
  ['Incident date', claim.value?.incident_date ? dateTime(claim.value.incident_date, true) : null],
  [
    'Reported amount',
    claim.value?.estimated_amount !== null ? number(claim.value?.estimated_amount) : null,
  ],
  ['Injury / condition', claim.value?.injury_type],
  ['Body part', claim.value?.body_part_affected],
  ['Treatment reported', claim.value?.treatment_received],
  ['Provider', claim.value?.provider_name],
])
async function retry() {
  if (retrying.value) return
  retrying.value = true
  actionError.value = ''
  try {
    await store.retry(id)
    notice.value = 'Processing requested. Completed assessments will be retained.'
    await refresh()
  } catch (error) {
    actionError.value = error.message
  } finally {
    retrying.value = false
  }
}
async function decided(result) {
  notice.value = result.applied
    ? 'This decision has already been applied.'
    : 'Your decision was saved. The claim is resuming.'
  await refresh()
}
async function saved(error) {
  actionError.value = error.message
  notice.value = 'Your decision was saved. Resume processing when the service is available.'
  await refresh()
}
</script>
<template>
  <div class="page-heading">
    <div>
      <RouterLink to="/claims" class="text-link" style="margin-bottom: 15px"
        ><AppIcon name="back" :size="14" />All claims</RouterLink
      >
      <h1 class="detail-title">{{ claim?.claim_number || 'Claim workspace' }}</h1>
      <div v-if="claim" class="detail-subtitle">
        <StatusBadge :value="claim.status" /><span>{{
          claim.claimant_name || 'Claimant not provided'
        }}</span
        ><span>Submitted {{ dateTime(claim.created_at, true) }}</span>
      </div>
    </div>
    <div class="button-group">
      <button
        type="button"
        class="button button-secondary"
        :disabled="store.loading"
        @click="refresh"
      >
        <AppIcon name="refresh" :size="16" />Refresh</button
      ><button
        v-if="canRetry"
        type="button"
        class="button button-primary"
        :disabled="retrying"
        @click="retry"
      >
        <AppIcon
          :name="retrying ? 'loader' : 'arrow'"
          :size="16"
          :class="{ spin: retrying }"
        />Resume processing
      </button>
    </div>
  </div>
  <ErrorAlert :message="store.error" retry @retry="refresh" /><ErrorAlert :message="actionError" />
  <div v-if="notice" class="alert alert-success" role="status">
    <AppIcon name="success" /><span>{{ notice }}</span>
  </div>
  <div v-if="!claim && store.loading" class="panel loading-state" role="status">
    <AppIcon name="loader" class="spin" />Loading claim and evidence…
  </div>
  <template v-if="claim">
    <div v-if="claim.status === 'processing'" class="alert alert-info" role="status">
      <AppIcon name="clock" /><span>{{
        store.history.some((item) => !item.action_taken)
          ? 'Your recorded decision is being applied.'
          : 'This claim is being assessed. New results will appear as processing progresses.'
      }}</span>
    </div>
    <div v-if="failure" class="alert alert-error">
      <AppIcon name="alert" /><span>{{
        failure.retrying
          ? 'A service interruption occurred. Processing will retry automatically.'
          : 'Processing stopped before completion. Resume when the issue has been resolved.'
      }}</span>
    </div>
    <nav class="tabs" aria-label="Claim sections">
      <button
        v-for="item in tabs"
        :key="item.value"
        type="button"
        class="tab"
        :class="{ active: tab === item.value }"
        :aria-current="tab === item.value ? 'page' : undefined"
        @click="changeTab(item.value)"
      >
        {{ item.label }}
      </button>
    </nav>
    <div class="detail-grid">
      <div class="stack">
        <div v-if="tab === 'assessment' || tab === 'review'" class="panel">
          <div class="panel-body">
            <div class="section-heading">
              <h2>Extracted claim details</h2>
              <span class="muted text-small">Intake evidence</span>
            </div>
            <div v-if="assessment?.summary" class="summary-box">{{ assessment.summary }}</div>
            <dl class="definition-grid">
              <div v-for="[label, value] in extracted" :key="label">
                <dt>{{ label }}</dt>
                <dd>{{ value || 'Not provided' }}</dd>
              </div>
              <div class="wide">
                <dt>Incident description</dt>
                <dd>{{ claim.incident_description || 'Not provided' }}</dd>
              </div>
            </dl>
            <div
              v-if="assessment?.intake_result?.missing_fields?.length"
              class="alert"
              style="margin-top: 22px; margin-bottom: 0"
            >
              <AppIcon name="alert" :size="16" /><span
                >Missing information:
                {{ assessment.intake_result.missing_fields.map(humanize).join(', ') }}.</span
              >
            </div>
          </div>
        </div>
        <AgentReasoningPanel v-if="tab === 'assessment'" :assessment="assessment" />
        <div v-if="tab === 'evidence' || tab === 'review'" class="panel">
          <div class="panel-body">
            <div class="section-heading"><h2>Original submission</h2></div>
            <p class="narrative">{{ claim.raw_text }}</p>
            <div v-if="claim.images.length" style="margin-top: 25px">
              <h3>Supporting images</h3>
              <div class="evidence-grid">
                <a
                  v-for="image in claim.images"
                  :key="image.index"
                  :href="evidenceUrl(image.url)"
                  target="_blank"
                  rel="noopener noreferrer"
                  ><img
                    :src="evidenceUrl(image.url)"
                    :alt="'Evidence attachment ' + (image.index + 1)"
                    loading="lazy"
                  /><span>Attachment {{ image.index + 1 }} · Open original</span></a
                >
              </div>
            </div>
            <p v-else class="text-small muted" style="margin-top: 20px; margin-bottom: 0">
              No images were attached.
            </p>
          </div>
        </div>
        <div v-if="tab === 'report' || tab === 'review'" class="panel">
          <div class="panel-body">
            <MarkdownReport
              v-if="assessment?.assessment_report"
              :source="assessment.assessment_report"
              :filename="claim.claim_number"
            /><EmptyState
              v-else
              title="The report is still being prepared"
              message="It will be available after the assessment stages complete."
              icon="file"
            />
          </div>
        </div>
        <div v-if="tab === 'review' && store.history.length" class="panel">
          <div class="section-heading"><h2>Review history</h2></div>
          <div class="panel-body">
            <div v-for="review in store.history" :key="review.id" class="history-item">
              <strong
                >{{ humanize(review.decision.replace(':', ' → ')) }} ·
                {{ review.reviewer_id }}</strong
              >
              <p>
                {{ dateTime(review.created_at) }} ·
                {{
                  review.action_taken
                    ? 'Applied: ' + humanize(review.action_taken)
                    : 'Saved, awaiting application'
                }}
              </p>
              <p v-if="review.notes">{{ review.notes }}</p>
            </div>
          </div>
        </div>
      </div>
      <div class="stack">
        <div class="panel">
          <div class="panel-body">
            <div class="section-heading">
              <h2>Assessment snapshot</h2>
              <AppIcon name="shield" :size="19" class="muted" />
            </div>
            <dl class="definition-grid">
              <div>
                <dt>Priority</dt>
                <dd>
                  <StatusBadge v-if="claim.priority" :value="claim.priority" priority /><span v-else
                    >Awaiting triage</span
                  >
                </dd>
              </div>
              <div>
                <dt>Confidence</dt>
                <dd>{{ percent(claim.confidence_score) }}</dd>
              </div>
              <div class="wide">
                <dt>Fraud screening score</dt>
                <dd>
                  {{ percent(assessment?.fraud_signals?.risk_score)
                  }}<span class="muted"> · Screening only</span>
                </dd>
              </div>
            </dl>
            <div class="confidence-track" aria-hidden="true">
              <span :style="{ width: (claim.confidence_score || 0) * 100 + '%' }" />
            </div>
            <p class="text-small muted" style="margin-top: 13px; margin-bottom: 0">
              Confidence reflects assessment certainty, not a probability of approval.
            </p>
            <div
              v-if="finalDecision"
              class="summary-box"
              style="margin-top: 20px; margin-bottom: 0"
            >
              Decision: <strong>{{ humanize(finalDecision.status) }}</strong
              ><br />Source: {{ humanize(finalDecision.source)
              }}<span v-if="finalDecision.reviewer_id"
                ><br />Reviewer: {{ finalDecision.reviewer_id }}</span
              >
            </div>
          </div>
        </div>
        <div v-if="reasons.length && !finalDecision" class="panel">
          <div class="panel-body">
            <h2 style="margin-bottom: 15px">Why review is needed</h2>
            <ul class="text-small muted" style="padding-left: 18px; line-height: 1.9">
              <li v-for="reason in reasons" :key="reason">{{ reason }}</li>
            </ul>
            <button
              v-if="tab !== 'review' && claim.status === 'under_review'"
              type="button"
              class="button button-primary"
              @click="changeTab('review')"
            >
              Review this claim<AppIcon name="arrow" :size="16" />
            </button>
          </div>
        </div>
        <div v-if="tab === 'review' && claim.status === 'under_review'" class="panel">
          <div class="panel-body">
            <div class="section-heading"><h2>Your decision</h2></div>
            <ReviewActionBar :claim-id="id" @decided="decided" @saved="saved" />
          </div>
        </div>
        <div v-else-if="tab === 'review' && claim.status !== 'under_review'" class="help-card">
          <h3>{{ finalDecision ? 'Decision recorded' : 'Review is not available yet' }}</h3>
          <p>
            {{
              finalDecision
                ? 'The final outcome and reviewer notes are retained in the report and timeline.'
                : 'A claim must finish assessment and pause for review before a decision can be submitted.'
            }}
          </p>
        </div>
        <ClaimTimeline :events="store.timeline" />
      </div>
    </div>
  </template>
</template>
