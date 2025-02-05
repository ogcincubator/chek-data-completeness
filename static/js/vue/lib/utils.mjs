export async function copyToClipboard(text) {
  if (text) {
    await navigator.clipboard.writeText(text);
  }
}

export function debounce(func, timeout) {
  let timer;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => func.apply(this, args), timeout);
  }
}

export function ogcApiProcessExecute(baseUrl, processId, requestData, chekResultsTimeMs = 1000) {
  let timeout = null;

  const headers = {
    'Accept': 'application/json',
    'Content-Type': 'application/json',
  };

  const promise = new Promise(async (resolve, reject) => {
    const executeUrl = new URL(`processes/${processId}/execution`, baseUrl);
    let jobId = null;
    let jobError = null;

    const checkJobStatus = async () => {
      try {
        const resp = await fetch(new URL(`jobs/${jobId}`, baseUrl), {headers});
        if (!resp.ok) {
          reject(`${resp.status} - ${resp.statusText}`);
          return;
        }
        let data = await resp.json();
        if (['accepted', 'running'].includes(data.status)) {
          timeout = setTimeout(checkJobStatus, chekResultsTimeMs);
        } else {
          if (data.status !== 'successful') {
            jobError = `Job submission failed with status ${data.status}`;
          }
          await fetchResults();
        }
      } catch (e) {
        console.error(`Error checking status for job ${jobId}`, e);
        reject(typeof e === 'string' ? e : (e.message || true));
      }
    };

    const fetchResults = async () => {
      try {
        const resp = await fetch(new URL(`jobs/${jobId}/results`, baseUrl), { headers });
        if (!resp.ok) {
          reject(`${resp.status} - ${resp.statusText}`);
          return;
        }
        resolve(await resp.json());
      } catch (e) {
        console.error(`Error retrieving results for job ${jobId}`, e);
        reject(typeof e === 'string' ? e : (e.message || true));
      }
    };

    try {
      const resp = await fetch(executeUrl,
        {
          method: 'POST',
          headers,
          body: JSON.stringify(requestData),
        });
      if (!resp.ok) {
        reject(`${resp.status} - ${resp.statusText}`);
        return;
      }
      const data = await resp.json();
      jobId = data.jobID;
      if (['accepted', 'running'].includes(data.status)) {
        // polling
        timeout = setTimeout(checkJobStatus, chekResultsTimeMs);
      } else {
        if (data.status !== 'successful') {
          jobError = `Job submission failed with status ${data.status}`;
        }
        await fetchResults();
      }
    } catch (e) {
      console.error(`Error executing process with id ${processId}`, e);
      reject(typeof e === 'string' ? e : (e.message || true));
    }
  });

  promise.cancel = () => {
    clearTimeout(timeout);
  };

  return promise;
}