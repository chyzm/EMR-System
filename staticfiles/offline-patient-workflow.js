(function () {
  const patientTable = document.querySelector('[data-offline-patient-list]');
  const patientDetail = document.querySelector('[data-patient-sync-id]');
  if (!patientTable && !patientDetail) return;

  let localPatients = [];
  let selectedPatient = null;

  function escapeHtml(input) {
    const element = document.createElement('div');
    element.textContent = String(input == null ? '' : input);
    return element.innerHTML;
  }

  function value(record, name) {
    return record && record.payload ? record.payload[name] : '';
  }

  function patientName(record) {
    return `${value(record, 'first_name')} ${value(record, 'last_name')}`.trim();
  }

  function patientIdentifier(record) {
    return value(record, 'patient_id') || `OFF-${record.syncId.slice(0, 8).toUpperCase()}`;
  }

  function field(label, name, type = 'text', attributes = '') {
    return `<div><label class="block text-sm font-medium text-gray-700 mb-1">${label}</label><input name="${name}" type="${type}" ${attributes} class="w-full px-3 py-2 border border-gray-300 rounded-md"></div>`;
  }

  function textArea(label, name, attributes = '') {
    return `<div><label class="block text-sm font-medium text-gray-700 mb-1">${label}</label><textarea name="${name}" ${attributes} class="w-full px-3 py-2 border border-gray-300 rounded-md" rows="3"></textarea></div>`;
  }

  function selectField(label, name, options, attributes = '') {
    return `<div><label class="block text-sm font-medium text-gray-700 mb-1">${label}</label><select name="${name}" ${attributes} class="w-full px-3 py-2 border border-gray-300 rounded-md">${options}</select></div>`;
  }

  function submit(label) {
    return `<div class="pt-3"><button type="submit" class="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700">${label}</button></div>`;
  }

  function contextRole() {
    const context = window.offlineQueue.getContext();
    return context ? context.user.role : '';
  }

  function allowedRoles(action) {
    return ({
      appointment: ['ADMIN', 'DOCTOR', 'RECEPTIONIST', 'NURSE', 'OPTOMETRIST'],
      vitals: ['ADMIN', 'DOCTOR', 'NURSE'],
      medical: ['ADMIN', 'DOCTOR', 'NURSE'],
      admission: ['ADMIN', 'DOCTOR', 'NURSE'],
      followup: ['ADMIN', 'DOCTOR'],
      billing: ['ADMIN', 'RECEPTIONIST'],
      payment: ['ADMIN', 'RECEPTIONIST'],
    })[action] || [];
  }

  function statusAfterAction(action) {
    return ({ vitals: 'VITALS_TAKEN', medical: 'CONSULTATION_COMPLETE', admission: 'ADMITTED', followup: 'FOLLOW_UP' })[action];
  }

  function actionAllowedForStatus(action, status) {
    if (['appointment', 'billing', 'payment'].includes(action)) return true;
    if (action === 'vitals') return ['REGISTERED', 'INSURANCE'].includes(status);
    if (action === 'medical') return ['REGISTERED', 'INSURANCE', 'VITALS_TAKEN', 'IN_CONSULTATION'].includes(status);
    if (action === 'admission') return ['VITALS_TAKEN', 'CONSULTATION_COMPLETE'].includes(status);
    if (action === 'followup') return ['IN_CONSULTATION', 'CONSULTATION_COMPLETE'].includes(status);
    return false;
  }

  function ensurePanel() {
    let panel = document.getElementById('local-patient-detail');
    if (panel) return panel;
    panel = document.createElement('div');
    panel.id = 'local-patient-detail';
    panel.className = 'hidden fixed inset-0 z-[90] overflow-y-auto bg-gray-900/60 p-4 md:p-8';
    panel.innerHTML = `
      <div class="mx-auto max-w-5xl rounded-xl bg-gray-50 shadow-2xl">
        <div class="flex items-start justify-between rounded-t-xl bg-gray-800 px-6 py-4 text-white">
          <div><h2 id="local-patient-name" class="text-xl font-semibold"></h2><p id="local-patient-id" class="text-sm text-gray-300"></p></div>
          <button id="close-local-patient" type="button" class="rounded bg-gray-700 px-3 py-1 hover:bg-gray-600">Close</button>
        </div>
        <div class="p-6">
          <div id="local-patient-summary" class="mb-6 rounded-lg bg-white p-4 shadow"></div>
          <div id="local-workflow-actions" class="mb-5 flex flex-wrap gap-2"></div>
          <div class="rounded-lg bg-white p-5 shadow"><h3 id="local-form-title" class="mb-4 text-lg font-semibold"></h3><form id="local-workflow-form" class="space-y-4"></form></div>
          <div id="local-patient-activity" class="mt-6 rounded-lg bg-white p-5 shadow"></div>
        </div>
      </div>`;
    document.body.appendChild(panel);
    panel.querySelector('#close-local-patient').addEventListener('click', closePanel);
    panel.querySelector('#local-workflow-actions').addEventListener('click', (event) => {
      const button = event.target.closest('[data-local-action]');
      if (button) renderAction(button.dataset.localAction);
    });
    panel.querySelector('#local-workflow-form').addEventListener('submit', submitWorkflow);
    return panel;
  }

  function closePanel() {
    ensurePanel().classList.add('hidden');
    if (location.hash.startsWith('#offline-patient=')) history.replaceState(null, '', `${location.pathname}${location.search}`);
  }

  async function recordsForPatient() {
    const types = ['appointment', 'vitals', 'medical_record', 'admission', 'follow_up', 'billing', 'payment'];
    const groups = await Promise.all(types.map((type) => window.offlineQueue.listRecords(type)));
    return groups.flat().filter((record) => {
      const patientSyncId = value(record, '_patient_sync_id') || value(record, 'patient_sync_id');
      if (patientSyncId === selectedPatient.syncId) return true;
      if (record.type === 'payment') return false;
      return false;
    });
  }

  async function renderActivity() {
    const records = await recordsForPatient();
    const activity = ensurePanel().querySelector('#local-patient-activity');
    activity.innerHTML = `<h3 class="mb-3 text-lg font-semibold">Records saved on this device</h3>${records.length ? records.map((record) => `
      <div class="flex items-center justify-between border-t border-gray-100 py-3">
        <span class="capitalize">${escapeHtml(record.type.replace(/_/g, ' '))}</span>
        <span class="rounded-full px-2 py-1 text-xs ${record.status === 'synced' ? 'bg-green-100 text-green-800' : record.status === 'failed' ? 'bg-red-100 text-red-800' : 'bg-amber-100 text-amber-800'}">${escapeHtml(record.status)}</span>
      </div>`).join('') : '<p class="text-sm text-gray-500">No additional records saved yet.</p>'}`;
  }

  async function openPatient(syncId) {
    localPatients = await window.offlineQueue.listRecords('patient');
    selectedPatient = localPatients.find((patient) => patient.syncId === syncId) || null;
    if (!selectedPatient) return;
    const panel = ensurePanel();
    panel.querySelector('#local-patient-name').textContent = patientName(selectedPatient);
    panel.querySelector('#local-patient-id').textContent = `${patientIdentifier(selectedPatient)} · Saved on this device`;
    panel.querySelector('#local-patient-summary').innerHTML = `
      <div class="grid grid-cols-1 gap-3 md:grid-cols-2">
        <p><strong>Status:</strong> ${escapeHtml(value(selectedPatient, 'status') || 'REGISTERED')}</p>
        <p><strong>Date of birth:</strong> ${escapeHtml(value(selectedPatient, 'date_of_birth'))}</p>
        <p><strong>Contact:</strong> ${escapeHtml(value(selectedPatient, 'contact'))}</p>
        <p><strong>Allergies:</strong> ${escapeHtml(value(selectedPatient, 'allergies') || 'None recorded')}</p>
      </div>`;
    const actions = ['appointment', 'vitals', 'medical', 'admission', 'followup', 'billing', 'payment'];
    const currentStatus = value(selectedPatient, 'status') || 'REGISTERED';
    const permitted = actions.filter((action) => allowedRoles(action).includes(contextRole()) && actionAllowedForStatus(action, currentStatus));
    panel.querySelector('#local-workflow-actions').innerHTML = permitted.map((action) => `<button type="button" data-local-action="${action}" class="rounded-md bg-gray-200 px-3 py-2 text-sm font-medium text-gray-800 hover:bg-blue-600 hover:text-white">${action === 'medical' ? 'Patient Record' : action.charAt(0).toUpperCase() + action.slice(1)}</button>`).join('');
    panel.classList.remove('hidden');
    await renderActivity();
    if (permitted.length) await renderAction(permitted[0]);
  }

  async function optionRecords(type, filter) {
    const records = await window.offlineQueue.listRecords(type);
    return filter ? records.filter(filter) : records;
  }

  async function renderAction(action) {
    const panel = ensurePanel();
    const form = panel.querySelector('#local-workflow-form');
    panel.querySelector('#local-form-title').textContent = action === 'medical' ? 'Add Patient Record' : `${action.charAt(0).toUpperCase() + action.slice(1)} Details`;
    form.dataset.action = action;
    if (action === 'appointment') {
      const providers = await optionRecords('provider');
      const options = providers.map((provider) => `<option value="${escapeHtml(value(provider, 'id'))}">${escapeHtml(value(provider, 'name'))} (${escapeHtml(value(provider, 'role'))})</option>`).join('');
      form.innerHTML = `${selectField('Provider', 'provider', options, 'required')}<div class="grid gap-4 md:grid-cols-2">${field('Date', 'date', 'date', 'required')}${selectField('Payment type', 'payment_type', '<option value="SELF">Self paid</option><option value="INSURANCE">Insurance</option>')}</div><div class="grid gap-4 md:grid-cols-2">${field('Start time', 'start_time', 'time', 'required')}${field('End time', 'end_time', 'time', 'required')}</div>${textArea('Reason', 'reason', 'required')}${textArea('Notes', 'notes')}${submit('Save Appointment')}`;
    } else if (action === 'vitals') {
      const appointments = await optionRecords('appointment', (record) => value(record, 'patient_sync_id') === selectedPatient.syncId || value(record, '_patient_sync_id') === selectedPatient.syncId);
      const options = appointments.map((appointment) => `<option value="${escapeHtml(appointment.syncId)}">${escapeHtml(value(appointment, 'date'))} ${escapeHtml(value(appointment, 'start_time'))} — ${escapeHtml(value(appointment, 'reason'))}</option>`).join('');
      form.innerHTML = appointments.length ? `${selectField('Appointment', '_appointment_sync_id', options, 'required')}<div class="grid gap-4 md:grid-cols-2">${field('Blood pressure', 'blood_pressure', 'text', 'required placeholder="120/80"')}${field('Pulse', 'pulse', 'number', 'required')}</div><div class="grid gap-4 md:grid-cols-2">${field('Temperature', 'temperature', 'number', 'required step="0.1"')}${field('Weight (kg)', 'weight', 'number', 'required step="0.1"')}</div>${selectField('Category', 'category', '<option value="CONSULT">Consultation</option><option value="FOLLOWUP">Follow-up</option>')}${textArea('Notes', 'notes')}${submit('Save Vitals')}` : '<p class="text-amber-700">Create an appointment for this patient before recording vitals.</p>';
    } else if (action === 'medical') {
      form.innerHTML = `${textArea('Chief complaint', 'chief_complaint')}${textArea('History of present illness', 'history_of_present_illness')}${textArea('Past medical history', 'past_medical_history')}${textArea('Diagnosis', 'diagnosis')}${textArea('Treatment plan', 'treatment_plan')}${textArea('Lab results', 'lab_results')}${textArea('Imaging results', 'imaging_results')}${textArea('Allergies', 'allergies')}${textArea('Procedures', 'procedures')}${textArea('Additional notes', 'additional_notes')}${submit('Save Patient Record')}`;
    } else if (action === 'admission') {
      const providers = await optionRecords('provider');
      const options = providers.map((provider) => `<option value="${escapeHtml(provider.syncId)}">${escapeHtml(value(provider, 'name') || value(provider, 'username'))}</option>`).join('');
      form.innerHTML = `<div class="grid gap-4 md:grid-cols-2">${field('Ward', 'ward', 'text', 'required')}${field('Bed', 'bed')}</div><div class="grid gap-4 md:grid-cols-2">${selectField('Admission type', 'admission_type', '<option value="EMERGENCY">Emergency</option><option value="ELECTIVE">Elective</option><option value="REFERRAL">Referral</option><option value="OBSERVATION">Observation</option><option value="MATERNITY">Maternity</option><option value="SURGICAL">Surgical</option>')}${selectField('Admission source', 'admission_source', '<option value="OPD">Outpatient Department</option><option value="EMERGENCY">Emergency Unit</option><option value="REFERRAL">Referral</option><option value="TRANSFER">Transfer</option><option value="DIRECT">Direct Admission</option>')}</div>${providers.length ? selectField('Attending doctor', 'attending_doctor', options) : ''}${textArea('Provisional diagnosis', 'provisional_diagnosis')}${textArea('Reason', 'reason', 'required')}${field('Expected discharge date', 'expected_discharge_date', 'date')}${submit('Save Admission')}`;
    } else if (action === 'followup') {
      form.innerHTML = `${textArea('Reason', 'reason', 'required')}<div class="grid gap-4 md:grid-cols-2">${field('Date', 'scheduled_date', 'date', 'required')}${field('Time', 'scheduled_time', 'time', 'required')}</div>${textArea('Notes', 'notes')}${submit('Save Follow-up')}`;
    } else if (action === 'billing') {
      const services = await optionRecords('service');
      const options = services.map((service) => `<option value="${escapeHtml(value(service, 'id'))}">${escapeHtml(value(service, 'name'))} — ₦${escapeHtml(value(service, 'price'))}</option>`).join('');
      form.innerHTML = `${selectField('Services', 'services', options, 'multiple size="5"')}<div class="grid gap-4 md:grid-cols-2">${field('Service date', 'service_date', 'date', 'required')}${field('Due date', 'due_date', 'date', 'required')}</div>${field('Amount when no service is selected', 'amount', 'number', 'required min="0" step="0.01" value="0"')}${textArea('Description', 'description')}${selectField('Discount type', 'discount_type', '<option value="NONE">None</option><option value="PERCENTAGE">Percentage</option><option value="FIXED">Fixed</option>')}${field('Discount value', 'discount_value', 'number', 'min="0" step="0.01" value="0"')}${field('Discount reason', 'discount_reason')}<input type="hidden" name="paid_amount" value="0">${submit('Save Bill')}`;
    } else if (action === 'payment') {
      const bills = await optionRecords('billing', (record) => value(record, '_patient_sync_id') === selectedPatient.syncId || value(record, 'patient_sync_id') === selectedPatient.syncId);
      const options = bills.map((bill) => `<option value="${escapeHtml(bill.syncId)}">${escapeHtml(value(bill, 'description') || 'Bill')} — ₦${escapeHtml(value(bill, 'balance') || value(bill, 'amount'))}</option>`).join('');
      form.innerHTML = bills.length ? `${selectField('Bill', '_billing_sync_id', options, 'required')}${field('Amount', 'payment_amount', 'number', 'required min="0.01" step="0.01"')}${selectField('Method', 'payment_method', '<option value="CASH">Cash</option><option value="BANK_TRANSFER">Bank transfer</option><option value="CHEQUE">Cheque</option><option value="OTHER">Other</option>')}${field('Transaction reference', 'transaction_reference')}${textArea('Notes', 'notes')}${submit('Save Payment')}` : '<p class="text-amber-700">Create a bill for this patient before recording payment.</p>';
    }
  }

  async function submitWorkflow(event) {
    event.preventDefault();
    const form = event.currentTarget;
    if (!form.reportValidity()) return;
    const action = form.dataset.action;
    const payload = { _patient_sync_id: selectedPatient.syncId, _offline_workspace: 'true' };
    new FormData(form).forEach((fieldValue, key) => {
      payload[key] = Object.prototype.hasOwnProperty.call(payload, key) ? [].concat(payload[key], fieldValue) : fieldValue;
    });
    const syncAction = ({ appointment: 'appointment_create', vitals: 'record_vitals', medical: 'add_medical_record', admission: 'admit_patient', followup: 'schedule_follow_up', billing: 'create_bill', payment: 'record_payment' })[action];
    await window.offlineQueue.enqueue(syncAction, payload);
    const nextStatus = statusAfterAction(action);
    if (nextStatus) {
      await window.offlineQueue.patchRecord('patient', selectedPatient.syncId, { status: nextStatus });
      selectedPatient.payload.status = nextStatus;
    }
    const patientSyncId = selectedPatient.syncId;
    await renderLocalPatients();
    await openPatient(patientSyncId);
  }

  async function renderLocalPatients() {
    if (!patientTable) return;
    localPatients = (await window.offlineQueue.listRecords('patient')).filter((patient) => patient.status !== 'synced');
    patientTable.querySelectorAll('[data-local-patient-row]').forEach((row) => row.remove());
    localPatients.forEach((patient) => {
      const row = document.createElement('tr');
      row.dataset.localPatientRow = patient.syncId;
      row.className = 'bg-amber-50 hover:bg-amber-100';
      row.innerHTML = `
        <td class="px-6 py-4 whitespace-nowrap">${escapeHtml(patientName(patient))}<span class="ml-2 rounded-full bg-amber-100 px-2 py-1 text-xs text-amber-800">On device</span></td>
        <td class="px-6 py-4 whitespace-nowrap">${escapeHtml(patientIdentifier(patient))}</td>
        <td class="px-6 py-4 whitespace-nowrap">${escapeHtml((window.offlineQueue.getContext() || { clinic: {} }).clinic.name || '')}</td>
        <td class="px-6 py-4 whitespace-nowrap"><a href="#offline-patient=${patient.syncId}" class="text-blue-600 hover:underline">View</a></td>
        <td class="px-6 py-4 whitespace-nowrap"><span class="text-xs text-amber-700">Pending synchronization</span></td>`;
      patientTable.prepend(row);
    });
  }

  async function renderPendingPatientActivity() {
    if (!patientDetail) return;
    const patientSyncId = patientDetail.dataset.patientSyncId;
    const types = ['appointment', 'vitals', 'medical_record', 'admission', 'follow_up', 'billing', 'payment'];
    const records = (await Promise.all(types.map((type) => window.offlineQueue.listRecords(type)))).flat().filter((record) => {
      return record.status !== 'synced' && (value(record, '_patient_sync_id') === patientSyncId || value(record, 'patient_sync_id') === patientSyncId);
    });
    if (!records.length) return;
    const section = document.createElement('div');
    section.className = 'mb-8 rounded-lg border border-amber-200 bg-amber-50 p-5';
    section.innerHTML = `<h3 class="font-semibold text-amber-900">Records pending synchronization</h3><div class="mt-3 flex flex-wrap gap-2">${records.map((record) => `<span class="rounded-full bg-white px-3 py-1 text-sm capitalize text-amber-800">${escapeHtml(record.type.replace(/_/g, ' '))}</span>`).join('')}</div>`;
    patientDetail.prepend(section);
  }

  function openFromHash() {
    const match = location.hash.match(/^#offline-patient=([a-f0-9-]+)$/i);
    if (match) openPatient(match[1]);
  }

  window.offlineQueue.ready.then(async () => {
    await renderLocalPatients();
    await renderPendingPatientActivity();
    openFromHash();
  });
  if (patientTable) {
    patientTable.addEventListener('click', (event) => {
      const link = event.target.closest('[data-offline-patient-view]');
      if (link && !navigator.onLine) {
        event.preventDefault();
        const syncId = link.dataset.offlinePatientView;
        history.replaceState(null, '', `${location.pathname}${location.search}#offline-patient=${syncId}`);
        openPatient(syncId);
      }
    });
  }
  window.addEventListener('hashchange', openFromHash);
  window.addEventListener('offlinequeuechange', renderLocalPatients);
})();
