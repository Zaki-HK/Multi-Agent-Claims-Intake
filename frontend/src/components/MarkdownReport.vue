<script setup>
import { computed } from 'vue'
import { marked } from 'marked'
import DOMPurify from 'dompurify'
import AppIcon from './AppIcon.vue'
const props = defineProps({
  source: String,
  filename: { type: String, default: 'claim-assessment' },
})
const html = computed(() =>
  DOMPurify.sanitize(marked.parse(props.source || '', { async: false, gfm: true }), {
    ALLOWED_TAGS: [
      'p',
      'br',
      'hr',
      'h1',
      'h2',
      'h3',
      'h4',
      'h5',
      'h6',
      'strong',
      'em',
      'del',
      'blockquote',
      'pre',
      'code',
      'ul',
      'ol',
      'li',
      'a',
      'table',
      'thead',
      'tbody',
      'tr',
      'th',
      'td',
    ],
    ALLOWED_ATTR: ['href', 'title'],
  }),
)
function download() {
  const url = URL.createObjectURL(
    new Blob([props.source || ''], { type: 'text/markdown;charset=utf-8' }),
  )
  const link = document.createElement('a')
  link.href = url
  link.download = props.filename.replace(/[^a-zA-Z0-9_-]/g, '_') + '.md'
  link.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
</script>
<template>
  <div>
    <div class="section-heading">
      <h2>Assessment report</h2>
      <button type="button" class="button button-small button-secondary" @click="download">
        <AppIcon name="download" :size="16" /> Download Markdown
      </button>
    </div>
    <article class="markdown-report" v-html="html" />
  </div>
</template>
