<script setup>
import { onBeforeUnmount, ref, watch } from 'vue'
import AppIcon from '../AppIcon.vue'
import ErrorAlert from '../ErrorAlert.vue'
const props = defineProps({
  modelValue: { type: Array, default: () => [] },
  maxCount: { type: Number, default: 10 },
  maxMb: { type: Number, default: 25 },
  disabled: Boolean,
})
const emit = defineEmits(['update:modelValue'])
const dragging = ref(false)
const error = ref('')
const previews = ref([])
function release() {
  previews.value.forEach((item) => URL.revokeObjectURL(item.url))
}
watch(
  () => props.modelValue,
  (files) => {
    release()
    previews.value = files.map((file) => ({ file, url: URL.createObjectURL(file) }))
  },
  { immediate: true },
)
onBeforeUnmount(release)
function add(files) {
  dragging.value = false
  if (props.disabled) return
  error.value = ''
  const accepted = [...props.modelValue]
  for (const file of Array.from(files || [])) {
    if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type)) {
      error.value = 'Choose JPEG, PNG, or WebP images.'
      return
    }
    if (file.size === 0) {
      error.value = 'Empty files cannot be attached.'
      return
    }
    if (
      !accepted.some(
        (item) =>
          item.name === file.name &&
          item.size === file.size &&
          item.lastModified === file.lastModified,
      )
    )
      accepted.push(file)
  }
  if (accepted.length > props.maxCount) {
    error.value = 'Attach no more than ' + props.maxCount + ' images.'
    return
  }
  if (accepted.reduce((sum, file) => sum + file.size, 0) > props.maxMb * 1024 * 1024) {
    error.value = 'Keep combined attachments below ' + props.maxMb + ' MB.'
    return
  }
  emit('update:modelValue', accepted)
}
function choose(event) {
  add(event.target.files)
  event.target.value = ''
}
function remove(index) {
  emit(
    'update:modelValue',
    props.modelValue.filter((_, i) => i !== index),
  )
  error.value = ''
}
</script>
<template>
  <div>
    <div
      class="dropzone"
      :class="{ dragging }"
      @dragover.prevent="dragging = !disabled"
      @dragleave.prevent="dragging = false"
      @drop.prevent="add($event.dataTransfer.files)"
    >
      <AppIcon name="upload" :size="29" /><strong
        >Drop images here, or <span class="text-link">browse files</span></strong
      >
      <p>JPEG, PNG, WebP · {{ maxCount }} images · {{ maxMb }} MB combined</p>
      <input
        type="file"
        accept="image/jpeg,image/png,image/webp"
        multiple
        aria-label="Attach claim evidence images"
        :disabled="disabled"
        @change="choose"
      />
    </div>
    <ErrorAlert :message="error" />
    <div v-if="previews.length" class="upload-previews">
      <div v-for="(item, index) in previews" :key="item.url" class="upload-preview">
        <img :src="item.url" :alt="item.file.name" /><button
          type="button"
          class="icon-button"
          :aria-label="'Remove ' + item.file.name"
          :disabled="disabled"
          @click="remove(index)"
        >
          <AppIcon name="close" :size="13" />
        </button>
        <p>{{ item.file.name }}</p>
      </div>
    </div>
  </div>
</template>
