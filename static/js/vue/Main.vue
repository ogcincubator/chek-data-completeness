<script setup>
import {ref, reactive, computed, defineProps, onMounted} from 'vue';
import ChekValidator from 'Validator.vue';
import ChekUplift from 'Uplift.vue';
import ChekRuleGenerator from 'RuleGenerator.vue';

const props = defineProps(['baseUrl']);

const tabs = ref([
  { value: 'validator', label: 'Validator' },
  { value: 'uplift', label: 'Uplift' },
  { value: 'rule-generator', label: 'Rule generator' },
]);
const currentTab = ref(tabs.value[0].value);

const backendUrlModel = ref('');
const backend = reactive({
  loading: false,
  error: false,
  url: false,
});
const backendReady = computed(() => !backend.loading && !backend.error && !!backend.url);

const reset = () => {
  backend.error = false;
  backend.url = null;
};

const loadBackend = async () => {
  reset();
  backend.loading = true;
  try {
    let response = await fetch(backendUrlModel.value, {
      headers: {'Accept': 'application/json'},
    });
    let data = await response.json();
    if (!data.links?.some(link => link.rel === 'http://www.opengis.net/def/rel/ogc/1.0/processes')) {
      throw new Error(`No OGC API processes service found at ${backendUrlModel}`);
    }
    backend.url = backendUrlModel.value;
    if (!backend.url.endsWith('/')) {
      backend.url += '/';
    }
  } catch (e) {
    console.error('Error fetching backend data', e);
    backend.error = true;
  } finally {
    backend.loading = false;
  }
};

onMounted(() => {
  backendUrlModel.value = props.baseUrl;
  loadBackend();
});

</script>
<template>
  <v-container>
    <v-row>
      <v-col>
        <h1>CHEK Data Completeness validator</h1>
      </v-col>
    </v-row>
    <v-row>
      <v-col>
        <v-card title="Backend service">
          <v-card-text>
            <v-text-field label="Service URL" v-model="backendUrlModel" :readonly="backendReady">
              <template #append-inner>
                <v-icon v-if="backendReady" @click="reset" icon="mdi-backspace-outline" title="Reset"></v-icon>
                <v-icon class="ml-2" icon="mdi-play-box" @click="loadBackend" title="Load backend"></v-icon>
              </template>
            </v-text-field>
            <v-alert v-if="backend.error" type="error">
              Error retrieving data from server. Please check that the URL is correct.
            </v-alert>
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>
    <v-row v-if="backendReady">
      <v-col>
        <v-card>
          <v-tabs
            v-model="currentTab"
          >
            <v-tab v-for="tab of tabs" :value="tab.value">{{ tab.label }}</v-tab>
          </v-tabs>
          <v-card-text>
            <v-tabs-window v-model="currentTab">
              <v-tabs-window-item value="validator" :transition="false" :reverse-transition="false">
                <chek-validator :backend-url="backend.url"></chek-validator>
              </v-tabs-window-item>
              <v-tabs-window-item value="uplift" :transition="false" :reverse-transition="false">
                <chek-uplift :backend-url="backend.url"></chek-uplift>
              </v-tabs-window-item>
              <v-tabs-window-item value="rule-generator" :transition="false" :reverse-transition="false">
                Rule generator
                <chek-rule-generator :backend-url="backend.url"></chek-rule-generator>
              </v-tabs-window-item>
            </v-tabs-window>
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>
  </v-container>
</template>