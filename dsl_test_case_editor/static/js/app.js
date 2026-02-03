let currentProjectId = null;

const elements = {
  projectName: document.getElementById("project-name"),
  projectDesc: document.getElementById("project-desc"),
  projectSelect: document.getElementById("project-select"),
  createProject: document.getElementById("create-project"),
  openProject: document.getElementById("open-project"),
  currentProject: document.getElementById("current-project"),
  uploadType: document.getElementById("upload-type"),
  uploadFile: document.getElementById("upload-file"),
  uploadBtn: document.getElementById("upload-file-btn"),
  uploadStatus: document.getElementById("upload-status"),
  convertEnvDbc: document.getElementById("convert-env-dbc"),
  convertStatus: document.getElementById("convert-status"),
  mappingBody: document.getElementById("mapping-body"),
  saveMapping: document.getElementById("save-mapping"),
  mappingStatus: document.getElementById("mapping-status"),
  caseSelect: document.getElementById("case-select"),
  loadCase: document.getElementById("load-case"),
  caseName: document.getElementById("case-name"),
  saveCase: document.getElementById("save-case"),
  caseStatus: document.getElementById("case-status"),
  saveOss: document.getElementById("save-oss"),
  editor: document.getElementById("dsl-editor"),
  insertTemplate: document.getElementById("insert-template"),
  validate: document.getElementById("validate-case"),
  diagnostics: document.getElementById("diagnostics"),
  suggestionType: document.getElementById("suggestion-type"),
  suggestionQuery: document.getElementById("suggestion-query"),
  searchSuggestions: document.getElementById("search-suggestions"),
  suggestionList: document.getElementById("suggestion-list"),
  aiQuestion: document.getElementById("ai-question"),
  aiContext: document.getElementById("ai-context"),
  askAi: document.getElementById("ask-ai"),
  aiAnswer: document.getElementById("ai-answer"),
};

async function apiRequest(url, options = {}) {
  const response = await fetch(url, options);
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || response.statusText);
  }
  return response.json();
}

async function loadProjects() {
  const projects = await apiRequest("/api/projects");
  elements.projectSelect.innerHTML = "";
  projects.forEach((project) => {
    const option = document.createElement("option");
    option.value = project.project_id;
    option.textContent = `${project.name} (${project.project_id})`;
    elements.projectSelect.appendChild(option);
  });
}

async function createProject() {
  const name = elements.projectName.value.trim();
  const description = elements.projectDesc.value.trim();
  if (!name) {
    alert("Project name is required.");
    return;
  }
  const payload = { name, description: description || null };
  const project = await apiRequest("/api/projects", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  currentProjectId = project.project_id;
  elements.currentProject.textContent = currentProjectId;
  await loadProjects();
  await refreshProjectState();
}

async function openProject() {
  const projectId = elements.projectSelect.value;
  if (!projectId) {
    alert("Select a project first.");
    return;
  }
  currentProjectId = projectId;
  elements.currentProject.textContent = currentProjectId;
  await refreshProjectState();
}

async function refreshProjectState() {
  if (!currentProjectId) {
    return;
  }
  const config = await apiRequest(`/api/projects/${currentProjectId}`);
  const mappingResponse = await apiRequest(`/api/projects/${currentProjectId}/mapping`);
  renderMapping(config, mappingResponse.mapping || {});
  await loadCases();
}

function renderMapping(config, mapping) {
  elements.mappingBody.innerHTML = "";
  config.dbc_files.forEach((entry) => {
    const row = document.createElement("tr");
    const nameCell = document.createElement("td");
    nameCell.textContent = entry.file_name;
    const typeCell = document.createElement("td");
    typeCell.textContent = entry.file_type;
    const channelCell = document.createElement("td");
    const input = document.createElement("input");
    input.type = "number";
    input.min = "0";
    input.value = mapping[entry.file_name] !== undefined ? mapping[entry.file_name] : "";
    input.dataset.fileName = entry.file_name;
    channelCell.appendChild(input);
    row.appendChild(nameCell);
    row.appendChild(typeCell);
    row.appendChild(channelCell);
    elements.mappingBody.appendChild(row);
  });
}

async function saveMapping() {
  if (!currentProjectId) {
    alert("Open a project first.");
    return;
  }
  const mapping = {};
  elements.mappingBody.querySelectorAll("input").forEach((input) => {
    const value = input.value.trim();
    if (value !== "") {
      mapping[input.dataset.fileName] = Number(value);
    }
  });
  await apiRequest(`/api/projects/${currentProjectId}/mapping`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ mapping }),
  });
  elements.mappingStatus.textContent = "Mapping saved.";
}

async function uploadFile() {
  if (!currentProjectId) {
    alert("Open a project first.");
    return;
  }
  const file = elements.uploadFile.files[0];
  if (!file) {
    alert("Select a file to upload.");
    return;
  }
  const formData = new FormData();
  formData.append("file_type", elements.uploadType.value);
  formData.append("file", file);
  const response = await apiRequest(`/api/projects/${currentProjectId}/upload`, {
    method: "POST",
    body: formData,
  });
  elements.uploadStatus.textContent = `Uploaded ${response.file_name}.`;
  await refreshProjectState();
}

async function convertEnvDbc() {
  if (!currentProjectId) {
    alert("Open a project first.");
    return;
  }
  const response = await apiRequest(
    `/api/projects/${currentProjectId}/convert-env-dbc`,
    { method: "POST" }
  );
  elements.convertStatus.textContent = response.message || response.status;
}

async function loadCases() {
  if (!currentProjectId) {
    return;
  }
  const response = await apiRequest(`/api/projects/${currentProjectId}/cases`);
  elements.caseSelect.innerHTML = "";
  response.cases.forEach((caseName) => {
    const option = document.createElement("option");
    option.value = caseName;
    option.textContent = caseName;
    elements.caseSelect.appendChild(option);
  });
}

async function loadCase() {
  if (!currentProjectId) {
    alert("Open a project first.");
    return;
  }
  const caseName = elements.caseSelect.value;
  if (!caseName) {
    alert("Select a case first.");
    return;
  }
  const response = await apiRequest(
    `/api/projects/${currentProjectId}/cases/${encodeURIComponent(caseName)}`
  );
  elements.editor.value = response.content;
  elements.caseName.value = caseName;
}

function guessCaseFileName(content) {
  const match = content.match(/^CASE\s*:\s*(.+)$/m);
  if (!match) {
    return "";
  }
  const name = match[1].trim();
  if (!name) {
    return "";
  }
  return `${name}.dsl`;
}

async function saveCase() {
  if (!currentProjectId) {
    alert("Open a project first.");
    return;
  }
  let caseName = elements.caseName.value.trim();
  if (!caseName) {
    caseName = guessCaseFileName(elements.editor.value);
  }
  if (!caseName) {
    alert("Provide a case file name or a CASE line.");
    return;
  }
  if (!caseName.includes(".")) {
    caseName = `${caseName}.dsl`;
  }
  const payload = {
    content: elements.editor.value,
    save_to_oss: elements.saveOss.checked,
  };
  const response = await apiRequest(
    `/api/projects/${currentProjectId}/cases/${encodeURIComponent(caseName)}`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }
  );
  elements.caseStatus.textContent = response.message;
  await loadCases();
}

async function validateCase() {
  if (!currentProjectId) {
    alert("Open a project first.");
    return;
  }
  const payload = {
    project_id: currentProjectId,
    content: elements.editor.value,
  };
  const response = await apiRequest("/api/validate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  elements.diagnostics.innerHTML = "";
  if (response.diagnostics.length === 0) {
    elements.diagnostics.textContent = "No issues found.";
    return;
  }
  response.diagnostics.forEach((diag) => {
    const line = document.createElement("div");
    line.textContent = `${diag.severity.toUpperCase()} L${diag.line}: ${diag.message}`;
    elements.diagnostics.appendChild(line);
  });
}

async function searchSuggestions() {
  if (!currentProjectId) {
    alert("Open a project first.");
    return;
  }
  const type = elements.suggestionType.value;
  const query = elements.suggestionQuery.value.trim();
  const response = await apiRequest(
    `/api/suggestions?project_id=${encodeURIComponent(
      currentProjectId
    )}&type=${encodeURIComponent(type)}&q=${encodeURIComponent(query)}`
  );
  elements.suggestionList.innerHTML = "";
  response.suggestions.forEach((item) => {
    const li = document.createElement("li");
    li.textContent = item;
    li.addEventListener("click", () => {
      insertAtCursor(elements.editor, item);
    });
    elements.suggestionList.appendChild(li);
  });
}

function insertAtCursor(textarea, text) {
  const start = textarea.selectionStart;
  const end = textarea.selectionEnd;
  const before = textarea.value.substring(0, start);
  const after = textarea.value.substring(end);
  textarea.value = `${before}${text}${after}`;
  textarea.selectionStart = textarea.selectionEnd = start + text.length;
  textarea.focus();
}

async function askAi() {
  if (!currentProjectId) {
    alert("Open a project first.");
    return;
  }
  const question = elements.aiQuestion.value.trim();
  if (!question) {
    alert("Enter a question.");
    return;
  }
  const payload = {
    project_id: currentProjectId,
    question,
    context: elements.aiContext.value.trim() || null,
  };
  const response = await apiRequest("/api/ai/ask", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  elements.aiAnswer.textContent = response.answer;
}

function insertTemplate() {
  const template = `CASE: Sample_Case\nMETA: test_point=sample priority=P1 owner=auto scenario_id=0 scenario_name=sample\n\n[SET]\nS1: set sys::FunctionSwitch::CSW_Enable_S=0x1\n\n[CHECK]\nC1: check sig::CAN 0::ADC_0x29C::CSW_Stats_S==1 timeoutOfCheck 5s\n`;
  if (elements.editor.value.trim()) {
    const overwrite = confirm("Replace current content with template?");
    if (!overwrite) {
      return;
    }
  }
  elements.editor.value = template;
}

elements.createProject.addEventListener("click", createProject);
elements.openProject.addEventListener("click", openProject);
elements.uploadBtn.addEventListener("click", uploadFile);
elements.convertEnvDbc.addEventListener("click", convertEnvDbc);
elements.saveMapping.addEventListener("click", saveMapping);
elements.loadCase.addEventListener("click", loadCase);
elements.saveCase.addEventListener("click", saveCase);
elements.insertTemplate.addEventListener("click", insertTemplate);
elements.validate.addEventListener("click", validateCase);
elements.searchSuggestions.addEventListener("click", searchSuggestions);
elements.askAi.addEventListener("click", askAi);

loadProjects().catch((error) => {
  console.error(error);
});
