<script setup>
import { ref, defineProps } from 'vue';
import { copyToClipboard } from "@/lib/utils.mjs";

const props = defineProps({
  color: {
    type: String,
  },
  label: {
    type: String,
    default: 'Copy to clipboard',
  },
  text: {
    type: String,
  },
});

const showTooltip = ref(false);
let timeout = null;

const copy = () => {
  clearTimeout(timeout);
  copyToClipboard(props.text);
  showTooltip.value = true;
  timeout = setTimeout(() => showTooltip.value = false, 2000);
};
</script>
<template>
  <v-tooltip
    v-model="showTooltip"
    :open-on-hover="false"
    location="top"
  >
    <template #activator="slotProps">
      <v-btn v-if="props.text" v-bind="slotProps.props" :color="props.color" @click.prevent="copy">{{ props.label }}</v-btn>
    </template>

    <span class="d-flex align-baseline"><v-icon icon="mdi-check-bold" size="x-small" class="mr-1"></v-icon> Copied!</span>

  </v-tooltip>
</template>