(function () {
  const CONTEXT_KEY = 'durielmedic_offline_context';
  const SUMMARY_KEY = 'durielmedic_offline_summary';
  const DEVICE_KEY = 'durielmedic_device_id';
  const LEGACY_QUEUE_KEY = 'durielmedic_offline_queue';
  const DB_VERSION = 1;
  const ACTION_ORDER = {
    patient_create: 10,
    appointment_create: 20,
    record_vitals: 30,
    add_medical_record: 40,
    admit_patient: 50,
    schedule_follow_up: 60,
    create_bill: 70,
    record_payment: 80,
  };

  let databasePromise = null;
  let csrfToken = '';

  function uuid() {
    if (window.crypto && window.crypto.randomUUID) return window.crypto.randomUUID();
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (character) => {
      const random = Math.random() * 16 | 0;
      const value = character === 'x' ? random : (random & 0x3 | 0x8);
      return value.toString(16);
    });
  }

  function getDeviceId() {
    let deviceId = localStorage.getItem(DEVICE_KEY);
    if (!deviceId) {
      deviceId = uuid();
      localStorage.setItem(DEVICE_KEY, deviceId);
    }
    return deviceId;
  }

  function getContext() {
    try {
      return JSON.parse(localStorage.getItem(CONTEXT_KEY) || 'null');
    } catch (error) {
      return null;
    }
  }

  function databaseName() {
    const context = getContext();
    if (!context) return 'durielmedic_offline_uninitialized';
    const tenantKey = `${location.host}_${context.clinic.sync_id}_${context.user.id}`.replace(/[^a-zA-Z0-9_-]/g, '_');
    return `durielmedic_${tenantKey}`;
  }

  function workerContextKey(context) {
    return `${context.clinic.sync_id}-${context.user.id}`.replace(/[^a-zA-Z0-9_-]/g, '_');
  }

  function postWorkerMessage(message) {
    if (!('serviceWorker' in navigator)) return;
    navigator.serviceWorker.ready.then((registration) => {
      const worker = registration.active || registration.waiting || registration.installing;
      if (worker) worker.postMessage(message);
    }).catch(() => {});
  }

  function openDatabase() {
    if (databasePromise) return databasePromise;
    databasePromise = new Promise((resolve, reject) => {
      const request = indexedDB.open(databaseName(), DB_VERSION);
      request.onupgradeneeded = () => {
        const database = request.result;
        if (!database.objectStoreNames.contains('records')) {
          const records = database.createObjectStore('records', { keyPath: 'key' });
          records.createIndex('type', 'type', { unique: false });
          records.createIndex('status', 'status', { unique: false });
        }
        if (!database.objectStoreNames.contains('operations')) {
          const operations = database.createObjectStore('operations', { keyPath: 'operationId' });
          operations.createIndex('status', 'status', { unique: false });
          operations.createIndex('createdAt', 'createdAt', { unique: false });
        }
        if (!database.objectStoreNames.contains('metadata')) {
          database.createObjectStore('metadata', { keyPath: 'key' });
        }
      };
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    });
    return databasePromise;
  }

  async function transaction(storeName, mode, callback) {
    const database = await openDatabase();
    return new Promise((resolve, reject) => {
      const currentTransaction = database.transaction(storeName, mode);
      const store = currentTransaction.objectStore(storeName);
      let result;
      try {
        result = callback(store);
      } catch (error) {
        reject(error);
        return;
      }
      currentTransaction.oncomplete = () => resolve(result);
      currentTransaction.onerror = () => reject(currentTransaction.error);
      currentTransaction.onabort = () => reject(currentTransaction.error);
    });
  }

  async function getAll(storeName) {
    const database = await openDatabase();
    return new Promise((resolve, reject) => {
      const request = database.transaction(storeName, 'readonly').objectStore(storeName).getAll();
      request.onsuccess = () => resolve(request.result || []);
      request.onerror = () => reject(request.error);
    });
  }

  async function getRecord(key) {
    const database = await openDatabase();
    return new Promise((resolve, reject) => {
      const request = database.transaction('records', 'readonly').objectStore('records').get(key);
      request.onsuccess = () => resolve(request.result || null);
      request.onerror = () => reject(request.error);
    });
  }

  function showToast(message, tone = 'amber') {
    const toast = document.createElement('div');
    const tones = {
      amber: 'border-amber-200 bg-amber-50 text-amber-800',
      blue: 'border-blue-200 bg-blue-50 text-blue-800',
      green: 'border-green-200 bg-green-50 text-green-800',
      red: 'border-red-200 bg-red-50 text-red-800',
    };
    toast.className = `fixed bottom-4 right-4 z-[100] rounded-lg border px-4 py-3 text-sm font-medium shadow-lg ${tones[tone] || tones.amber}`;
    toast.textContent = message;
    document.body.appendChild(toast);
    setTimeout(() => toast.remove(), 4000);
  }

  function getActionLabel(action) {
    return ({
      patient_create: 'Patient registration',
      appointment_create: 'Appointment',
      record_vitals: 'Vitals entry',
      add_medical_record: 'Medical record',
      record_eye_exam: 'Eye exam',
      admit_patient: 'Admission',
      schedule_follow_up: 'Follow-up',
      create_bill: 'Bill',
      record_payment: 'Payment',
    })[action] || action.replace(/_/g, ' ');
  }

  function recordTypeForAction(action) {
    return ({
      patient_create: 'patient',
      appointment_create: 'appointment',
      record_vitals: 'vitals',
      add_medical_record: 'medical_record',
      record_eye_exam: 'eye_exam',
      admit_patient: 'admission',
      schedule_follow_up: 'follow_up',
      create_bill: 'billing',
      record_payment: 'payment',
    })[action] || action;
  }

  function escapeHtml(value) {
    const element = document.createElement('div');
    element.textContent = String(value == null ? '' : value);
    return element.innerHTML;
  }

  async function updateSummary() {
    const operations = await getAll('operations');
    const summary = {
      total: operations.length,
      pending: operations.filter((item) => ['pending', 'syncing'].includes(item.status)).length,
      failed: operations.filter((item) => item.status === 'failed').length,
      synced: operations.filter((item) => item.status === 'synced').length,
    };
    localStorage.setItem(SUMMARY_KEY, JSON.stringify(summary));
    updateQueueBadge(summary.pending + summary.failed);
    renderQueueStatus(operations);
    window.dispatchEvent(new CustomEvent('offlinequeuechange', { detail: summary }));
    return summary;
  }

  function getQueueSummary() {
    try {
      return JSON.parse(localStorage.getItem(SUMMARY_KEY)) || { total: 0, pending: 0, failed: 0, synced: 0 };
    } catch (error) {
      return { total: 0, pending: 0, failed: 0, synced: 0 };
    }
  }

  function updateQueueBadge(count) {
    const badge = document.getElementById('offline-queue-badge');
    const label = document.getElementById('offline-queue-label');
    if (!badge || !label) return;
    label.textContent = `${count} pending`;
    badge.classList.toggle('hidden', count === 0);
    badge.classList.toggle('inline-flex', count > 0);
  }

  function renderQueueStatus(operations) {
    const panel = document.getElementById('offline-queue-panel');
    if (!panel) return;
    if (!operations.length) {
      panel.innerHTML = '<div class="text-sm text-gray-500">No offline records.</div>';
      return;
    }
    const sorted = operations.slice().sort((left, right) => right.createdAt.localeCompare(left.createdAt));
    panel.innerHTML = sorted.slice(0, 50).map((item) => `
      <div class="flex items-start justify-between gap-3 border-b border-gray-100 py-3">
        <div>
          <div class="text-sm font-medium text-gray-800">${escapeHtml(getActionLabel(item.action))}</div>
          <div class="text-xs text-gray-500">${escapeHtml(new Date(item.createdAt).toLocaleString())}</div>
          ${item.lastError ? `<div class="mt-1 text-xs text-red-600">${escapeHtml(item.lastError)}</div>` : ''}
        </div>
        <span class="rounded-full px-2 py-1 text-xs ${item.status === 'synced' ? 'bg-green-50 text-green-700' : item.status === 'failed' ? 'bg-red-50 text-red-700' : 'bg-amber-50 text-amber-700'}">${escapeHtml(item.status)}</span>
      </div>
    `).join('');
  }

  async function saveBootstrap(data) {
    const previousContext = getContext();
    const nextContext = {
      clinic: data.clinic,
      user: data.user,
      generatedAt: data.generatedAt,
      dataRefreshedAt: data.metadataOnly && previousContext ? previousContext.dataRefreshedAt : data.generatedAt,
      offlineExpiresAt: data.offlineExpiresAt,
    };
    localStorage.setItem(CONTEXT_KEY, JSON.stringify(nextContext));
    postWorkerMessage({ type: 'SET_CONTEXT', contextKey: workerContextKey(nextContext) });
    csrfToken = data.csrfToken || csrfToken;
    if (!previousContext || previousContext.clinic.sync_id !== data.clinic.sync_id || previousContext.user.id !== data.user.id) {
      databasePromise = null;
    }

    const records = [];
    data.patients.forEach((patient) => records.push({
      key: `patient:${patient.sync_id}`,
      type: 'patient',
      syncId: patient.sync_id,
      status: 'synced',
      payload: patient,
      updatedAt: patient.updated_at,
    }));
    data.appointments.forEach((appointment) => records.push({
      key: `appointment:${appointment.sync_id}`,
      type: 'appointment',
      syncId: appointment.sync_id,
      status: 'synced',
      payload: appointment,
      updatedAt: data.generatedAt,
    }));
    data.services.forEach((service) => records.push({
      key: `service:${service.id}`,
      type: 'service',
      syncId: String(service.id),
      status: 'synced',
      payload: service,
      updatedAt: data.generatedAt,
    }));
    (data.optical_products || []).forEach((product) => records.push({
      key: `optical_product:${product.id}`,
      type: 'optical_product',
      syncId: String(product.id),
      status: 'synced',
      payload: product,
      updatedAt: data.generatedAt,
    }));
    data.bills.forEach((bill) => records.push({
      key: `billing:${bill.sync_id}`,
      type: 'billing',
      syncId: bill.sync_id,
      status: 'synced',
      payload: bill,
      updatedAt: bill.updated_at,
    }));
    data.providers.forEach((provider) => records.push({
      key: `provider:${provider.id}`,
      type: 'provider',
      syncId: String(provider.id),
      status: 'synced',
      payload: provider,
      updatedAt: data.generatedAt,
    }));
    await transaction('records', 'readwrite', (store) => records.forEach((record) => store.put(record)));
    await transaction('metadata', 'readwrite', (store) => store.put({ key: 'bootstrap', value: nextContext }));
    if (!data.metadataOnly && data.patientPage === 1) {
      postWorkerMessage({
        type: 'WARM_PAGES',
        urls: ['/patients/', '/patients/add/', '/DurielMedicAppappointments/add/', '/billing/create/'],
      });
    }
    return nextContext;
  }

  async function refreshBootstrap() {
    let patientPage = 1;
    let data = null;
    do {
      const response = await fetch(`/api/offline/bootstrap/?patient_page=${patientPage}`, { credentials: 'same-origin', cache: 'no-store' });
      if (!response.ok) throw new Error(response.status === 403 ? 'Your session expired. Sign in before syncing.' : 'Unable to refresh clinic data.');
      data = await response.json();
      await saveBootstrap(data);
      patientPage += 1;
    } while (data.hasMorePatients);
    return data;
  }

  async function refreshSession() {
    const response = await fetch('/api/offline/bootstrap/?metadata_only=1', { credentials: 'same-origin', cache: 'no-store' });
    if (!response.ok) throw new Error(response.status === 403 ? 'Your session expired. Sign in before syncing.' : 'Unable to reach the clinic server.');
    const data = await response.json();
    await saveBootstrap(data);
    return data;
  }

  async function enqueue(action, payload, options = {}) {
    const context = getContext();
    if (!context) throw new Error('Open the application online once before using offline mode.');
    if (!context.offlineExpiresAt || new Date(context.offlineExpiresAt) <= new Date()) {
      throw new Error('Offline access expired. Connect to the internet and sign in again.');
    }
    const operationId = options.operationId || uuid();
    const recordId = options.recordId || payload._sync_id || uuid();
    const createdAt = new Date().toISOString();
    const operation = {
      operationId,
      recordId,
      action,
      payload: { ...payload, _sync_id: recordId },
      formKey: options.formKey || operationId,
      clinicSyncId: context.clinic.sync_id,
      status: 'pending',
      attempts: 0,
      lastError: '',
      createdAt,
    };
    const record = {
      key: `${recordTypeForAction(action)}:${recordId}`,
      type: recordTypeForAction(action),
      syncId: recordId,
      status: 'pending',
      payload: operation.payload,
      createdAt,
      updatedAt: createdAt,
    };
    await transaction('operations', 'readwrite', (store) => store.put(operation));
    await transaction('records', 'readwrite', (store) => store.put(record));
    await updateSummary();
    if (navigator.onLine) syncQueue();
    return operation;
  }

  async function setOperationStatus(operation, status, lastError = '') {
    operation.status = status;
    operation.lastError = lastError;
    operation.attempts = (operation.attempts || 0) + (status === 'syncing' ? 1 : 0);
    await transaction('operations', 'readwrite', (store) => store.put(operation));
  }

  async function markProcessed(item, result) {
    item.status = 'synced';
    item.lastError = '';
    item.serverResult = result;
    item.syncedAt = new Date().toISOString();
    await transaction('operations', 'readwrite', (store) => store.put(item));
    const key = `${recordTypeForAction(item.action)}:${item.recordId}`;
    const record = await getRecord(key);
    if (record) {
      record.status = 'synced';
      record.serverResult = result;
      record.updatedAt = item.syncedAt;
      if (item.action === 'patient_create' && result.patient_id) record.payload.patient_id = result.patient_id;
      if (result.server_id) record.payload.server_id = result.server_id;
      await transaction('records', 'readwrite', (store) => store.put(record));
    }
  }

  async function syncQueue() {
    if (!navigator.onLine || !getContext()) return;
    let operations = (await getAll('operations'))
      .filter((item) => ['pending', 'syncing'].includes(item.status))
      .sort((left, right) => (ACTION_ORDER[left.action] || 999) - (ACTION_ORDER[right.action] || 999) || left.createdAt.localeCompare(right.createdAt));
    if (!operations.length) return;

    try {
      await refreshSession();
    } catch (error) {
      operations.forEach((item) => { item.status = 'pending'; item.lastError = error.message; });
      await transaction('operations', 'readwrite', (store) => operations.forEach((item) => store.put(item)));
      await updateSummary();
      return;
    }

    for (let offset = 0; offset < operations.length; offset += 25) {
      const batch = operations.slice(offset, offset + 25);
      await Promise.all(batch.map((item) => setOperationStatus(item, 'syncing')));
      try {
        const response = await fetch('/api/sync/queue/', {
          method: 'POST',
          credentials: 'same-origin',
          headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
          body: JSON.stringify({ deviceId: getDeviceId(), items: batch }),
        });
        if (!response.ok) throw new Error(response.status === 403 ? 'Your session expired. Sign in before syncing.' : `Sync failed (${response.status}).`);
        const data = await response.json();
        const processed = new Map(data.processed.map((item) => [item.operationId, item]));
        const failed = new Map(data.failed.map((item) => [item.operationId, item]));
        for (const item of batch) {
          if (processed.has(item.operationId)) {
            await markProcessed(item, processed.get(item.operationId));
          } else {
            const failure = failed.get(item.operationId);
            item.status = 'failed';
            item.lastError = failure ? failure.error : 'The server did not acknowledge this record.';
            await transaction('operations', 'readwrite', (store) => store.put(item));
          }
        }
      } catch (error) {
        for (const item of batch) {
          item.status = 'pending';
          item.lastError = error.message;
          await transaction('operations', 'readwrite', (store) => store.put(item));
        }
        break;
      }
    }
    const summary = await updateSummary();
    if (!summary.pending && !summary.failed) showToast('Offline records synchronized.', 'green');
  }

  async function retryFailedQueue() {
    const operations = await getAll('operations');
    const failed = operations.filter((item) => item.status === 'failed');
    failed.forEach((item) => { item.status = 'pending'; item.lastError = ''; });
    await transaction('operations', 'readwrite', (store) => failed.forEach((item) => store.put(item)));
    await updateSummary();
    await syncQueue();
  }

  async function clearCompletedQueue() {
    const operations = await getAll('operations');
    await transaction('operations', 'readwrite', (store) => operations.filter((item) => item.status === 'synced').forEach((item) => store.delete(item.operationId)));
    await updateSummary();
  }

  async function clearPendingQueue() {
    const operations = await getAll('operations');
    await transaction('operations', 'readwrite', (store) => operations.filter((item) => item.status !== 'synced').forEach((item) => store.delete(item.operationId)));
    await updateSummary();
  }

  async function listRecords(type) {
    const records = await getAll('records');
    return records.filter((record) => record.type === type);
  }

  async function patchRecord(type, syncId, changes) {
    const record = await getRecord(`${type}:${syncId}`);
    if (!record) throw new Error('Local record was not found.');
    record.payload = { ...record.payload, ...changes };
    record.updatedAt = new Date().toISOString();
    await transaction('records', 'readwrite', (store) => store.put(record));
    window.dispatchEvent(new CustomEvent('offlinerecordchange', { detail: record }));
    return record;
  }

  async function migrateLegacyQueue() {
    let legacyItems;
    try {
      legacyItems = JSON.parse(localStorage.getItem(LEGACY_QUEUE_KEY) || '[]');
    } catch (error) {
      legacyItems = [];
    }
    if (!Array.isArray(legacyItems) || !legacyItems.length) return;

    for (const legacyItem of legacyItems.filter((item) => item.status !== 'synced')) {
      const recordId = uuid();
      const operationId = uuid();
      const createdAt = legacyItem.submittedAt || new Date().toISOString();
      const operation = {
        operationId,
        recordId,
        action: legacyItem.action,
        payload: { ...(legacyItem.payload || {}), _sync_id: recordId },
        formKey: legacyItem.formKey || operationId,
        clinicSyncId: getContext().clinic.sync_id,
        status: legacyItem.status === 'failed' ? 'failed' : 'pending',
        attempts: legacyItem.attempts || 0,
        lastError: legacyItem.lastError || '',
        createdAt,
      };
      const record = {
        key: `${recordTypeForAction(operation.action)}:${recordId}`,
        type: recordTypeForAction(operation.action),
        syncId: recordId,
        status: operation.status,
        payload: operation.payload,
        createdAt,
        updatedAt: createdAt,
      };
      await transaction('operations', 'readwrite', (store) => store.put(operation));
      await transaction('records', 'readwrite', (store) => store.put(record));
    }
    localStorage.removeItem(LEGACY_QUEUE_KEY);
  }

  function serializeForm(form) {
    const payload = {};
    const formData = new FormData(form);
    for (const [key, value] of formData.entries()) {
      if (value instanceof File) {
        if (value.size) showToast('Attachments are not available offline and were not saved.', 'amber');
        continue;
      }
      if (Object.prototype.hasOwnProperty.call(payload, key)) {
        payload[key] = Array.isArray(payload[key]) ? [...payload[key], value] : [payload[key], value];
      } else {
        payload[key] = value;
      }
    }
    if (form.dataset.patientSyncId) payload._patient_sync_id = form.dataset.patientSyncId;
    if (form.dataset.patientId && !payload.patient_id && !payload.patient) payload.patient_id = form.dataset.patientId;
    if (form.dataset.appointmentSyncId) payload._appointment_sync_id = form.dataset.appointmentSyncId;
    if (form.dataset.billingSyncId) payload._billing_sync_id = form.dataset.billingSyncId;
    delete payload.csrfmiddlewaretoken;
    return payload;
  }

  function setupForm(form) {
    const action = form.dataset.syncAction;
    if (!action || form.dataset.offlineReady === 'true') return;
    form.dataset.offlineReady = 'true';
    form.addEventListener('submit', async (event) => {
      const serverRole = document.body?.dataset.serverSyncRole || 'standalone';
      const isLoopbackServer = ['localhost', '127.0.0.1', '::1'].includes(window.location.hostname);
      // A reachable cloud or clinic server must process normal POST requests.
      // The IndexedDB queue is only a fallback for a cached cloud page whose
      // browser has genuinely lost network connectivity.
      if (serverRole === 'local' || isLoopbackServer || navigator.onLine) return;
      const hasAttachment = Array.from(form.querySelectorAll('input[type="file"]')).some((input) => input.files && input.files.length);
      if (hasAttachment) return;
      event.preventDefault();
      if (!form.reportValidity()) return;
      try {
        const operation = await enqueue(action, serializeForm(form), { formKey: `${location.pathname}:${uuid()}` });
        showToast(`${getActionLabel(action)} saved on this device.`, navigator.onLine ? 'blue' : 'amber');
        form.dispatchEvent(new CustomEvent('offlinesaved', { detail: operation }));
        form.reset();
        if (action === 'patient_create') {
          window.location.assign(`/patients/#offline-patient=${operation.recordId}`);
        }
      } catch (error) {
        showToast(error.message, 'red');
      }
    });
  }

  async function clearDeviceData() {
    const name = databaseName();
    if (databasePromise) {
      const database = await databasePromise;
      database.close();
    }
    databasePromise = null;
    await new Promise((resolve, reject) => {
      const request = indexedDB.deleteDatabase(name);
      request.onsuccess = resolve;
      request.onerror = () => reject(request.error);
      request.onblocked = resolve;
    });
    localStorage.removeItem(CONTEXT_KEY);
    localStorage.removeItem(SUMMARY_KEY);
    postWorkerMessage({ type: 'CLEAR_CONTEXT' });
  }

  function lockDeviceData() {
    databasePromise = null;
    localStorage.removeItem(CONTEXT_KEY);
    localStorage.removeItem(SUMMARY_KEY);
    postWorkerMessage({ type: 'CLEAR_CONTEXT' });
  }

  const ready = (async () => {
    if (navigator.onLine) {
      try {
        const context = getContext();
        const stale = !context || !context.dataRefreshedAt || Date.now() - new Date(context.dataRefreshedAt).getTime() > 15 * 60 * 1000;
        if (stale) await refreshBootstrap();
        else await refreshSession();
      } catch (error) { /* Existing local data remains available. */ }
    }
    if (getContext()) {
      await openDatabase();
      await migrateLegacyQueue();
      await updateSummary();
    }
  })();

  document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('form[data-sync-action]').forEach(setupForm);
    document.querySelectorAll('a[href*="/logout/"]').forEach((link) => link.addEventListener('click', lockDeviceData));
    window.addEventListener('online', syncQueue);
    window.addEventListener('offlinequeuechange', () => updateQueueBadge(getQueueSummary().pending + getQueueSummary().failed));
    ready.then(syncQueue);
  });

  window.offlineQueue = {
    ready,
    enqueue,
    syncQueue,
    retryFailedQueue,
    clearCompletedQueue,
    clearPendingQueue,
    clearDeviceData,
    lockDeviceData,
    getQueueSummary,
    getContext,
    listRecords,
    patchRecord,
    refreshBootstrap,
  };
})();
