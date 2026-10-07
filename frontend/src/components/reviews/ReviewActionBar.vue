<script setup>
import { computed, ref } from 'vue'
import { useReviewsStore } from '../../stores/reviews'
import AppIcon from '../AppIcon.vue'
import ErrorAlert from '../ErrorAlert.vue'
const props = defineProps({ claimId: String })
const emit = defineEmits(['decided', 'saved'])
const store = useReviewsStore()
const reviewer = ref('')
const decision = ref('approve')
const target = ref('escalated')
const notes = ref('')
const busy = ref(false)
const accepted = ref(false)
const error = ref('')
const confirmation = ref(false)
const valid = computed(
  () => reviewer.value.trim() && (decision.value === 'approve' || notes.value.trim()),
)
function edit() {
  confirmation.value = false
  error.value = ''
}
async function submit() {
  if (busy.value || accepted.value || !valid.value) return
  if (!confirmation.value) {
    confirmation.value = true
    return
  }
  busy.value = true
  error.value = ''
  const payload = {
    reviewer_id: reviewer.value.trim(),
    decision: decision.value,
    notes: notes.value.trim() || null,
  }
  if (decision.value === 'override') payload.override_status = target.value
  try {
    const result = await store.decide(props.claimId, payload)
    accepted.value = true
    emit('decided', result)
  } catch (failure) {
    error.value = failure.message
    if (failure.claimId) {
      accepted.value = true
      emit('saved', failure)
    }
  } finally {
    busy.value = false
  }
}
</script>
<template>
  <form @submit.prevent="submit">
    <div class="field">
      <label for="reviewer-id">Reviewer identifier</label
      ><input
        id="reviewer-id"
        v-model="reviewer"
        maxlength="64"
        required
        :disabled="busy || accepted"
        placeholder="Your adjuster or reviewer ID"
        @input="edit"
      />
    </div>
    <div class="field">
      <label for="review-decision">Decision</label
      ><select id="review-decision" v-model="decision" :disabled="busy || accepted" @change="edit">
        <option value="approve">Approve claim</option>
        <option value="reject">Reject claim</option>
        <option value="override">Override outcome</option>
      </select>
    </div>
    <div v-if="decision === 'override'" class="field">
      <label for="override-target">Override outcome</label
      ><select id="override-target" v-model="target" :disabled="busy || accepted" @change="edit">
        <option value="approved">Approved</option>
        <option value="denied">Denied</option>
        <option value="escalated">Escalated</option>
      </select>
    </div>
    <div class="field">
      <label for="review-notes"
        >Decision notes
        <span class="muted">{{ decision === 'approve' ? '(optional)' : '(required)' }}</span></label
      ><textarea
        id="review-notes"
        v-model="notes"
        rows="4"
        maxlength="5000"
        :required="decision !== 'approve'"
        :disabled="busy || accepted"
        placeholder="Record the evidence behind your decision."
        @input="edit"
      />
    </div>
    <ErrorAlert :message="error" />
    <div v-if="confirmation && !accepted" class="alert" role="status">
      <AppIcon name="alert" /><span
        >Confirm
        {{
          decision === 'override'
            ? 'override to ' + target
            : decision === 'approve'
              ? 'approval'
              : 'rejection'
        }}
        of this claim. Your decision and notes will be recorded.</span
      >
    </div>
    <button
      type="submit"
      class="button"
      :class="decision === 'reject' ? 'button-danger' : 'button-primary'"
      :disabled="busy || accepted || !valid"
    >
      <AppIcon :name="busy ? 'loader' : 'check'" :class="{ spin: busy }" :size="17" />{{
        accepted
          ? 'Decision recorded'
          : busy
            ? 'Saving decision…'
            : confirmation
              ? 'Confirm decision'
              : 'Review decision'
      }}
    </button>
    <button
      v-if="confirmation && !busy && !accepted"
      type="button"
      class="button button-ghost"
      @click="confirmation = false"
    >
      Back
    </button>
  </form>
</template>
