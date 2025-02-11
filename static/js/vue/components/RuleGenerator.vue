<script setup>
import { ref, onMounted, watch, defineProps, computed } from 'vue';
import { debounce, ogcApiProcessExecute } from "@/lib/utils.mjs";
import CopyToClipboardButton from "@/components/CopyToClipboardButton.vue";

const props = defineProps({
  backendUrl: String,
});
const backendUrl = ref(props.backendUrl);

const BBLOCKS_URL = 'https://ogcincubator.github.io/chek-profiles-bblocks/build/register.json';
const TEMPLATE_TAG = 'chek-rule-template';
const loading = ref(false);
const bblocks = ref([]);
const template = ref(null);
const inputJson = ref(null);
const loadingTemplate = ref(false);
const loadingRule = ref(false);
const ruleError = ref(null);
const ruleResult = ref(null);
const compileImmediately = ref(false);

let lastProcessedInput = null;

onMounted(async () => {
  loading.value = true;
  try {
    const register = await fetch(BBLOCKS_URL);
    bblocks.value = (await register.json()).bblocks.filter(b => b?.tags?.includes(TEMPLATE_TAG));
  } finally {
    loading.value = false;
  }
});

const outputTtl = computed(() => {
  return ruleResult.value?.valid && ruleResult.value.data;
});

const ruleCompileErrors = computed(() => {
  return ruleResult.value?.errors?.[0];
});

watch(template, async () => {
  if (!template.value) {
    return;
  }
  if (!template.value.fullyLoaded) {
    loadingTemplate.value = true;
    try {
      const r = await fetch(template.value.documentation['json-full'].url);
      Object.assign(template.value, await r.json());
      template.value.fullyLoaded = true;
    } finally {
      loadingTemplate.value = false;
    }
  }
  if (!inputJson.value && template.value?.examples?.length) {
    compileImmediately.value = true;
    inputJson.value = template.value.examples[0]?.snippets?.filter(s => s.language === 'json')?.[0]?.code;
  }
});

const compileTemplate = async () => {
  if (!template.value || (lastProcessedInput === inputJson.value)) {
    return;
  }
  lastProcessedInput = inputJson.value;
  ruleError.value = null;
  ruleResult.value = null;
  if (!inputJson.value?.trim()?.length) {
    return;
  }
  try {
    JSON.parse(inputJson.value);
  } catch (e) {
    ruleError.value = 'The input JSON code is not valid';
    return;
  }

  loadingRule.value = true;
  try {
    let requestData = {
      inputs: {
        inputJson: inputJson.value,
        bblockId: template.value.itemIdentifier,
      },
    };
    ruleResult.value = await ogcApiProcessExecute(backendUrl.value, '_ruleTemplate', requestData);
  } catch (e) {
    ruleError.value = 'The input JSON code is not valid';
    console.error('ERROR!!', e);
  } finally {
    loadingRule.value = false;
  }
};

const debouncedCompileTemplate = debounce(compileTemplate, 1500);
watch([inputJson, template], () => {
  if (compileImmediately.value) {
    compileImmediately.value = false;
    compileTemplate();
  } else {
    debouncedCompileTemplate();
  }
});

</script>
<template>
  <div class="rule-generator">
    <v-select
      label="Rule template"
      v-model="template"
      :items="bblocks"
      item-title="name"
      item-value="itemIdentifier"
      return-object
    >
    </v-select>
    <v-container v-if="template">
      <v-row>
        <v-col lg="6">
          <v-textarea
            class="monospace"
            label="Input JSON"
            v-model="inputJson"
            rows="15"
          >
          </v-textarea>
        </v-col>
        <v-col lg="6">
          <div class="text-center">
            <v-progress-circular class="ma-2" v-if="loadingRule" :size="50" indeterminate></v-progress-circular>
          </div>
          <v-alert v-if="ruleError" type="error">
            {{ ruleError }}
          </v-alert>
          <v-alert v-if="ruleCompileErrors" type="error">
            Errors were encoutered while validating the rule:
            <pre style="white-space: pre-wrap">
              {{ ruleCompileErrors }}
            </pre>
          </v-alert>
          <div v-if="outputTtl">
            <v-textarea
              class="monospace"
              label="Compiled Rule"
              v-model="outputTtl"
              rows="15"
              readonly
              hide-details
            >
            </v-textarea>
            <div class="d-flex justify-end mt-1">
              <copy-to-clipboard-button :text="outputTtl"></copy-to-clipboard-button>
              <v-btn class="ml-1" @click="$emit('useInValidator', outputTtl)">Use in validator</v-btn>
            </div>
          </div>
        </v-col>
      </v-row>
    </v-container>
  </div>
</template>
<style>
.monospace textarea {
  font-family: 'Consolas', 'Noto mono', 'Courier New', Courier, monospace;
  font-size: 90%;
}
</style>