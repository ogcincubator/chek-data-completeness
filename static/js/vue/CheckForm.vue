<template>
  <div class="container">
    <h1 class="text-center">CHEK data completeness validator</h1>
    <div class="backend mb-3 card">
      <div class="card-header">Backend service</div>
      <div class="card-body">
        <fieldset :disabled="backend.loading">
          <label for="backend-service">Service URL</label>
          <div class="input-group mb-3">
            <input class="form-control" v-model="backendUrlModel" :disabled="backendReady">
            <button v-if="backendReady" @click="reset" class="btn btn-primary border-right" type="button">
              Edit
            </button>
            <button @click.prevent="loadBackend" class="btn btn-primary" type="button">
              <span v-if="backend.loading" class="spinner-border text-black" style="width: 1rem; height: 1rem;" role="status">
                <span class="visually-hidden">Loading...</span>
              </span>
              <span v-else-if="backendReady">Reload</span>
              <span v-else>Load</span>
            </button>
          </div>
        </fieldset>
        <div v-if="backend.error" class="alert alert-danger d-none" role="alert">
          Error retrieving data from server. Please check that the URL is correct.
        </div>
      </div>
    </div>
    <div v-if="backendReady" class="validation-form mb-3 card">
      <div class="card-header">Validation data</div>
      <div class="card-body">
        <form @submit.prevent="execute">
          <fieldset :disabled="profile.loading || results.loading">
            <div class="mb-3">
              <label for="profile" class="form-label">Select a profile for validation</label>
              <select class="form-select" v-model="profileModel">
                <option v-for="profile of profiles" :key="profile.id" :value="profile.id">{{ profile.id }}</option>
              </select>
            </div>
            <div v-if="profileReady">
              <div class="mb-3" v-for="(cityFile, idx) of cityFiles" :key="cityFile.id">
                <label :for="`file-${cityFile.id}`" class="form-label">File to validate</label>
                <div class="input-group">
                  <input @change="fileSelected(cityFile, idx, $event)" class="form-control" type="file" :id="`file-${cityFile.id}`">
                  <button v-if="idx > 0 && cityFile.file" @click="deleteFile(idx)" class="btn btn-primary" type="button">
                    Remove
                  </button>
                </div>
              </div>
              <h3 v-if="profileFields.length">Parameters</h3>
              <div v-for="(field, idx) of profileFields" :key="idx" class="mb-3 process-input " :class="{required: field.required}">
                <label :for="`input-field-${idx}`">{{ field.name }}</label>
                <input class="form-control" :type="field.type" :id="`input-field-${idx}`" v-model="field.value"
                       :required="field.required"/>
                <div v-if="field.description" class="form-text">{{ field.description }}</div>
              </div>
            </div>
          </fieldset>
          <button v-if="profileReady" type="submit" class="btn btn-primary" :disabled="results.loading">Validate</button>
          <button v-if="results.loading" @click.prevent="resetResults" class="btn btn-secondary ms-2">Cancel</button>
        </form>
      </div>
    </div>
    <div v-if="showResults" class="results mb-3 card">
      <div class="card-header">Validation results</div>
      <div class="card-body">
        <div v-if="results.loading">
          <div class="alert alert-info" role="alert">
            Validation is running
            <div class="spinner-border text-primary" style="width: 1rem; height: 1rem;" role="status">
              <span class="visually-hidden">Loading...</span>
            </div>
          </div>
        </div>
        <div v-if="validationSuccess" class="alert alert-success" role="alert">
          Validation was successful!
        </div>
        <div v-if="validationErrors" class="alert alert-warning" role="alert">
          Validation errors were encountered
        </div>
        <div v-if="results.error" class="alert alert-danger" role="alert">
          An error was encountered while attempting validation<span v-if="typeof results.error === 'string'"> ({{ results.error }})</span>.
        </div>
        <div v-if="resultsReady">
          <div class="text-end">
            <button @click.prevent="copyResultsToClipboard" class="btn btn-primary">Copy to clipboard</button>
          </div>
          <pre class="border rounded-1 p-1 my-1" style="font-size: 90%; max-height: 400px"><code>{{ results.content }}</code></pre>
        </div>
      </div>
    </div>
  </div>
</template>
<script>
const CHECK_RESULTS_TIME_MS = 1000;

let cityFileId = 0;

export default {
  props: {
    baseUrl: String,
  },
  data() {
    return {
      backendUrlModel: this.baseUrl,
      profileModel: null,
      cityFiles: [{
        id: ++cityFileId,
        file: null,
      }],
      backend: {
        loading: false,
        error: false,
        url: false,
      },
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
    };
  },
  methods: {
    reset() {
      this.backend.error = false;
      this.backend.url = null;
      this.profile.id = null;
      this.profileCache = {};
      this.cityFiles = [{
        id: ++cityFileId,
        file: null,
      }]
    },
    async loadBackend() {
      this.reset();
      this.backend.loading = true;
      try {
        let response = await fetch(this.backendUrlModel, {
          headers: {'Accept': 'application/json'},
        });
        let data = await response.json();
        if (!data.links?.some(link => link.rel === 'http://www.opengis.net/def/rel/ogc/1.0/processes')) {
          throw new Error(`No OGC API processes service found at ${url}`);
        }

        response = await fetch(new URL('processes', this.baseUrl), {
          headers: {'Accept': 'application/json'},
        });
        data = await response.json();
        this.profiles = data.processes;
        this.backend.url = this.backendUrlModel;
        if (!this.backend.url.endsWith('/')) {
          this.backend.url += '/';
        }

      } catch (e) {
        console.error('Error fetching backend data', e);
        this.backend.error = true;
      } finally {
        this.backend.loading = false;
      }
    },
    async execute() {
      this.results.error = false;
      const cityFiles = await Promise.all(
          this.cityFiles.filter(c => !!c.file).map(async (c, idx) => ({
            name: `file-${idx}`,
            data_str: await c.file.text(),
          }))
      );
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
        let response = await fetch(new URL(`processes/${this.profile.id}/execution`, this.backend.url), {
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
        this.cityFiles.push({ id: ++cityFileId, file: null });
      }
    },
    async deleteFile(idx) {
      this.cityFiles.splice(idx, 1)
      if (!this.cityFiles.some(c => !c.file)) {
        this.cityFiles.push({ id: ++cityFileId, file: null });
      }
    },
    async checkJobStatus() {
      try {
        let response = await fetch(new URL(`jobs/${this.profile.jobId}`, this.backend.url), {
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
        let response = await fetch(new URL(`jobs/${this.profile.jobId}/results`, this.backend.url), {
          headers: {
            'Accept': 'application/json',
          }
        });
        if (!response.ok) {
          throw new Error(`${response.status} - ${response.statusText}`);
        }
        this.results.loading = false;
        this.results.content = JSON.stringify(await response.json(), null, 2);
      } catch (e) {
        console.error(`Error obtaining results for job ${this.profile.jobId}`, e);
        if (!this.results.error) {
          this.results.error = typeof e === 'string' ? e : (e.message || true);
        }
      }
    },
    copyResultsToClipboard() {
      if (this.results.content) {
        navigator.clipboard.writeText(this.results.content);
      }
    },
  },
  computed: {
    backendReady() {
      return !this.backend.error && this.backend.url;
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
    profileFields() {
      if (!this.profile.id || !this.profile.data.inputs) {
        return [];
      }
      const inputs = [];
      for (const e of Object.entries(this.profile.data.inputs)) {
        if (e[0] !== 'cityFiles') {
          inputs.push({
            name: e[0],
            description: e[1].description || e[0],
            required: e[1]?.minOccurs > 0,
            type: e[1]?.schema?.type || 'string',
            value: '',
          });
        }
      }
      return inputs;
    },
    validationSuccess() {
      return (this.resultsReady && this.results.content?.valid) || false;
    },
    validationErrors() {
      return this.resultsReady && !this.results.error && !this.results.content.valid;
    },
  },
  watch: {
    async profileModel(profileId) {
      this.profile.error = false;

      if (this.profileCache[profileId]) {
        this.profile.id = profileId;
        this.profile.data = this.profileCache[profileId];
        return;
      }

      this.profile.loading = true;
      try {
        let response = await fetch(new URL(`processes/${profileId}`, this.backend.url), {
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
  },
}
</script>
<style>
.process-input.required label:after {
  color: red;
  content: '*';
  margin-left: 0.2em;
}
</style>