<script setup>
import { onMounted, ref } from 'vue'
import { onBeforeRouteLeave, useRouter } from 'vue-router'
import { api } from '../composables/useApi'
import { useClaimsStore } from '../stores/claims'
import AppIcon from '../components/AppIcon.vue'
import ErrorAlert from '../components/ErrorAlert.vue'
import FnolTextInput from '../components/claims/FnolTextInput.vue'
import ImageUploader from '../components/claims/ImageUploader.vue'
const router = useRouter()
const store = useClaimsStore()
const description = ref('')
const images = ref([])
const busy = ref(false)
const error = ref('')
const savedId = ref(null)
const limits = ref(null)
const settingsError = ref('')
async function settings() {
  settingsError.value = ''
  try {
    limits.value = await api('/claims/intake-settings')
  } catch (failure) {
    settingsError.value = failure.message
  }
}
onMounted(settings)
onBeforeRouteLeave(() => !busy.value)
async function submit() {
  if (busy.value || savedId.value || !limits.value || !description.value.trim()) return
  busy.value = true
  error.value = ''
  try {
    const result = await store.submit(description.value.trim(), images.value)
    busy.value = false
    router.push('/claims/' + result.claim_id)
  } catch (failure) {
    error.value = failure.message
    savedId.value = failure.claimId
    busy.value = false
  }
}
</script>
<template>
  <div class="page-heading">
    <div>
      <span class="eyebrow">FIRST NOTICE OF LOSS</span>
      <h1>Tell us what happened.</h1>
      <p>An incident narrative and evidence are all you need to get started.</p>
    </div>
    <RouterLink to="/claims" class="button button-ghost"
      ><AppIcon name="back" :size="16" />Back to claims</RouterLink
    >
  </div>
  <ErrorAlert :message="settingsError" retry @retry="settings" /><ErrorAlert :message="error" />
  <div v-if="savedId" class="alert alert-info" role="status">
    <AppIcon name="file" /><span
      >Your claim was saved. Open it to resume processing when the service is available.<br /><RouterLink
        :to="'/claims/' + savedId"
        class="text-link"
        >Open saved claim<AppIcon name="arrow" :size="14" /></RouterLink
    ></span>
  </div>
  <div v-if="!limits && !settingsError" class="loading-state" role="status">
    <AppIcon name="loader" class="spin" />Preparing submission…
  </div>
  <div v-if="limits" class="form-grid">
    <form class="panel" @submit.prevent="submit">
      <div class="form-section">
        <div class="step-heading">
          <span class="step-number">1</span>
          <h2>The incident</h2>
        </div>
        <FnolTextInput
          v-model="description"
          :max-length="limits.max_text_length"
          :disabled="busy || !!savedId"
        />
      </div>
      <div class="form-section">
        <div class="step-heading">
          <span class="step-number">2</span>
          <h2>Supporting evidence <span class="muted text-small">(optional)</span></h2>
        </div>
        <p class="text-small muted">
          Photos, scanned notes, and receipts can help clarify your report.
        </p>
        <ImageUploader
          v-model="images"
          :max-count="limits.max_images"
          :max-mb="limits.max_upload_size_mb"
          :disabled="busy || !!savedId"
        />
      </div>
      <div class="form-actions">
        <p>
          {{
            busy
              ? 'Reading your submission. Keep this workspace open until your claim is saved.'
              : 'Your submission will be assessed against the policy terms. Uncertain cases go to a reviewer.'
          }}
        </p>
        <button
          type="submit"
          class="button button-primary"
          :disabled="busy || !!savedId || !description.trim()"
        >
          <AppIcon :name="busy ? 'loader' : 'arrow'" :size="17" :class="{ spin: busy }" />{{
            busy ? 'Submitting claim…' : 'Submit claim'
          }}
        </button>
      </div>
    </form>
    <div class="stack">
      <div class="help-card">
        <AppIcon name="file" :size="25" style="margin-bottom: 18px; color: #769b61" />
        <h3>A little context<br />goes a long way.</h3>
        <p>Include these details when you have them:</p>
        <ul>
          <li>Claimant name and policy number</li>
          <li>Date and description of the incident</li>
          <li>Any injury, treatment, or provider details</li>
          <li>Estimated amount, if known</li>
        </ul>
      </div>
      <div class="help-card">
        <h3>What happens next?</h3>
        <p>
          Your report is organized, checked against policy evidence, and assessed for uncertainty.
          You can follow its progress in the claim workspace.
        </p>
      </div>
    </div>
  </div>
</template>
