<script setup>
import { ref, defineProps, computed } from 'vue';
import CopyToClipboardButton from "@/components/CopyToClipboardButton.vue";

const props = defineProps({
  backendUrl: String,
});
const backendUrl = ref(props.backendUrl);

const cityFile = ref();
const loading = ref(false);
const error = ref(false);
const jobId = ref();
const result = ref();
const timeoutRef = ref();

const CHECK_RESULTS_TIME_MS = 500;

const uplift = async () => {
  error.value = false;
  if (!cityFile.value) {
    return;
  }
  loading.value = true;
  const requestCityFile = {};
  try {
    requestCityFile.name = cityFile.value.name || 'CityFile';
    requestCityFile.data_str = await cityFile.value.text();
  } catch (e) {
    console.error('Error loading file', e);
    error.value = 'Local file could not be loaded';
    loading.value = false;
    return;
  }

  const requestData = {
    inputs: {
      cityFiles: [requestCityFile],
    }
  };
  let response = await fetch(new URL('processes/_semanticUplift/execution', backendUrl.value), {
    method: 'POST',
    headers: {
      'Accept': 'application/json',
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(requestData),
  });
  if (!response.ok) {
    error.value = `${response.status} - ${response.statusText}`;
    return;
  }
  let data = await response.json();
  jobId.value = data.jobID;
  if (['accepted', 'running'].includes(data.status)) {
    // polling
    timeoutRef.value = setTimeout(checkJobStatus, CHECK_RESULTS_TIME_MS);
  } else {
    if (data.status !== 'successful') {
      error.value = `Job submission failed with status ${data.status}`;
    }
    fetchResults();
  }
};

const checkJobStatus = async () => {
  try {
    let response = await fetch(new URL(`jobs/${jobId.value}`, backendUrl.value), {
      headers: {
        'Accept': 'application/json',
      }
    });
    if (!response.ok) {
      throw new Error(`${response.status} - ${response.statusText}`);
    }
    let data = await response.json();
    if (['accepted', 'running'].includes(data.status)) {
      timeoutRef.value = setTimeout(checkJobStatus, CHECK_RESULTS_TIME_MS);
    } else {
      if (data.status !== 'successful') {
        error.value = `Job failed with status ${data.status}`;
      }
      await fetchResults();
    }
  } catch (e) {
    console.error(`Error checking status for job ${jobId.value}`, e);
    error.value = typeof e === 'string' ? e : (e.message || true);
    loading.value = false;
  }
};

const fetchResults = async () => {
  loading.value = true;
  try {
    let response = await fetch(new URL(`jobs/${jobId.value}/results`, backendUrl.value), {
      headers: {
        'Accept': 'application/json',
      }
    });
    if (!response.ok) {
      throw new Error(`${response.status} - ${response.statusText}`);
    }
    result.value = await response.json();
  } catch (e) {
    console.error(`Error obtaining results for job ${jobId.value}`, e);
    if (!error.value) {
      error.value = typeof e === 'string' ? e : (e.message || true);
    }
  } finally {
    loading.value = false;
  }
};

const resultText = computed(() => result.value?.data);
const saveResults = () => {
  if (resultText.value) {
    const blob = new Blob([resultText.value], { type: 'text/turtle' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'uplift-results.ttl';
    a.click();
    URL.revokeObjectURL(url);
    a.remove();
  }
}

const cancel = () => {
  clearTimeout(timeoutRef.value);
  loading.value = false;
};

const errorMessage = computed(() => result.value?.errors[0] || error.value);

</script>
<template>
  <div class="chek-uplift">
    <v-file-input
      label="City file to uplift"
      v-model="cityFile"
      :loading="loading"
      :clearable="false"
    >
      <template #append-inner>
        <v-icon v-if="loading" @click.stop="cancel">mdi-stop</v-icon>
        <v-icon v-if="!!cityFile && !loading" @click.stop="uplift">mdi-play-box</v-icon>
      </template>
    </v-file-input>
    <v-alert v-if="!loading && error" type="error">Error uplifting file: {{ errorMessage }}</v-alert>
    <div class="results" v-if="!loading && resultText">
      <div class="text-end">
        <copy-to-clipboard-button :text="resultText"></copy-to-clipboard-button>
        <v-btn class="ml-2" @click.prevent="saveResults" prepend-icon="mdi-content-save" color="primary">
          Save to file
        </v-btn>
      </div>
      <pre class="border rounded-1 pa-1 my-1 overflow-scroll" style="font-size: 90%; max-height: 400px"><code>{{ resultText }}</code></pre>
    </div>
  </div>
</template>