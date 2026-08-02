(function () {
  const DRAFT_PREFIX = 'durielmedic_draft_';
  const QUEUE_KEY = 'durielmedic_offline_queue';
  const MAX_QUEUE_ENTRIES = 100;

  function safeStorage() {
    try {
      return window.localStorage;
    } catch (error) {
      return null;
    }
  }

  function getStorageKey(form) {
    if (form.dataset.draftKey) {
      return form.dataset.draftKey;
    }

    const action = form.getAttribute('action') || window.location.pathname;
    const formId = form.id || 'default-form';
    const path = window.location.pathname.replace(/[^a-zA-Z0-9]+/g, '_') || 'root';
    return `${DRAFT_PREFIX}${path}_${formId}_${action}`;
  }

  function isSensitiveForm(form) {
    const action = (form.getAttribute('action') || '').toLowerCase();
    return action.includes('login') || form.classList.contains('no-offline-draft');
  }

  function getQueue() {
    const storage = safeStorage();
    if (!storage) return [];

    try {
      return JSON.parse(storage.getItem(QUEUE_KEY) || '[]');
    } catch (error) {
      return [];
    }
  }

  function saveQueue(queue) {
    const storage = safeStorage();
    if (!storage) return;

    storage.setItem(QUEUE_KEY, JSON.stringify(queue));
    updateQueueBadge(queue.length);
    renderQueueStatus(queue);
  }

  function showToast(message, tone = 'amber') {
    const toast = document.createElement('div');
    const toneClasses = {
      amber: 'border-amber-200 bg-amber-50 text-amber-800',
      blue: 'border-blue-200 bg-blue-50 text-blue-800',
      green: 'border-green-200 bg-green-50 text-green-800'
    };

    toast.className = `fixed bottom-4 right-4 z-[100] rounded-lg border px-4 py-3 text-sm font-medium shadow-lg ${toneClasses[tone] || toneClasses.amber}`;
    toast.textContent = message;
    document.body.appendChild(toast);
    setTimeout(() => toast.remove(), 3000);
  }

  function getActionLabel(actionType) {
    const labels = {
      patient_create: 'Patient registration',
      record_vitals: 'Vitals entry',
      add_medical_record: 'Medical record',
      admit_patient: 'Admission',
      schedule_follow_up: 'Follow-up',
      create_bill: 'Billing',
      record_payment: 'Payment'
    };
    return labels[actionType] || actionType.replace(/_/g, ' ').replace(/\b\w/g, (l) => l.toUpperCase());
  }

  function addQueueEntry(entry) {
    const queue = getQueue();
    queue.push({
      ...entry,
      status: 'queued',
      attempts: 0,
      lastError: ''
    });

    if (queue.length > MAX_QUEUE_ENTRIES) {
      queue.splice(0, queue.length - MAX_QUEUE_ENTRIES);
    }

    saveQueue(queue);
  }

  function removeQueueEntry(formKey) {
    const queue = getQueue().filter((entry) => entry.formKey !== formKey);
    saveQueue(queue);
  }

  function retryQueueEntry(formKey) {
    const queue = getQueue();
    const updated = queue.map((entry) => (entry.formKey === formKey ? { ...entry, status: 'queued', lastError: '' } : entry));
    saveQueue(updated);
    showToast('Retrying queued action…', 'blue');
    syncQueue(true);
  }

  function retryFailedQueue() {
    const queue = getQueue();
    const updated = queue.map((entry) => (entry.status === 'failed' ? { ...entry, status: 'queued', lastError: '' } : entry));
    saveQueue(updated);
    showToast('Retrying failed actions…', 'blue');
    syncQueue(true);
  }

  function clearCompletedQueue() {
    const queue = getQueue().filter((entry) => entry.status !== 'synced');
    saveQueue(queue);
    showToast('Cleared completed items.', 'green');
  }

  function renderQueueStatus(queue) {
    const panel = document.getElementById('offline-queue-panel');
    if (!panel) return;

    if (!queue.length) {
      panel.innerHTML = '<div class="text-sm text-gray-500">No queued actions.</div>';
      return;
    }

    const failedCount = queue.filter((entry) => entry.status === 'failed').length;
    const hasSyncedItems = queue.some((entry) => entry.status === 'synced');
    const retryButton = failedCount
      ? '<button type="button" data-retry-all="true" class="rounded border border-blue-200 px-2 py-1 text-xs font-medium text-blue-700 hover:bg-blue-50">Retry failed</button>'
      : '';
    const clearButton = hasSyncedItems
      ? '<button type="button" data-clear-completed="true" class="rounded border border-green-200 px-2 py-1 text-xs font-medium text-green-700 hover:bg-green-50">Clear synced</button>'
      : '';

    panel.innerHTML = `
      <div class="mb-2 flex items-center justify-between gap-2">
        <div class="text-xs font-semibold uppercase tracking-wide text-gray-500">Queue</div>
        <div class="flex gap-2">${retryButton}${clearButton}</div>
      </div>
      ${queue.map((entry) => {
        const label = entry.action || 'unknown-action';
        const statusClass = entry.status === 'synced' ? 'bg-green-100 text-green-700' : entry.status === 'failed' ? 'bg-red-100 text-red-700' : 'bg-amber-100 text-amber-700';
        const retryControl = entry.status === 'failed'
          ? `<button type="button" data-retry-form-key="${entry.formKey}" class="text-xs font-medium text-blue-700 hover:text-blue-900">Retry</button>`
          : '';
        return `
          <div class="flex items-center justify-between gap-2 rounded-lg border border-gray-200 px-3 py-2 text-sm">
            <div>
              <div class="font-medium text-gray-800">${getActionLabel(entry.action)}</div>
              <div class="text-xs text-gray-500">${entry.submittedAt || ''}</div>
            </div>
            <div class="flex items-center gap-2">
              ${retryControl}
              <span class="rounded-full px-2 py-1 text-xs font-medium ${statusClass}">${entry.status || 'queued'}</span>
            </div>
          </div>
        `;
      }).join('')}
    `;
  }

  function syncQueue(force = false) {
    const queue = getQueue();
    if ((!force && !navigator.onLine) || queue.length === 0) return;

    const pendingQueue = queue.filter((entry) => entry.status !== 'synced');
    if (!pendingQueue.length) return;

    const updatedQueue = pendingQueue.map((entry) => ({ ...entry, status: 'syncing', attempts: (entry.attempts || 0) + 1 }));
    saveQueue(queue.map((entry) => {
      const match = updatedQueue.find((updated) => updated.formKey === entry.formKey);
      return match || entry;
    }));

    fetch('/api/sync/queue/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ items: updatedQueue })
    })
      .then((response) => response.json())
      .then((data) => {
        if (!data.success) {
          const remaining = queue.map((entry) => {
            const match = updatedQueue.find((updated) => updated.formKey === entry.formKey);
            if (!match) return entry;
            return { ...match, status: 'failed', lastError: 'Sync request failed' };
          });
          saveQueue(remaining);
          return;
        }

        const successfulKeys = new Set((data.processed || []).map((item) => item.formKey));
        const failedKeys = new Set((data.failed || []).map((item) => item.formKey));
        const updated = queue.map((entry) => {
          if (successfulKeys.has(entry.formKey)) {
            return { ...entry, status: 'synced', lastError: '' };
          }
          if (failedKeys.has(entry.formKey)) {
            const match = updatedQueue.find((updatedEntry) => updatedEntry.formKey === entry.formKey);
            const attempts = (match?.attempts || 0) + 1;
            return { ...entry, status: attempts > 3 ? 'failed' : 'queued', attempts, lastError: data.failed.find((item) => item.formKey === entry.formKey)?.error || 'Sync failed' };
          }
          return entry;
        });
        saveQueue(updated);
      })
      .catch(() => {
        const updated = queue.map((entry) => {
          const match = updatedQueue.find((updatedEntry) => updatedEntry.formKey === entry.formKey);
          if (!match) return entry;
          return { ...match, status: 'failed', lastError: 'Network error' };
        });
        saveQueue(updated);
      });
  }

  function updateQueueBadge(count) {
    const badge = document.getElementById('offline-queue-badge');
    const label = document.getElementById('offline-queue-label');
    if (!badge || !label) return;

    if (count > 0) {
      badge.classList.remove('hidden');
      label.textContent = `${count} draft${count === 1 ? '' : 's'}`;
    } else {
      badge.classList.add('hidden');
      label.textContent = '0 drafts';
    }
  }

  function serializeForm(form) {
    const payload = {};
    Array.from(form.elements).forEach((element) => {
      if (!element.name || element.disabled) return;
      if (['submit', 'button', 'reset', 'file'].includes(element.type)) return;
      if (element.type === 'password') return;

      if (element.type === 'checkbox' || element.type === 'radio') {
        payload[element.name] = element.checked ? element.value : '';
      } else if (element.type === 'select-multiple') {
        payload[element.name] = Array.from(element.selectedOptions).map((option) => option.value);
      } else {
        payload[element.name] = element.value;
      }
    });

    return payload;
  }

  function restoreForm(form, draft) {
    Object.entries(draft).forEach(([name, value]) => {
      const matchingFields = Array.from(form.elements).filter((element) => element.name === name);
      matchingFields.forEach((element) => {
        if (element.type === 'checkbox' || element.type === 'radio') {
          element.checked = String(value) === String(element.value);
        } else if (element.type === 'select-multiple') {
          Array.from(element.options).forEach((option) => {
            option.selected = Array.isArray(value) && value.includes(option.value);
          });
        } else {
          element.value = value || '';
        }
      });
    });
  }

  function saveDraft(form) {
    const storage = safeStorage();
    if (!storage) return;

    const key = getStorageKey(form);
    const payload = serializeForm(form);
    storage.setItem(key, JSON.stringify(payload));
  }

  function loadDraft(form) {
    const storage = safeStorage();
    if (!storage) return false;

    const key = getStorageKey(form);
    const rawDraft = storage.getItem(key);
    if (!rawDraft) return false;

    try {
      const draft = JSON.parse(rawDraft);
      restoreForm(form, draft);
      return true;
    } catch (error) {
      return false;
    }
  }

  function clearDraft(form) {
    const storage = safeStorage();
    if (!storage) return;
    storage.removeItem(getStorageKey(form));
  }

  function setupForm(form) {
    if (!form || form.method.toLowerCase() === 'get' || isSensitiveForm(form)) return;

    const hasExistingDraft = loadDraft(form);
    if (hasExistingDraft) {
      form.dataset.offlineDraftRestored = 'true';
    }

    form.addEventListener('input', () => saveDraft(form));
    form.addEventListener('change', () => saveDraft(form));
    form.addEventListener('submit', (event) => {
      if (navigator.onLine) {
        clearDraft(form);
        return;
      }

      event.preventDefault();
      const payload = serializeForm(form);
      const actionType = form.dataset.syncAction || 'patient_create';
      addQueueEntry({
        formKey: getStorageKey(form),
        action: actionType,
        payload,
        submittedAt: new Date().toISOString()
      });
      saveDraft(form);

      const actionLabel = getActionLabel(actionType).toLowerCase();
      showToast(`Queued ${actionLabel}. It will sync when the connection is restored.`, 'amber');
    });
  }

  document.addEventListener('DOMContentLoaded', () => {
    updateQueueBadge(getQueue().length);
    renderQueueStatus(getQueue());

    const queuePanel = document.getElementById('offline-queue-panel');
    if (queuePanel) {
      queuePanel.addEventListener('click', (event) => {
        const retryAllButton = event.target.closest('[data-retry-all="true"]');
        if (retryAllButton) {
          retryFailedQueue();
          return;
        }

        const clearCompletedButton = event.target.closest('[data-clear-completed="true"]');
        if (clearCompletedButton) {
          clearCompletedQueue();
          return;
        }

        const retryButton = event.target.closest('[data-retry-form-key]');
        if (retryButton) {
          retryQueueEntry(retryButton.getAttribute('data-retry-form-key'));
        }
      });
    }

    Array.from(document.querySelectorAll('form')).forEach((form) => setupForm(form));
    saveQueue(getQueue());
    window.addEventListener('online', () => syncQueue());
    window.addEventListener('load', () => syncQueue());
  });
})();
