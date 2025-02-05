<template>
  <div class="chek-validator">
    <v-container v-if="backendUrl">
      <v-row>
        <v-col>
          <v-card title="Validation data">
            <v-card-text>
              <v-form @submit.prevent="execute" v-model="formValid" ref="formRef">
                <v-autocomplete
                  label="Select a profile for validation"
                  v-model="profileModel"
                  :items="profiles"
                  return-object
                  :messages="profileModel?.description || []"
                  :custom-filter="profileFilter"
                >
                  <template #item="{ props, item }">
                    <v-list-item
                      v-bind="props"
                      :subtitle="item.raw.description || ''"
                    >
                      <template #title>
                        <span v-if="item.title" class="mr-3">
                          {{ item.title }}
                        </span>
                        <code :class="{ 'text-caption': !!item.title }">{{ item.raw.id }}</code>
                      </template>
                    </v-list-item>
                  </template>
                  <template #selection="{ item }">
                    <span v-if="item.title" class="mr-2">
                      {{ item.title }}
                    </span>
                    <code>{{ item.raw.id }}</code>
                  </template>
                </v-autocomplete>
                <div v-if="profileReady">
                  <v-file-input
                    v-for="(cityFile, idx) of cityFiles"
                    label="File to validate"
                    :key="cityFile.id"
                    :clearable="false"
                    @change="fileSelected(cityFile, idx, $event)"
                    :rules="!idx ? [rules.fileRequired] : []"
                    :error-messages="cityFile.errors"
                  >
                    <template #append>
                      <v-btn
                        v-if="idx > 0 && cityFile.file"
                        @click="deleteFile(idx)"
                        size="small"
                      >
                        <v-icon icon="mdi-delete"></v-icon>
                      </v-btn>
                    </template>
                  </v-file-input>
                  <h3 v-if="profileFields.length">Parameters</h3>
                  <template
                    v-for="(field, idx) of profileFields"
                    :key="`${profile.id}::${field.name}`"
                  >
                    <v-checkbox
                      v-if="field.type === 'boolean'"
                      :label="field.label"
                      v-model="field.value"
                      :messages="field?.description || ''"
                    >
                    </v-checkbox>
                    <v-text-field
                      v-else
                      :label="field.name"
                      v-model="field.value"
                      :messages="field?.description || ''"
                      :rules="field.required ? [rules.required] : []"
                      :class="{required: field.required}"
                      validate-on="input"
                      class="process-input"
                    >
                    </v-text-field>
                  </template>
                  <div class="mt-4">
                    <v-btn :loading="results.loading" type="submit" color="primary" prepend-icon="mdi-play">Validate</v-btn>
                    <v-btn v-if="results.loading" @click.prevent="resetResults" color="secondary" class="ml-2">Cancel</v-btn>
                  </div>
                </div>
              </v-form>
            </v-card-text>
          </v-card>
        </v-col>
      </v-row>
      <v-row>
        <v-col>
          <v-card v-if="showResults" class="results" title="Validation results" :loading="results.loading">
            <v-card-text>
              <div class="card-body">
                <div class="my-2">
                  <v-alert type="success" v-if="validationSuccess">Validation was successful!</v-alert>
                  <v-alert type="warning" v-if="validationErrors">Validation errors were encountered.</v-alert>
                  <!-- validation errors table -->
                  <v-alert v-if="results.error" type="error">
                    An error was encountered while attempting validation ({{ resultsError }}).

                  </v-alert>
                </div>
                <v-expansion-panels v-if="resultsReady">
                  <v-expansion-panel
                    title="Full JSON report"
                  >
                    <v-expansion-panel-text>
                      <div class="text-end">
                        <copy-to-clipboard-button :text="results.content"></copy-to-clipboard-button>
                      </div>
                      <pre class="border rounded-1 pa-1 my-1 overflow-scroll" style="font-size: 90%; max-height: 400px"><code>{{ resultText }}</code></pre>
                    </v-expansion-panel-text>
                  </v-expansion-panel>
                </v-expansion-panels>
              </div>
            </v-card-text>
          </v-card>
        </v-col>
      </v-row>
    </v-container>
  </div>
</template>
<script>
import CopyToClipboardButton from "@/components/CopyToClipboardButton.vue";

const CHECK_RESULTS_TIME_MS = 1000;
const CHEK_DOCUMENT_URI = 'urn:chek:vocab/document';
const RESERVED_PROCESS_IDS = [
  '_semanticUplift',
  '_ruleTemplate',
];

let cityFileId = 0;

const jsonldToString = (node) => {
  if (typeof node === 'object') {
    if (node['@id']) {
      return node['@id'];
    }
    if (node['@value']) {
      return node['@value'];
    }
    return JSON.stringify(node);
  }
  if (Array.isArray(node)) {
    return JSON.stringify(node);
  }
  return node;
};

export default {
  components: {
    CopyToClipboardButton,
  },
  props: {
    backendUrl: String,
  },
  data() {
    return {
      backend: {
        loading: false,
        error: false,
      },
      profileModel: null,
      cityFiles: [{
        id: ++cityFileId,
        file: null,
        errors: [],
      }],
      profiles: [],
      profile: {
        id: null,
        loading: false,
        data: null,
        error: false,
      },
      profileCache: {},
      results: {
        loading: false,
        status: null,
        jobId: null,
        error: false,
        content: null,
        timeout: null,
      },
      profileFields: [],
      formValid: false,
      rules: {
        required: value => !!value || 'This field is required',
        fileRequired: value => (!!value && !!value.length) || 'At least one file is required',
      },
    };
  },
  methods: {
    reset() {
      this.backend.loading = false;
      this.backend.error = false;
      this.profile.id = null;
      this.profileCache = {};
      this.cityFiles = [{
        id: ++cityFileId,
        file: null,
        errors: [],
      }];
    },
    async loadBackend() {
      this.reset();
      if (!this.backendUrl) {
        return;
      }
      this.backend.loading = true;
      try {
        let response = await fetch(new URL('processes', this.backendUrl), {
          headers: {'Accept': 'application/json'},
        });
        let data = await response.json();
        this.profiles = data.processes.filter(p => !RESERVED_PROCESS_IDS.includes(p.id));
      } catch (e) {
        console.error('Error fetching backend data', e);
        this.backend.error = true;
      } finally {
        this.backend.loading = false;
      }
    },
    async execute() {
      const formValidation = await this.$refs.formRef.validate();
      if (!formValidation.valid) {
        return;
      }
      this.results.error = false;
      let fileErrors = false;
      const cityFiles = await Promise.all(
        this.cityFiles.filter(c => !!c.file).map(async (c, idx) => {
          try {
            const data_str = await c.file.text();
            c.errors = [];
            return {
              name: c.file.name || `file-${idx}`,
              data_str,
            }
          } catch (e) {
            c.errors = ['The file could not be loaded'];
            fileErrors = true;
          }
        })
      );
      if (fileErrors) {
        return;
      }
      const requestData = {
        inputs: {
          cityFiles,
        },
      };
      for (const field of this.profileFields) {
        requestData.inputs[field.name] = field.value;
      }

      this.results.loading = true;
      try {
        let response = await fetch(new URL(`processes/${this.profile.id}/execution`, this.backendUrl), {
          method: 'POST',
          headers: {
            'Accept': 'application/json',
            'Content-Type': 'application/json',
          },
          body: JSON.stringify(requestData),
        });
        if (!response.ok) {
          throw new Error(`${response.status} - ${response.statusText}`);
        }
        let data = await response.json();

        this.profile.jobId = data.jobID;

        this.results.status = data.status;
        if (['accepted', 'running'].includes(data.status)) {
          // polling
          setTimeout(this.checkJobStatus, CHECK_RESULTS_TIME_MS);
        } else if (data.status === 'successful') {
          // fetch results
          this.fetchResults();
        } else {
          throw new Error(`Job submission failed with status ${data.status}`);
        }

      } catch (e) {
        console.error(`Error executing process ${this.profile.id}`, requestData, e);
        this.results.error = typeof e === 'string' ? e : (e.message || true);
        this.results.loading = false;
      }
    },
    resetResults() {
      this.results.loading = false;
      this.results.error = false;
      clearTimeout(this.results.timeout);
      this.results.timeout = null;
      this.results.content = null;
    },
    async fileSelected(cityFile, idx, ev) {
      const [file] = ev.target.files;
      cityFile.file = file;
      if (!this.cityFiles.some(c => !c.file)) {
        this.cityFiles.push({id: ++cityFileId, file: null});
      }
    },
    async deleteFile(idx) {
      this.cityFiles.splice(idx, 1)
      if (!this.cityFiles.some(c => !c.file)) {
        this.cityFiles.push({id: ++cityFileId, file: null});
      }
    },
    async checkJobStatus() {
      try {
        let response = await fetch(new URL(`jobs/${this.profile.jobId}`, this.backendUrl), {
          headers: {
            'Accept': 'application/json',
          }
        });
        if (!response.ok) {
          throw new Error(`${response.status} - ${response.statusText}`);
        }
        let data = await response.json();
        if (['accepted', 'running'].includes(data.status)) {
          setTimeout(this.checkJobStatus, CHECK_RESULTS_TIME_MS);
        } else {
          if (data.status !== 'successful') {
            this.results.error = `Job failed with status ${data.status}`;
          }
          await this.fetchResults();
        }
      } catch (e) {
        console.error(`Error checking status for job ${this.profile.jobId}`, e);
        this.results.error = typeof e === 'string' ? e : (e.message || true);
        this.results.loading = false;
      }
    },
    async fetchResults() {
      try {
        let response = await fetch(new URL(`jobs/${this.profile.jobId}/results`, this.backendUrl), {
          headers: {
            'Accept': 'application/json',
          }
        });
        if (!response.ok) {
          throw new Error(`${response.status} - ${response.statusText}`);
        }
        this.results.loading = false;
        this.results.content = await response.json();
      } catch (e) {
        console.error(`Error obtaining results for job ${this.profile.jobId}`, e);
        if (!this.results.error) {
          this.results.error = typeof e === 'string' ? e : (e.message || true);
        }
      }
    },
    profileFilter(title, query, item) {
      const itemTitle = item.raw.title.toLowerCase();
      const itemId = item.raw.id.toLowerCase();
      const q = query.toLowerCase();
      return itemTitle.indexOf(q) > -1 || itemId.indexOf(q) > -1;
    },
  },
  computed: {
    backendReady() {
      return !this.backend.error && this.backendUrl;
    },
    profileReady() {
      return this.backendReady && !this.profile.error && this.profile.id;
    },
    showResults() {
      return this.results.loading || this.results.error || this.results.content;
    },
    resultsReady() {
      return !this.results.loading && this.results.content;
    },
    validationSuccess() {
      return (this.resultsReady && this.results.content?.valid) || false;
    },
    validationErrors() {
      return this.resultsReady && !this.results.error && !this.results.content.valid;
    },
    resultText() {
      return JSON.stringify(this.results?.content, null, 2);
    },
    resultsError() {
      if (!this.results.error) {
        return '';
      }
      let error = '';
      if (typeof this.results.error === 'string') {
        error = this.results.error;
      }
      if (Array.isArray(this.results.content?.errors)
        && this.results.content.errors.length > 0
        && typeof this.results.content.errors[0] === 'string') {
        if (error.length > 0) {
          error += ': ';
        }
        error += this.results.content.errors[0];
      }
      return error;
    },
    extractedErrors() {
      if (!this.results.content) {
        return [];
      }
      const result = [];
      const shaclReport = this.results.content.shaclReport;
      const val3dityReports = this.results.content.fileValidation;

      if (shaclReport.result?.length) {
        for (const failedShape of shaclReport.result) {
          let msg = `${failedShape.resultMessage} (${jsonldToString(failedShape.sourceShape)}`;
          if (failedShape.focusNode !== CHEK_DOCUMENT_URI) {
            msg += `for ${jsonldToString(failedShape.focusNode)}`;
          }
          msg += failedShape.value !== CHEK_DOCUMENT_URI ? `, value ${jsonldToString(failedShape.value)})` : ')';

          result.push({
            type: 'SHACL',
            message: msg,
          })
        }
      }

      if (!this.results.content.val3dityResult) {
        for (const fileEntry of val3dityReports) {
          const featuresOverview = fileEntry?.val3dityReport?.features_overview;
          if (featuresOverview?.length) {
            for (const fo of featuresOverview) {
              if (fo.total > fo.valid) {
                let msg = `${fileEntry.name}: Errors found in ${fo.total - fo.valid} features of type ${fo.type}`;
                result.push({
                  type: 'val3dity',
                  message: msg,
                });
              }
            }
          }
        }
      }

      return result;
    }
  },
  watch: {
    backendUrl: {
      immediate: true,
      handler(v) {
        this.loadBackend();
      },
    },
    async profileModel(profile) {
      const profileId = profile.id;
      this.profile.error = false;

      if (this.profileCache[profileId]) {
        this.profile.id = profileId;
        this.profile.data = this.profileCache[profileId];
        return;
      }

      this.profile.loading = true;
      try {
        let response = await fetch(new URL(`processes/${profileId}`, this.backendUrl), {
          headers: {'Accept': 'application/json'},
        });
        const profileData = await response.json();
        this.profile.id = profileId;
        this.profile.data = profileData;
        this.profileCache[profileId] = profileData;
      } catch (e) {
        console.error(`Error loading profile ${profileId}`, e);
        this.profile.error = true;
      } finally {
        this.profile.loading = false;
      }
    },
    'profile.id'() {
      this.profileFields = [];
      if (this.profile?.id && this.profile.data.inputs) {
        for (const e of Object.entries(this.profile.data.inputs)) {
          if (e[0] !== 'cityFiles') {
            this.profileFields.push({
              name: e[0],
              description: e[1].description || e[0],
              required: e[1]?.minOccurs > 0,
              type: e[1]?.schema?.type || 'string',
              value: '',
            });
          }
        }
      }
    },
  },
}
</script>
<style>
.process-input.required .v-label:after {
  color: red;
  content: '*';
  margin-left: 0.2em;
}
</style>