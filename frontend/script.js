// Detect environment and set API base URL
const API_BASE_URL = 
  process.env.REACT_APP_API_URL || 
  (typeof window !== 'undefined' && window.location.hostname === 'localhost' 
    ? 'http://localhost:8000/api/documents' 
    : 'https://quality-audit-api.onrender.com/api/documents');

// State
let currentFileType = "pdf"; // 'pdf' or 'docx'
const filesState = {
  ce1: null,
  ce2: null,
  ce3: null,
  rw: null,
};

// DOM elements
const pdfToggleBtn = document.getElementById("pdfToggle");
const docxToggleBtn = document.getElementById("docxToggle");
const resultsSection = document.getElementById("resultsSection");

const fileInputs = {
  ce1: document.getElementById("ce1File"),
  ce2: document.getElementById("ce2File"),
  ce3: document.getElementById("ce3File"),
  rw: document.getElementById("rwFile"),
};

const statusElements = {
  ce1: document.getElementById("ce1Status"),
  ce2: document.getElementById("ce2Status"),
  ce3: document.getElementById("ce3Status"),
  rw: document.getElementById("rwStatus"),
};

// Utility helpers
function resetResultCells() {
  const allCellIds = [
    "grammar-ce1",
    "grammar-ce2",
    "grammar-ce3",
    "grammar-rw",
    "title-val-ce1",
    "title-val-ce2",
    "title-val-ce3",
    "title-val-rw",
    "title-comp-ce1",
    "title-comp-ce2",
    "title-comp-ce3",
    "title-comp-rw",
    "format-comp-ce1",
    "format-comp-ce2",
    "format-comp-ce3",
    "format-comp-rw",
    "google-val-ce1",
    "google-val-ce2",
    "google-val-ce3",
    "google-val-rw",
    "visual-val-ce1",
    "visual-val-ce2",
    "visual-val-ce3",
    "visual-val-rw",
    "ai-math-ce1",
    "ai-math-ce2",
    "ai-math-ce3",
    "ai-math-rw",
    "reference-val-ce1",
    "reference-val-ce2",
    "reference-val-ce3",
    "reference-val-rw",
    "code-val-ce1",
    "code-val-ce2",
    "code-val-ce3",
    "code-val-rw",
    "grammar-ce1",
    "grammar-ce2",
    "grammar-ce3",
    "grammar-rw",
    "title-val-ce1",
    "title-val-ce2",
    "title-val-ce3",
    "title-val-rw",
    "title-comp-ce1",
    "title-comp-ce2",
    "title-comp-ce3",
    "title-comp-rw",
    "format-comp-ce1",
    "format-comp-ce2",
    "format-comp-ce3",
    "format-comp-rw",
    "google-val-ce1",
    "google-val-ce2",
    "google-val-ce3",
    "google-val-rw",
    "visual-val-ce1",
    "visual-val-ce2",
    "visual-val-ce3",
    "visual-val-rw",
    "ai-math-ce1",
    "ai-math-ce2",
    "ai-math-ce3",
    "ai-math-rw",
    "reference-val-ce1",
    "reference-val-ce2",
    "reference-val-ce3",
    "reference-val-rw",
    "code-val-ce1",
    "code-val-ce2",
    "code-val-ce3",
    "code-val-rw",
    "section-val-ce1",
    "section-val-ce2",
    "section-val-ce3",
    "section-val-rw",
    "accessibility-val-ce1",
    "accessibility-val-ce2",
    "accessibility-val-ce3",
    "accessibility-val-rw",
    "report-ce1",
    "report-ce2",
    "report-ce3",
    "report-rw",
  ];

  allCellIds.forEach((cellId) => {
    const cell = document.getElementById(cellId);
    if (cell) {
      // Clean up classes on the cell itself (just in case)
      cell.classList.remove("result-success", "result-error", "result-warning");
      cell.innerHTML = "-";
      cell.removeAttribute("title"); // Clear tooltips
    }
  });
}

function setAcceptForFileInputs() {
  const ext = currentFileType === "pdf" ? ".pdf" : ".docx";
  Object.values(fileInputs).forEach((input) => {
    input.value = "";
    input.setAttribute("accept", ext);
  });

  Object.values(statusElements).forEach((el) => {
    el.textContent = "";
    el.className = "upload-status";
  });

  // Reset labels
  document.querySelectorAll(".upload-card .file-name").forEach((el) => {
    el.textContent = "No file selected";
  });

  // Reset file state and button
  Object.keys(filesState).forEach((key) => (filesState[key] = null));
  updateCheckButtonState();
  hideResultsSection();
  resetResultCells();
}

function updateCheckButtonState() {
  const allSelected = Object.values(filesState).every((file) => !!file);

  // Show results section when all files are selected
  if (allSelected) {
    showResultsSection();
  } else {
    hideResultsSection();
  }
}

function showResultsSection() {
  resultsSection.style.display = "block";
}

function hideResultsSection() {
  resultsSection.style.display = "none";
}

function setCellLoading(cellId) {
  const cell = document.getElementById(cellId);
  if (!cell) return;
  // Ensure no residual classes on the cell
  cell.classList.remove("result-success", "result-error", "result-warning");
  cell.innerHTML = '<div class="loader"></div>';
}

function setCellResult(cellId, isSuccess) {
  const cell = document.getElementById(cellId);
  if (!cell) return;

  const resultClass = isSuccess ? "result-success" : "result-error";
  const text = isSuccess ? "Q" : "NQ";

  // Render badge inside span, NOT applying class to TD
  cell.innerHTML = `<span class="${resultClass}">${text}</span>`;
}

function setCellError(cellId) {
  setCellResult(cellId, false);
}

function getFileExtension(file) {
  if (!file || !file.name) return "";
  const parts = file.name.split(".");
  return parts.length > 1 ? "." + parts.pop().toLowerCase() : "";
}

function validateFileExtension(file) {
  const expectedExt = currentFileType === "pdf" ? ".pdf" : ".docx";
  return getFileExtension(file) === expectedExt;
}

async function postFormData(url, formData) {
  const response = await fetch(url, {
    method: "POST",
    body: formData,
  });

  if (!response.ok) {
    const text = await response.text().catch(() => "");
    throw new Error(
      `Request failed with status ${response.status}: ${
        text || response.statusText
      }`
    );
  }

  return response.json();
}

// ----- Grammar result interpretation -----
function isGrammarOk(data) {
  if (!data || !Array.isArray(data.results)) {
    // If structure is unexpected, treat as failure
    return false;
  }

  for (const segment of data.results) {
    const spellingErrors =
      Array.isArray(segment.spelling_errors) &&
      segment.spelling_errors.length > 0;
    const grammarErrors =
      Array.isArray(segment.grammar_errors) &&
      segment.grammar_errors.length > 0;

    if (spellingErrors || grammarErrors) {
      return false;
    }
  }
  return true;
}

// ----- API calls per task -----
async function runGrammarCheckForFile(key, file) {
  const cellIdMap = {
    ce1: "grammar-ce1",
    ce2: "grammar-ce2",
    ce3: "grammar-ce3",
    rw: "grammar-rw",
  };
  const cellId = cellIdMap[key];
  setCellLoading(cellId);

  if (!validateFileExtension(file)) {
    setCellError(cellId);
    return;
  }

  const endpoint =
    currentFileType === "pdf" ? "/pdf/grammar-check/" : "/docx/grammar-check/";

  const url = API_BASE_URL + endpoint;
  const formData = new FormData();
  formData.append("file", file);

  try {
    const data = await postFormData(url, formData);
    const ok = isGrammarOk(data);
    setCellResult(cellId, ok);
  } catch (err) {
    console.error("Grammar check error:", err);
    setCellError(cellId);
  }
}

async function runTitleValidationForFile(key, file) {
  const cellIdMap = {
    ce1: "title-val-ce1",
    ce2: "title-val-ce2",
    ce3: "title-val-ce3",
    rw: "title-val-rw",
  };
  const cellId = cellIdMap[key];
  setCellLoading(cellId);

  const url = API_BASE_URL + "/title/validate/";
  const formData = new FormData();
  formData.append("file", file);

  try {
    const data = await postFormData(url, formData);
    const ok = !!data.is_valid;
    setCellResult(cellId, ok);
  } catch (err) {
    console.error("Title validation error:", err);
    setCellError(cellId);
  }
}

// Title comparison: compare each CE file against RW as the reference
const titleComparisonState = {
  ce1: null,
  ce2: null,
  ce3: null,
};

function updateTitleComparisonRwCell() {
  const rwCellId = "title-comp-rw";
  const values = Object.values(titleComparisonState);
  if (values.some((v) => v === null)) {
    // Still loading at least one; keep loader
    setCellLoading(rwCellId);
    return;
  }
  const allMatch = values.every((v) => v === true);
  setCellResult(rwCellId, allMatch);
}
async function runTitleComparisonForFile(key, file, rwFile) {
  const cellIdMap = {
    ce1: "title-comp-ce1",
    ce2: "title-comp-ce2",
    ce3: "title-comp-ce3",
  };
  const cellId = cellIdMap[key];
  setCellLoading(cellId);

  const url = API_BASE_URL + "/title/compare/";
  const formData = new FormData();
  formData.append("file_1", file);
  formData.append("file_2", rwFile);

  try {
    const data = await postFormData(url, formData);
    const match = !!data.match;
    titleComparisonState[key] = match;
    setCellResult(cellId, match);
  } catch (err) {
    console.error("Title comparison error:", err);
    titleComparisonState[key] = false;
    setCellError(cellId);
  } finally {
    updateTitleComparisonRwCell();
  }
}

async function runFormatComparison(files) {
  const ce1Cell = "format-comp-ce1";
  const ce2Cell = "format-comp-ce2";
  const ce3Cell = "format-comp-ce3";
  const rwCell = "format-comp-rw";

  setCellLoading(ce1Cell);
  setCellLoading(ce2Cell);
  setCellLoading(ce3Cell);
  setCellLoading(rwCell);

  // First comparison: CE1, CE2, CE3
  const url = API_BASE_URL + "/format/compare/";
  const formDataMain = new FormData();
  formDataMain.append("file_1", files.ce1);
  formDataMain.append("file_2", files.ce2);
  formDataMain.append("file_3", files.ce3);

  try {
    const data = await postFormData(url, formDataMain);
    const allMatch =
      data &&
      data.consistency &&
      Object.prototype.hasOwnProperty.call(data.consistency, "all_match")
        ? !!data.consistency.all_match
        : false;

    setCellResult(ce1Cell, allMatch);
    setCellResult(ce2Cell, allMatch);
    setCellResult(ce3Cell, allMatch);
  } catch (err) {
    console.error("Format comparison (CE1-CE3) error:", err);
    setCellError(ce1Cell);
    setCellError(ce2Cell);
    setCellError(ce3Cell);
  }

  // Second comparison to evaluate RW formatting with others (CE1, CE2, RW)
  const formDataRw = new FormData();
  formDataRw.append("file_1", files.ce1);
  formDataRw.append("file_2", files.ce2);
  formDataRw.append("file_3", files.rw);

  try {
    const dataRw = await postFormData(url, formDataRw);
    const allMatchRw =
      dataRw &&
      dataRw.consistency &&
      Object.prototype.hasOwnProperty.call(dataRw.consistency, "all_match")
        ? !!dataRw.consistency.all_match
        : false;

    setCellResult(rwCell, allMatchRw);
  } catch (err) {
    console.error("Format comparison (with RW) error:", err);
    setCellError(rwCell);
  }
}

async function runGoogleValidationForFile(key, file) {
  const cellIdMap = {
    ce1: "google-val-ce1",
    ce2: "google-val-ce2",
    ce3: "google-val-ce3",
    rw: "google-val-rw",
  };
  const cellId = cellIdMap[key];
  setCellLoading(cellId);

  const url = API_BASE_URL + "/validate-google-search/";
  const formData = new FormData();
  formData.append("file", file);

  try {
    const data = await postFormData(url, formData);

    const hasResults =
      data && Array.isArray(data.results) && data.results.length > 0;

    if (!hasResults) {
      const cell = document.getElementById(cellId);
      if (cell) {
        // Render error badge
        cell.innerHTML = '<span class="result-error">No Results</span>';
      }
      return;
    }

    // Calculate average confidence
    const confidenceCounts = {
      High: 0,
      Medium: 0,
      Low: 0,
    };

    data.results.forEach((r) => {
      const label = r.confidence_label || "Low";
      if (confidenceCounts.hasOwnProperty(label)) {
        confidenceCounts[label]++;
      }
    });

    // Determine overall confidence level
    let overallConfidence = "Low";
    const totalResults = data.results.length;
    const highPercentage = (confidenceCounts.High / totalResults) * 100;
    const mediumPercentage = (confidenceCounts.Medium / totalResults) * 100;

    if (highPercentage >= 60) {
      overallConfidence = "High";
    } else if (highPercentage + mediumPercentage >= 60) {
      overallConfidence = "Medium";
    }

    // Display the confidence level
    const cell = document.getElementById(cellId);
    if (cell) {
      if (overallConfidence === "High") {
        cell.innerHTML = '<span class="result-success">Q</span>';
      } else if (overallConfidence === "Medium") {
        cell.innerHTML = '<span class="result-warning">NQ</span>';
      } else {
        cell.innerHTML = '<span class="result-error">NQ</span>';
      }
    }
  } catch (err) {
    console.error("Google validation error:", err);
    setCellError(cellId);
  }
}

// ----- Main orchestration for individual tasks -----
async function runGrammarCheck() {
  const files = { ...filesState };
  const cellIds = ["grammar-ce1", "grammar-ce2", "grammar-ce3", "grammar-rw"];
  cellIds.forEach(setCellLoading);

  const promises = Object.entries(files).map(([key, file]) =>
    runGrammarCheckForFile(key, file)
  );

  await Promise.allSettled(promises);
}

async function runTitleValidation() {
  const files = { ...filesState };
  const cellIds = [
    "title-val-ce1",
    "title-val-ce2",
    "title-val-ce3",
    "title-val-rw",
  ];
  cellIds.forEach(setCellLoading);

  const promises = Object.entries(files).map(([key, file]) =>
    runTitleValidationForFile(key, file)
  );

  await Promise.allSettled(promises);
}

async function runTitleComparison() {
  const files = { ...filesState };
  const cellIds = [
    "title-comp-ce1",
    "title-comp-ce2",
    "title-comp-ce3",
    "title-comp-rw",
  ];
  cellIds.forEach(setCellLoading);

  // Reset title comparison state
  titleComparisonState.ce1 = null;
  titleComparisonState.ce2 = null;
  titleComparisonState.ce3 = null;

  const promises = ["ce1", "ce2", "ce3"].map((key) =>
    runTitleComparisonForFile(key, files[key], files.rw)
  );

  await Promise.allSettled(promises);
}

async function runFormatComparisonTask() {
  const files = { ...filesState };
  const cellIds = [
    "format-comp-ce1",
    "format-comp-ce2",
    "format-comp-ce3",
    "format-comp-rw",
  ];
  cellIds.forEach(setCellLoading);

  await runFormatComparison(files);
}

async function runGoogleValidation() {
  const files = { ...filesState };
  const cellIds = [
    "google-val-ce1",
    "google-val-ce2",
    "google-val-ce3",
    "google-val-rw",
  ];
  cellIds.forEach(setCellLoading);

  const promises = Object.entries(files).map(([key, file]) =>
    runGoogleValidationForFile(key, file)
  );

  await Promise.allSettled(promises);
}

async function runReferenceValidation() {
  const files = { ...filesState };
  // Explicitly map keys to cell IDs to ensure we set loading states correctly
  const cellIdMap = {
    ce1: "reference-val-ce1",
    ce2: "reference-val-ce2",
    ce3: "reference-val-ce3",
    rw: "reference-val-rw",
  };

  // Set loaders for all cells associated with the files
  Object.values(cellIdMap).forEach(setCellLoading);

  const promises = Object.entries(files).map(([key, file]) =>
    runReferenceValidationForFile(key, file)
  );

  await Promise.allSettled(promises);
}

async function runReferenceValidationForFile(key, file) {
  const cellIdMap = {
    ce1: "reference-val-ce1",
    ce2: "reference-val-ce2",
    ce3: "reference-val-ce3",
    rw: "reference-val-rw",
  };
  const cellId = cellIdMap[key];
  const cell = document.getElementById(cellId);
  if (!cell) return;

  setCellLoading(cellId);

  // 1. Validation Checks (as fixed previously)
  if (!file) {
    console.warn(`[${key}] No file provided for reference validation.`);
    setCellError(cellId);
    return;
  }
  if (!validateFileExtension(file)) {
    console.warn(`[${key}] Invalid file extension.`);
    setCellError(cellId);
    cell.title = "Invalid file type.";
    return;
  }

  const url = API_BASE_URL + "/reference/validate/";
  const formData = new FormData();
  formData.append("file", file);

  try {
    const data = await postFormData(url, formData);

    const report = data.report || {};
    const details = Array.isArray(report.details) ? report.details : [];
    const totalRefs = report.total_references_found || 0;

    // Calculate invalid count by checking the inner validation objects
    let invalidCount = 0;
    details.forEach((ref) => {
      // Check Timeline
      const isTimelineValid =
        ref.timeline_validation && ref.timeline_validation.is_valid;
      // Check Format
      const isFormatValid =
        ref.format_validation && ref.format_validation.is_valid;

      // If either fails, the reference is invalid
      if (!isTimelineValid || !isFormatValid) {
        invalidCount++;
      }
    });

    // Rule: Qualified (Q) if at least 1 reference exists AND 0 are invalid
    const isValid = totalRefs > 0 && invalidCount === 0;

    setCellResult(cellId, isValid);

    // Update Tooltip
    if (isValid) {
      cell.title = `All ${totalRefs} reference(s) are valid.`;
    } else {
      if (totalRefs === 0) {
        cell.title = "No references found in the document.";
      } else {
        cell.title = `Found ${invalidCount} invalid reference(s) out of ${totalRefs} total.`;
      }
    }

    console.log(`[${key}] Reference Check:`, {
      total: totalRefs,
      invalid: invalidCount,
      pass: isValid,
    });
  } catch (err) {
    console.error(`Reference validation error for ${key}:`, err);
    setCellError(cellId);
    cell.title = "Error connecting to validation service.";
  }
}

async function runVisualValidation() {
  const files = { ...filesState };
  const cellIds = [
    "visual-val-ce1",
    "visual-val-ce2",
    "visual-val-ce3",
    "visual-val-rw",
  ];
  cellIds.forEach(setCellLoading);

  const promises = Object.entries(files).map(([key, file]) =>
    runVisualValidationForFile(key, file)
  );

  await Promise.allSettled(promises);
}

// ----- Event wiring -----
function initFileInputHandlers() {
  Object.entries(fileInputs).forEach(([key, input]) => {
    input.addEventListener("change", (event) => {
      const file = event.target.files[0];
      handleFileForKey(key, file);
    });
  });
}
async function runVisualValidationForFile(key, file) {
  const cellIdMap = {
    ce1: "visual-val-ce1",
    ce2: "visual-val-ce2",
    ce3: "visual-val-ce3",
    rw: "visual-val-rw",
  };
  const cellId = cellIdMap[key];
  const cell = document.getElementById(cellId);
  if (!cell) return;

  setCellLoading(cellId);

  const url = API_BASE_URL + "/visuals/validate/";
  const formData = new FormData();
  formData.append("file", file);

  try {
    const data = await postFormData(url, formData);

    // 1. Get the report object
    const report = data.validation_report || {};

    // We default to an empty array if it doesn't exist
    const allDuplicates = Array.isArray(report.duplicates)
      ? report.duplicates
      : [];

    // 3. Filter the list to count images vs tables (for the tooltip)
    const duplicateImages = allDuplicates.filter(
      (item) => item.type === "Image"
    );
    const duplicateTables = allDuplicates.filter(
      (item) => item.type === "Table"
    );

    // 4. Determine success (Fail if ANY duplicates exist)
    const hasDuplicates = allDuplicates.length > 0;
    const isSuccess = !hasDuplicates;

    // Update UI
    setCellResult(cellId, isSuccess);

    // Update Tooltip (color is handled by setCellResult)
    if (hasDuplicates) {
      cell.title = `Found ${duplicateImages.length} duplicate image(s) and ${duplicateTables.length} duplicate table(s).`;
    } else {
      cell.title = "No duplicate images or tables found.";
    }

    console.log(`[${key}] Visual Check:`, {
      totalDuplicates: allDuplicates.length,
      images: duplicateImages.length,
      tables: duplicateTables.length,
      pass: isSuccess,
    });
  } catch (err) {
    console.error(`Visual validation error for ${key}:`, err);
    setCellError(cellId);
    cell.title = "Error connecting to validation service.";
  }
}

async function runAiMathValidationForFile(key, file) {
  const cellIdMap = {
    ce1: "ai-math-ce1",
    ce2: "ai-math-ce2",
    ce3: "ai-math-ce3",
    rw: "ai-math-rw",
  };
  const cellId = cellIdMap[key];
  const cell = document.getElementById(cellId);
  if (!cell) return;

  setCellLoading(cellId);

  const url = API_BASE_URL + "/validate-math-gemini/";
  const formData = new FormData();
  formData.append("file", file);

  try {
    const data = await postFormData(url, formData);

    // Check for overall assessment
    if (data && data.overall_assessment) {
      const confidence = data.overall_assessment.average_confidence;
      const accuracy = data.overall_assessment.accuracy_percentage;

      let badgeClass = "result-error";
      if (confidence >= 0.9) {
        badgeClass = "result-success";
      } else if (confidence >= 0.7) {
        badgeClass = "result-warning";
      }

      // Render as badge in span
      cell.innerHTML = `<span class="${badgeClass}">${(
        accuracy
      ).toFixed(0)}%</span>`;

      // Tooltip with more details
      cell.title = `Accuracy: ${accuracy}%\nCorrect: ${data.overall_assessment.correct_calculations}\nIncorrect: ${data.overall_assessment.incorrect_calculations}`;
    } else {
      setCellError(cellId);
      cell.title = "Invalid response format";
    }
  } catch (err) {
    console.error(`AI Math validation error for ${key}:`, err);
    setCellError(cellId);
    cell.title = "Error connecting to validation service.";
  }
}

async function runAiMathValidation() {
  const files = { ...filesState };
  const cellIds = ["ai-math-ce1", "ai-math-ce2", "ai-math-ce3", "ai-math-rw"];
  cellIds.forEach(setCellLoading);

  const promises = Object.entries(files).map(([key, file]) =>
    runAiMathValidationForFile(key, file)
  );

  await Promise.allSettled(promises);
}

async function runCodeValidationForFile(key, file) {
  const cellIdMap = {
    ce1: "code-val-ce1",
    ce2: "code-val-ce2",
    ce3: "code-val-ce3",
    rw: "code-val-rw",
  };
  const cellId = cellIdMap[key];
  const cell = document.getElementById(cellId);
  if (!cell) return;

  setCellLoading(cellId);

  const url = API_BASE_URL + "/validate-code/";
  const formData = new FormData();
  formData.append("file", file);

  try {
    const data = await postFormData(url, formData);

    if (data.status === "success" && data.total_code_snippets_found === 0) {
      cell.innerHTML = '<span class="result-warning">No Code</span>';
      cell.title = "No code snippets found in document";
      return;
    }

    if (data && data.overall_assessment) {
      const confidence = data.overall_assessment.average_confidence;
      const accuracy = data.overall_assessment.accuracy_percentage;
      const validSnippets = data.overall_assessment.valid_snippets;
      const invalidSnippets = data.overall_assessment.invalid_snippets;
      const totalSnippets = data.total_code_snippets_found;

      let badgeClass = "result-error";

      if (accuracy >= 80) {
        badgeClass = "result-success";
      } else if (accuracy >= 60) {
        badgeClass = "result-warning";
      }

      cell.innerHTML = `<span class="${badgeClass}">${accuracy.toFixed(
        0
      )}%</span>`;

      cell.title = `Code Quality: ${accuracy}%\nValid: ${validSnippets}/${totalSnippets}\nInvalid: ${invalidSnippets}/${totalSnippets}\nAccuracy: ${accuracy.toFixed(
        0
      )}%`;
    } else if (data.status === "error") {
      setCellError(cellId);
      cell.title = data.message || "Validation failed";
    } else {
      setCellError(cellId);
      cell.title = "Invalid response format";
    }
  } catch (err) {
    console.error(`Code validation error for ${key}:`, err);
    setCellError(cellId);
    cell.title = "Error connecting to validation service.";
  }
}

async function runCodeValidation() {
  const files = { ...filesState };
  const cellIds = [
    "code-val-ce1",
    "code-val-ce2",
    "code-val-ce3",
    "code-val-rw",
  ];
  cellIds.forEach(setCellLoading);

  const promises = Object.entries(files).map(([key, file]) =>
    runCodeValidationForFile(key, file)
  );

  await Promise.allSettled(promises);
}

// ----- Section Validation -----
async function runSectionValidationForFile(key, file) {
  const cellIdMap = {
    ce1: "section-val-ce1",
    ce2: "section-val-ce2",
    ce3: "section-val-ce3",
    rw: "section-val-rw",
  };
  const cellId = cellIdMap[key];
  const cell = document.getElementById(cellId);
  if (!cell) return;

  setCellLoading(cellId);

  const url = API_BASE_URL + "/section/validate/";
  const formData = new FormData();
  formData.append("file", file);

  try {
    const data = await postFormData(url, formData);

    const completenessScore = data.completeness_score || 0;

    // Determine result based on completeness score
    let isSuccess = completenessScore >= 75;

    setCellResult(cellId, isSuccess);

    // Update tooltip with details
    const missingCount = (data.missing_sections || []).length;
    const presentCount = (data.present_sections || []).length;

    if (completenessScore >= 100) {
      cell.title = `All required sections present (${presentCount}/${presentCount})`;
    } else {
      cell.title = `Completeness: ${completenessScore.toFixed(
        0
      )}%\nPresent: ${presentCount}\nMissing: ${missingCount}`;
    }
  } catch (err) {
    console.error(`Section validation error for ${key}:`, err);
    setCellError(cellId);
    cell.title = "Error connecting to validation service.";
  }
}

async function runSectionValidation() {
  const files = { ...filesState };
  const cellIds = [
    "section-val-ce1",
    "section-val-ce2",
    "section-val-ce3",
    "section-val-rw",
  ];
  cellIds.forEach(setCellLoading);

  const promises = Object.entries(files).map(([key, file]) =>
    runSectionValidationForFile(key, file)
  );

  await Promise.allSettled(promises);
}

async function runAccessibilityValidationForFile(key, file) {
  const cellIdMap = {
    ce1: "accessibility-val-ce1",
    ce2: "accessibility-val-ce2",
    ce3: "accessibility-val-ce3",
    rw: "accessibility-val-rw",
  };
  const cellId = cellIdMap[key];
  const cell = document.getElementById(cellId);
  if (!cell) return;

  setCellLoading(cellId);

  const url = API_BASE_URL + "/accessibility/validate/";
  const formData = new FormData();
  formData.append("file", file);

  try {
    const data = await postFormData(url, formData);

    if (data && data.status === "success" && data.report) {
      const report = data.report;

      const isAccessible = !!report.is_compliant;

      setCellResult(cellId, isAccessible);

      const issues = report.issues || [];
      const issueCount = report.total_issues || issues.length;

      // Construct a tooltip string
      let tooltipText = "";
      if (isAccessible) {
        tooltipText = "Pass: Document is accessible.\nNo issues found.";
      } else {
        tooltipText = `NQ: Issues Found: ${issueCount}`;
      }

      cell.title = tooltipText;
    } else {
      // Handle cases where API returns 200 but status is not success
      console.warn("Validation returned unexpected structure:", data);
      setCellError(cellId);
      cell.title = "Invalid response format from server";
    }
  } catch (err) {
    console.error(`Accessibility validation error for ${key}:`, err);
    setCellError(cellId);
    cell.title = "Error connecting to validation service.";
  }
}
async function runAccessibilityValidation() {
  const files = { ...filesState };
  const cellIds = [
    "accessibility-val-ce1",
    "accessibility-val-ce2",
    "accessibility-val-ce3",
    "accessibility-val-rw",
  ];
  cellIds.forEach(setCellLoading);

  const promises = Object.entries(files).map(([key, file]) =>
    runAccessibilityValidationForFile(key, file)
  );

  await Promise.allSettled(promises);
}

// ----- Report Generation -----
async function runGenerateReportForFile(key, file) {
  const cellIdMap = {
    ce1: "report-ce1",
    ce2: "report-ce2",
    ce3: "report-ce3",
    rw: "report-rw",
  };
  const cellId = cellIdMap[key];
  const cell = document.getElementById(cellId);
  if (!cell) return;

  setCellLoading(cellId);

  const url = API_BASE_URL + "/report/generate/";
  const formData = new FormData();
  formData.append("file", file);

  try {
    const response = await fetch(url, {
      method: "POST",
      body: formData,
    });

    if (!response.ok) {
      throw new Error(`Request failed with status ${response.status}`);
    }

    // Get the HTML content
    const htmlContent = await response.text();

    // Open in new window
    const reportWindow = window.open("", "_blank");
    if (reportWindow) {
      reportWindow.document.write(htmlContent);
      reportWindow.document.close();

      // Mark as success
      cell.innerHTML = '<span class="result-success">View</span>';
      cell.style.cursor = "pointer";
      cell.title = "Click to view report again";

      // Store HTML for re-opening
      cell.dataset.reportHtml = htmlContent;

      // Add click handler to re-open report
      cell.onclick = () => {
        const newWindow = window.open("", "_blank");
        if (newWindow) {
          newWindow.document.write(cell.dataset.reportHtml);
          newWindow.document.close();
        }
      };
    } else {
      // Popup blocked
      cell.innerHTML = '<span class="result-warning">Blocked</span>';
      cell.title = "Popup blocked. Please allow popups and try again.";
    }
  } catch (err) {
    console.error(`Report generation error for ${key}:`, err);
    setCellError(cellId);
    cell.title = "Error generating report.";
  }
}

async function runGenerateReport() {
  const files = { ...filesState };
  const cellIds = ["report-ce1", "report-ce2", "report-ce3", "report-rw"];
  cellIds.forEach(setCellLoading);

  const promises = Object.entries(files).map(([key, file]) =>
    runGenerateReportForFile(key, file)
  );

  await Promise.allSettled(promises);
}

function initToggleHandlers() {
  pdfToggleBtn.addEventListener("click", () => {
    if (currentFileType === "pdf") return;
    currentFileType = "pdf";
    pdfToggleBtn.classList.add("active");
    docxToggleBtn.classList.remove("active");
    setAcceptForFileInputs();
  });

  docxToggleBtn.addEventListener("click", () => {
    if (currentFileType === "docx") return;
    currentFileType = "docx";
    docxToggleBtn.classList.add("active");
    pdfToggleBtn.classList.remove("active");
    setAcceptForFileInputs();
  });
}

function initRunButtons() {
  const runButtons = document.querySelectorAll(".run-btn");
  runButtons.forEach((btn) => {
    btn.addEventListener("click", async () => {
      const task = btn.getAttribute("data-task");

      // Check if all files are uploaded
      const allFilesUploaded = Object.values(filesState).every(
        (file) => !!file
      );
      if (!allFilesUploaded) {
        alert("Please upload all files before running checks.");
        return;
      }

      // Disable button during execution
      btn.disabled = true;
      btn.innerHTML = '<i class="ph ph-spinner ph-spin"></i> Running...';

      try {
        switch (task) {
          case "grammar":
            await runGrammarCheck();
            break;
          case "title-validation":
            await runTitleValidation();
            break;
          case "title-comparison":
            await runTitleComparison();
            break;
          case "format-comparison":
            await runFormatComparisonTask();
            break;
          case "google-validation":
            await runGoogleValidation();
            break;
          case "visual-validation":
            await runVisualValidation();
            break;
          case "ai-math-validation":
            await runAiMathValidation();
            break;
          case "reference-validation":
            await runReferenceValidation();
            break;
          case "code-validation":
            await runCodeValidation();
            break;
          case "section-validation":
            await runSectionValidation();
            break;
          case "accessibility-validation":
            await runAccessibilityValidation();
            break;
          case "generate-report":
            await runGenerateReport();
            break;
          default:
            console.error("Unknown task:", task);
        }
      } catch (error) {
        console.error("Error running task:", error);
      } finally {
        btn.disabled = false;
        btn.innerHTML = '<i class="ph ph-play"></i> Run';
      }
    });
  });
}

// ----- Drag and Drop Handlers -----
function handleFileForKey(key, file) {
  const statusEl = statusElements[key];
  const input = fileInputs[key];
  const card = document.querySelector(`.upload-card[data-file-key="${key}"]`);

  if (!file) {
    statusEl.textContent = "";
    statusEl.className = "upload-status";
    filesState[key] = null;
    return;
  }

  // Update file name display
  const label = card.querySelector(".file-name");
  if (label) {
    label.textContent = file.name;
    // Add tooltip if name is truncated
    label.title = file.name;
  }

  // Validate file extension
  if (!validateFileExtension(file)) {
    statusEl.textContent = "Invalid file type";
    statusEl.className = "upload-status error";
    filesState[key] = null;
    if (input) input.value = "";
  } else {
    statusEl.textContent = "File selected";
    statusEl.className = "upload-status success";
    filesState[key] = file;
  }

  updateCheckButtonState();
}

function initDragDropHandlers() {
  const uploadCards = document.querySelectorAll(".upload-card");

  uploadCards.forEach((card) => {
    const fileKey = card.getAttribute("data-file-key");
    if (!fileKey) return;

    // Prevent default drag behaviors on the card
    ["dragenter", "dragover", "dragleave", "drop"].forEach((eventName) => {
      card.addEventListener(eventName, (e) => {
        e.preventDefault();
        e.stopPropagation();
      });
    });

    // Highlight effect on drag enter/over
    ["dragenter", "dragover"].forEach((eventName) => {
      card.addEventListener(eventName, () => {
        card.classList.add("drag-over");
      });
    });

    // Remove highlight on drag leave/drop
    ["dragleave", "drop"].forEach((eventName) => {
      card.addEventListener(eventName, () => {
        card.classList.remove("drag-over");
      });
    });

    // Handle file drop
    card.addEventListener("drop", (e) => {
      const dt = e.dataTransfer;
      const files = dt.files;

      if (files.length > 0) {
        const file = files[0];
        handleFileForKey(fileKey, file);
      }
    });
  });

  // Prevent default drag behavior on the whole document
  // to avoid browser opening the file
  ["dragenter", "dragover", "dragleave", "drop"].forEach((eventName) => {
    document.body.addEventListener(eventName, (e) => {
      e.preventDefault();
      e.stopPropagation();
    });
  });
}

function init() {
  initFileInputHandlers();
  initDragDropHandlers();
  initToggleHandlers();
  initRunButtons();
  setAcceptForFileInputs();
}

document.addEventListener("DOMContentLoaded", init);
