<script setup>
defineProps({ modelValue: String, maxLength: { type: Number, default: 20000 }, disabled: Boolean })
defineEmits(['update:modelValue'])
</script>
<template>
  <div class="field">
    <label for="fnol-description">What happened? <span class="muted">(required)</span></label>
    <textarea
      id="fnol-description"
      :value="modelValue"
      :maxlength="maxLength"
      :disabled="disabled"
      required
      rows="9"
      placeholder="Describe the incident in your own words. Include the claimant, policy number, date, and any injury or treatment details you have."
      aria-describedby="description-help"
      @input="$emit('update:modelValue', $event.target.value)"
    />
    <div id="description-help" class="field-counter">
      <span>Include known details. Leave uncertain facts out.</span
      ><span
        >{{ (modelValue || '').length.toLocaleString() }} / {{ maxLength.toLocaleString() }}</span
      >
    </div>
  </div>
</template>
