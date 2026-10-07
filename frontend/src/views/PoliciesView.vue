<script setup>
import { ref } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import { api } from '../composables/useApi'
import { dateTime, usePolling } from '../composables/useClaims'
import AppIcon from '../components/AppIcon.vue'
import StatusBadge from '../components/StatusBadge.vue'
import ErrorAlert from '../components/ErrorAlert.vue'
import EmptyState from '../components/EmptyState.vue'
import PaginationBar from '../components/PaginationBar.vue'
const items = ref([])
const total = ref(0)
const offset = ref(0)
const search = ref('')
const appliedSearch = ref('')
const error = ref('')
const notice = ref('')
const loading = ref(false)
const busy = ref(false)
const uploading = ref(null)
const showForm = ref(false)
const maxMb = ref(null)
const limit = 20
const fresh = () => ({
  policy_number: '',
  holder_name: '',
  plan_type: 'PPO',
  effective_date: '',
  expiration_date: '',
  status: 'active',
})
const form = ref(fresh())
let serial = 0
async function load(signal) {
  const token = ++serial
  loading.value = true
  try {
    const [data, settings] = await Promise.all([
      api('/policies', {
        query: { search: appliedSearch.value, offset: offset.value, limit },
        signal,
      }),
      api('/claims/intake-settings', { signal }),
    ])
    if (token === serial) {
      items.value = data.items
      total.value = data.total
      maxMb.value = settings.max_upload_size_mb
      error.value = ''
    }
  } catch (failure) {
    if (token === serial && !signal?.aborted) error.value = failure.message
  } finally {
    if (token === serial) loading.value = false
  }
}
const { refresh } = usePolling(load, {
  interval: 20000,
  enabled: () => !uploading.value && !busy.value,
})
onBeforeRouteLeave(() => !busy.value && !uploading.value)
function filter() {
  appliedSearch.value = search.value.trim()
  offset.value = 0
  refresh()
}
function page(value) {
  offset.value = value
  refresh()
}
async function create() {
  if (busy.value || uploading.value) return
  busy.value = true
  error.value = ''
  notice.value = ''
  try {
    const created = await api('/policies', { method: 'POST', body: form.value })
    showForm.value = false
    form.value = fresh()
    search.value = created.policy_number
    appliedSearch.value = created.policy_number
    offset.value = 0
    notice.value = 'Policy metadata saved. Upload a PDF to make its terms available for assessment.'
    await refresh()
  } catch (failure) {
    error.value = failure.message
  } finally {
    busy.value = false
  }
}
async function upload(policy, event) {
  const file = event.target.files?.[0]
  event.target.value = ''
  if (!file || uploading.value || busy.value || !maxMb.value) return
  error.value = ''
  notice.value = ''
  if (!file.name.toLowerCase().endsWith('.pdf') || !file.size) {
    error.value = 'Choose a nonempty PDF policy document.'
    return
  }
  if (file.size > maxMb.value * 1024 * 1024) {
    error.value = 'The PDF must be smaller than ' + maxMb.value + ' MB.'
    return
  }
  const body = new FormData()
  body.append('file', file)
  uploading.value = policy.id
  try {
    const result = await api('/policies/' + policy.id + '/upload', {
      method: 'POST',
      body,
      timeout: 1800000,
    })
    notice.value =
      policy.policy_number +
      ' is ready for assessment. ' +
      result.page_count +
      ' pages parsed; ' +
      result.chunk_count +
      ' passages indexed.'
    await refresh()
  } catch (failure) {
    await load()
    error.value = failure.message
  } finally {
    uploading.value = null
  }
}
</script>
<template>
  <div class="page-heading">
    <div>
      <span class="eyebrow">POLICY REPOSITORY</span>
      <h1>The terms behind the decision.</h1>
      <p>Create policy records and turn their PDFs into searchable coverage evidence.</p>
    </div>
    <button
      type="button"
      class="button button-primary"
      :disabled="!!uploading || busy"
      @click="showForm = !showForm"
    >
      <AppIcon :name="showForm ? 'close' : 'plus'" :size="17" />{{
        showForm ? 'Close form' : 'Add policy'
      }}
    </button>
  </div>
  <ErrorAlert :message="error" retry @retry="refresh" />
  <div v-if="notice" class="alert alert-success" role="status">
    <AppIcon name="success" /><span>{{ notice }}</span>
  </div>
  <form v-if="showForm" class="panel policy-form" @submit.prevent="create">
    <div class="panel-body">
      <div class="section-heading">
        <h2>New policy record</h2>
        <span class="muted text-small">Upload the document after saving</span>
      </div>
      <div class="field-row">
        <div class="field">
          <label for="policy-number">Policy number</label
          ><input
            id="policy-number"
            v-model.trim="form.policy_number"
            required
            maxlength="64"
            :disabled="busy"
          />
        </div>
        <div class="field">
          <label for="policy-holder">Policyholder</label
          ><input
            id="policy-holder"
            v-model.trim="form.holder_name"
            required
            maxlength="255"
            :disabled="busy"
          />
        </div>
      </div>
      <div class="field-row">
        <div class="field">
          <label for="plan-type">Plan type</label
          ><input
            id="plan-type"
            v-model.trim="form.plan_type"
            required
            maxlength="64"
            list="plan-types"
            :disabled="busy"
          /><datalist id="plan-types">
            <option value="HMO" />
            <option value="PPO" />
            <option value="EPO" />
          </datalist>
        </div>
        <div class="field">
          <label for="policy-status">Status</label
          ><select id="policy-status" v-model="form.status" :disabled="busy">
            <option value="active">Active</option>
            <option value="inactive">Inactive</option>
            <option value="expired">Expired</option>
          </select>
        </div>
      </div>
      <div class="field-row">
        <div class="field">
          <label for="effective-date">Effective date</label
          ><input
            id="effective-date"
            v-model="form.effective_date"
            type="date"
            required
            :max="form.expiration_date || undefined"
            :disabled="busy"
          />
        </div>
        <div class="field">
          <label for="expiration-date">Expiration date</label
          ><input
            id="expiration-date"
            v-model="form.expiration_date"
            type="date"
            required
            :min="form.effective_date || undefined"
            :disabled="busy"
          />
        </div>
      </div>
      <button type="submit" class="button button-primary" :disabled="busy">
        <AppIcon :name="busy ? 'loader' : 'check'" :size="16" :class="{ spin: busy }" />{{
          busy ? 'Saving…' : 'Save policy'
        }}
      </button>
    </div>
  </form>
  <div v-if="uploading" class="alert alert-info" role="status">
    <AppIcon name="loader" class="spin" /><span
      >Parsing and indexing the policy. Larger documents may take several minutes. Keep this
      workspace open until it finishes.</span
    >
  </div>
  <form class="filters" @submit.prevent="filter">
    <div class="field search-field">
      <label for="policy-search">Find a policy</label
      ><input
        id="policy-search"
        v-model="search"
        maxlength="255"
        placeholder="Policy number or policyholder"
      />
    </div>
    <button type="submit" class="button button-secondary">
      <AppIcon name="search" :size="16" />Search
    </button>
  </form>
  <div class="panel">
    <div class="section-heading">
      <h2>
        Policy library <span class="muted text-small">/ {{ total }}</span>
      </h2>
      <span class="muted text-small">PDF · {{ maxMb || '—' }} MB maximum</span>
    </div>
    <div v-if="loading && !items.length" class="loading-state" role="status">
      <AppIcon name="loader" class="spin" />Loading policies…
    </div>
    <div v-else-if="items.length" class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Policy / holder</th>
            <th>Plan</th>
            <th>Policy period</th>
            <th>Status</th>
            <th>Document</th>
            <th>Upload PDF</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="policy in items" :key="policy.id">
            <td>
              <strong class="mono">{{ policy.policy_number }}</strong
              ><span class="table-subtitle">{{ policy.holder_name }}</span>
            </td>
            <td>{{ policy.plan_type }}</td>
            <td>
              {{ dateTime(policy.effective_date, true)
              }}<span class="table-subtitle">to {{ dateTime(policy.expiration_date, true) }}</span>
            </td>
            <td>{{ policy.status.charAt(0).toUpperCase() + policy.status.slice(1) }}</td>
            <td><StatusBadge :value="policy.indexing_status" /></td>
            <td>
              <label class="button button-small button-secondary file-button"
                ><AppIcon
                  :name="uploading === policy.id ? 'loader' : 'upload'"
                  :size="15"
                  :class="{ spin: uploading === policy.id }" />{{
                  uploading === policy.id
                    ? 'Indexing…'
                    : policy.indexing_status === 'indexed'
                      ? 'Replace PDF'
                      : 'Upload PDF'
                }}<input
                  type="file"
                  accept=".pdf,application/pdf"
                  :disabled="!!uploading || busy || !maxMb"
                  :aria-label="'Upload PDF for ' + policy.policy_number"
                  @change="upload(policy, $event)"
              /></label>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <EmptyState
      v-else-if="!error"
      title="No policies found"
      message="Add a policy record, then upload its PDF to build the reference library."
      icon="folder"
    />
    <PaginationBar
      :total="total"
      :offset="offset"
      :limit="limit"
      :disabled="loading || !!uploading || busy"
      @change="page"
    />
  </div>
</template>
