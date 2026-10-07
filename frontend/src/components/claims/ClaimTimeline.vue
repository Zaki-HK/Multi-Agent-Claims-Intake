<script setup>
import { dateTime, humanize } from '../../composables/useClaims'
import EmptyState from '../EmptyState.vue'
defineProps({ events: { type: Array, default: () => [] } })
</script>
<template>
  <div class="panel">
    <div class="section-heading">
      <h2>Claim timeline</h2>
      <span class="muted text-small">{{ events.length }} events</span>
    </div>
    <div class="panel-body">
      <ol v-if="events.length" class="timeline">
        <li v-for="event in events" :key="event.id" class="timeline-item">
          <strong
            >{{ humanize(event.event_type)
            }}<span v-if="event.agent_name" class="muted">
              · {{ humanize(event.agent_name) }}</span
            ></strong
          ><time :datetime="event.timestamp">{{ dateTime(event.timestamp) }}</time>
          <details v-if="Object.keys(event.details || {}).length">
            <summary>View event details</summary>
            <pre class="event-details">{{ JSON.stringify(event.details, null, 2) }}</pre>
          </details>
        </li>
      </ol>
      <EmptyState
        v-else
        title="No events yet"
        message="The timeline will update as this claim progresses."
        icon="clock"
      />
    </div>
  </div>
</template>
