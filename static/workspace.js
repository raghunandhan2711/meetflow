const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const escape = (value = "") =>
  String(value).replace(
    /[&<>"']/g,
    (character) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        character
      ],
  );
const paths = {
  wave: '<path d="M3 10v4M7 6v12M11 3v18M15 7v10M19 5v14M23 10v4"/>',
  dashboard:
    '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',
  library:
    '<rect x="4" y="3" width="15" height="18" rx="2"/><path d="M8 7h7M8 11h7M8 15h4M1 7v14"/>',
  check:
    '<rect x="3" y="3" width="18" height="18" rx="3"/><path d="m7 12 3 3 7-7"/>',
  branch:
    '<circle cx="6" cy="5" r="2"/><circle cx="18" cy="6" r="2"/><circle cx="6" cy="19" r="2"/><path d="M6 7v10M18 8v2a5 5 0 0 1-5 5H6"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  arrow: '<path d="M4 12h15m-6-6 6 6-6 6"/>',
  search: '<circle cx="10" cy="10" r="6"/><path d="m15 15 5 5"/>',
  mic: '<rect x="9" y="2" width="6" height="13" rx="3"/><path d="M5 10v2a7 7 0 0 0 14 0v-2M12 19v3M9 22h6"/>',
  upload:
    '<path d="M12 16V3m-5 5 5-5 5 5M4 15v5a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-5"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  people:
    '<circle cx="9" cy="8" r="3"/><path d="M3 21v-3a6 6 0 0 1 12 0v3M16 5a3 3 0 0 1 0 6M18 15a5 5 0 0 1 3 5"/>',
  download: '<path d="M12 3v13m-5-5 5 5 5-5M4 17v4h16v-4"/>',
  shield:
    '<path d="m12 2 8 3v6c0 5-4 8-8 11-4-3-8-6-8-11V5l8-3Z"/><path d="m8 12 3 3 5-6"/>',
  note: '<path d="M5 3h10l4 4v14H5V3Zm10 0v5h4M8 12h8M8 16h6"/>',
  back: '<path d="M20 12H4m6-6-6 6 6 6"/>',
  calendar:
    '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M7 2v6M17 2v6M3 11h18"/>',
  external: '<path d="M14 3h7v7m0-7L10 14M10 3H3v18h18v-7"/>',
  edit: '<path d="m14 4 6 6M4 20l4-1L21 6l-4-4L4 15v5Z"/>',
  trash: '<path d="M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7M14 10v7"/>',
  bolt: '<path d="m13 2-8 12h6l-1 8 9-13h-7l1-7Z"/>',
};
const icon = (name) =>
  `<svg viewBox="0 0 24 24" aria-hidden="true">${paths[name] || paths.note}</svg>`;
$$("[data-icon]").forEach(
  (element) => (element.innerHTML = icon(element.dataset.icon)),
);
const state = {
  page: "dashboard",
  meetings: [],
  settings: {},
  meeting: null,
  tab: "overview",
  search: "",
  filter: "all",
  board: false,
};
const activeStatuses = ["queued", "transcribing", "analyzing"];
const date = (value) =>
  new Date(value).toLocaleDateString("en-IN", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
const time = (seconds) =>
  `${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(Math.floor(seconds % 60)).padStart(2, "0")}`;
const initials = (name) =>
  name
    .split(/\s+/)
    .map((word) => word[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();
const allTasks = () =>
  state.meetings.flatMap((meeting) =>
    meeting.tasks.map((task) => ({
      ...task,
      meeting_title: meeting.title,
      meeting_id: meeting.id,
    })),
  );
let toastTimer,
  searchTimer,
  searchVersion = 0,
  polling = false,
  confirmation = null;
async function api(path, options = {}) {
  const response = await fetch("/api" + path, {
    ...options,
    headers:
      options.body instanceof FormData
        ? options.headers
        : { "Content-Type": "application/json", ...options.headers },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(
      typeof body.detail === "string"
        ? body.detail
        : "Check the entered values and try again.",
    );
  }
  return response.json();
}
function toast(message) {
  clearTimeout(toastTimer);
  $("#toast").textContent = message;
  $("#toast").classList.add("visible");
  toastTimer = setTimeout(() => $("#toast").classList.remove("visible"), 5500);
}
function heading(label, title, description, actions = "") {
  return `<div class="page-heading"><div><span class="eyebrow">${label}</span><h1>${title}</h1><p>${description}</p></div><div class="heading-actions">${actions}</div></div>`;
}
function pill(meeting) {
  const labels = {
    ready: "Analyzed",
    transcribed: "Transcript ready",
    queued: "Queued",
    transcribing: "Transcribing",
    analyzing: "Analyzing",
    failed: "Needs attention",
  };
  const style =
    meeting.status === "failed"
      ? "failed"
      : meeting.status === "transcribed"
        ? "transcribed"
        : activeStatuses.includes(meeting.status)
          ? "processing"
          : "";
  return `<span class="pill ${style}"><span class="status-dot"></span>${labels[meeting.status] || escape(meeting.status)}</span>`;
}
async function refresh() {
  state.meetings = await api("/meetings");
  $("#meeting-count").textContent = state.meetings.length;
  $("#task-count").textContent = allTasks().filter(
    (task) => task.status !== "done",
  ).length;
}
function navigate(page) {
  location.hash = page;
}
let routeVersion = 0;
async function route() {
  const version = ++routeVersion;
  const parts = location.hash.slice(1).split("/");
  const page = parts[0] || "dashboard";
  try {
    if (page === "meeting" && parts[1]) {
      const meeting = await api("/meetings/" + encodeURIComponent(parts[1]));
      if (version !== routeVersion) return;
      state.meeting = meeting;
      state.page = "meetings";
      state.tab = ["overview", "transcript", "actions"].includes(parts[2])
        ? parts[2]
        : "overview";
    } else {
      state.page = ["dashboard", "meetings", "tasks", "decisions"].includes(
        page,
      )
        ? page
        : "dashboard";
      state.meeting = null;
      state.search = "";
      searchVersion++;
      clearTimeout(searchTimer);
    }
    $$("[data-nav]").forEach((button) =>
      button.classList.toggle("active", button.dataset.nav === state.page),
    );
    $("#page-name").textContent = state.meeting
      ? "Meeting notes"
      : {
          dashboard: "Overview",
          meetings: "Meeting archive",
          tasks: "Action items",
          decisions: "Decision log",
        }[state.page];
    render();
    window.scrollTo(0, 0);
  } catch (error) {
    toast(error.message);
    navigate("meetings");
  }
}
function render() {
  if (state.meeting) return renderMeeting();
  ({
    dashboard: renderDashboard,
    meetings: renderLibrary,
    tasks: renderTasks,
    decisions: renderDecisions,
  })[state.page]();
}
function metrics() {
  const meetings = state.meetings;
  const tasks = allTasks();
  return `<div class="overview">${[
    ["library", "Meetings", meetings.length],
    [
      "check",
      "Open action items",
      tasks.filter((task) => task.status !== "done").length,
    ],
    [
      "branch",
      "Decisions recorded",
      meetings.reduce((total, meeting) => total + meeting.decisions.length, 0),
    ],
    [
      "external",
      "Jira issues created",
      tasks.filter((task) => task.jira_key).length,
    ],
  ]
    .map(
      ([symbol, label, count]) =>
        `<div class="metric"><div class="metric-icon">${icon(symbol)}</div><div><span class="label">${label}</span><strong>${String(count).padStart(2, "0")}</strong></div></div>`,
    )
    .join("")}</div>`;
}
function renderDashboard() {
  const bars = [
    16, 24, 37, 21, 45, 60, 38, 52, 68, 40, 28, 48, 34, 59, 43, 26, 37, 18, 29,
    13,
  ]
    .map((height, index) => `<span class="bar-${index}"></span>`)
    .join("");
  $("#content").innerHTML =
    `<section class="hero"><div><span class="eyebrow">YOUR NEXT CHAPTER STARTS HERE</span><h1>Good conversations.<br><em>Real progress.</em></h1><p>Bring the conversation. Find the decisions. Give every next step a home. Your meeting-to-action workspace starts here.</p><div class="heading-actions"><button class="button primary" data-capture="upload">${icon("upload")}Upload a meeting</button><button class="button secondary" data-capture="record">${icon("mic")}Record a meeting</button></div></div><div class="hero-visual"><div class="capture-card-top"><span>✳ YOUR NEXT GOOD IDEA STARTS HERE</span><span class="status-dot"></span></div><h2>Bring the conversation.<br><em>We’ll help with the rest.</em></h2><p>Choose how you’d like to start.</p><div class="capture-card-options"><button data-capture="upload"><span class="capture-card-icon">${icon("upload")}</span><span><strong>Upload a recording</strong><small>Audio or video · up to 24 MB</small></span>${icon("arrow")}</button><button data-capture="record"><span class="capture-card-icon">${icon("mic")}</span><span><strong>Record your meeting</strong><small>Capture from your microphone</small></span>${icon("arrow")}</button><button data-capture="text"><span class="capture-card-icon">${icon("note")}</span><span><strong>Start with a transcript</strong><small>Paste the conversation you already have</small></span>${icon("arrow")}</button></div><div class="capture-card-foot">${icon("shield")} Local workspace. Clear next steps.</div></div></section><div class="quick-capture">${[
      ["upload", "upload", "Upload recording", "Audio or video, up to 24 MB"],
      ["record", "mic", "Record a meeting", "Capture from your microphone"],
      [
        "text",
        "note",
        "Import transcript",
        "Start with an existing conversation",
      ],
    ]
      .map(
        ([mode, symbol, title, description]) =>
          `<button class="capture-option" data-capture="${mode}"><span class="capture-icon">${icon(symbol)}</span><span><strong>${title}</strong><small>${description}</small></span><span class="capture-arrow">${icon("arrow")}</span></button>`,
      )
      .join(
        "",
      )}</div>${metrics()}<div class="section-heading"><h2>Recent meetings <span>${state.meetings.length} in your archive</span></h2><button class="text-button" data-nav="meetings">View archive ${icon("arrow")}</button></div>${meetingList(state.meetings.slice(0, 4))}<div class="workflow-strip">${["Capture meeting", "Transcribe & identify", "Analyze outcomes", "Create Jira tasks"].map((label, index) => `<div><span class="step-number">${index + 1}</span>${label}</div>${index < 3 ? '<span class="step-arrow">→</span>' : ""}`).join("")}</div>`;
}
function meetingList(meetings) {
  return `<div class="library">${meetings.length ? `<div class="list-header"><span>MEETING</span><span>CAPTURED</span><span>STATUS</span><span>TASKS</span><span></span></div>${meetings.map((meeting) => `<button class="meeting-row" data-meeting="${escape(meeting.id)}"><span class="meeting-cell"><span class="meeting-icon">${icon(meeting.source === "audio" ? "mic" : "note")}</span><span><span class="meeting-name">${escape(meeting.title)}</span><span class="meeting-meta">${meeting.source === "sample" ? '<span class="pill sample">Example</span>' : escape(meeting.source === "audio" ? "Recording" : "Transcript")}<span>·</span>${meeting.duration ? Math.ceil(meeting.duration / 60) + " min" : "Text import"}${meeting.speakers.length ? `<span>·</span>${meeting.speakers.length} speakers` : ""}</span></span></span><span class="meeting-date">${date(meeting.created_at)}</span>${pill(meeting)}<span class="row-tasks">${icon("check")}${meeting.tasks.length}</span><span class="row-arrow">${icon("arrow")}</span></button>`).join("")}<div class="library-foot"><span>${meetings.length} ${meetings.length === 1 ? "meeting" : "meetings"}</span><span>Most recent first</span></div>` : `<div class="empty-state"><div class="empty-icon">${icon("mic")}</div><h3>${state.search ? "No matching meetings." : "Ready for your first meeting."}</h3><p>${state.search ? "Try a different title or a phrase from the transcript." : "Upload a recording, capture your microphone, or import a transcript to get started."}</p>${state.search ? "" : `<button class="button primary" data-capture="upload">${icon("plus")}New meeting</button><button class="button secondary" data-action="sample">View example</button>`}</div>`}</div>`;
}
function renderLibrary() {
  $("#content").innerHTML =
    heading(
      "YOUR MEETING ARCHIVE",
      "Every conversation, connected.",
      "Find meeting transcripts, decisions, and the actions that followed.",
      `<button class="button primary small" data-capture="upload">${icon("plus")}New meeting</button>`,
    ) +
    `<div class="section-heading"><h2>All meetings <span>${state.meetings.length} saved</span></h2><label class="search">${icon("search")}<input id="meeting-search" aria-label="Search meetings" placeholder="Search title, summary, or transcript…" value="${escape(state.search)}"></label></div><div id="library-results">${meetingList(state.meetings)}</div><div class="bottom-note">${icon("shield")}Recordings and notes are saved in your project workspace.</div>`;
}
function taskCard(task, context = false) {
  const status = task.status;
  return `<article class="task-card" data-task-card="${escape(task.id)}"><button class="task-check ${status === "done" ? "done" : ""}" data-toggle-task="${escape(task.id)}" aria-label="${status === "done" ? "Reopen" : "Complete"} task: ${escape(task.title)}" aria-pressed="${status === "done"}">${status === "done" ? "✓" : ""}</button><div class="task-body"><button class="task-title ${status === "done" ? "done" : ""}" data-edit-task="${escape(task.id)}">${escape(task.title)}</button><p class="task-description">${escape(task.description)}</p><div class="task-meta"><span>${escape(task.owner || "Unassigned")}</span>${task.due_date ? `<span>· ${escape(task.due_date)}</span>` : ""}<span class="priority ${escape(task.priority)}">● ${escape(task.priority)}</span>${task.feature ? `<span>${escape(task.feature)}</span>` : ""}${context ? `<button class="text-button" data-meeting="${escape(task.meeting_id)}">${escape(task.meeting_title)}</button>` : ""}</div>${task.evidence ? `<details class="task-evidence-toggle"><summary>Source quote</summary><div class="details-source">“${escape(task.evidence)}”</div></details>` : ""}</div><div class="task-actions"><select data-task-status="${escape(task.id)}" aria-label="Status for ${escape(task.title)}">${[
    ["open", "To do"],
    ["in_progress", "In progress"],
    ["done", "Done"],
  ]
    .map(
      ([value, label]) =>
        `<option value="${value}" ${value === status ? "selected" : ""}>${label}</option>`,
    )
    .join(
      "",
    )}</select>${task.jira_key ? `<a class="button secondary small" href="${escape(task.jira_url)}" target="_blank" rel="noopener">${escape(task.jira_key)} ${icon("external")}</a>` : `<button class="button secondary small" data-jira="${escape(task.id)}" ${task.jira_status !== "not_sent" ? "disabled" : ""}>${task.jira_status === "uncertain" ? "Verify in Jira" : task.jira_status === "sending" ? "Sending…" : "Create Jira issue ↗"}</button>`}${task.jira_status === "not_sent" ? `<button class="icon-button" data-delete-task="${escape(task.id)}" aria-label="Delete task: ${escape(task.title)}">${icon("trash")}</button>` : ""}</div></article>`;
}
function renderMeeting() {
  const meeting = state.meeting;
  const active = activeStatuses.includes(meeting.status);
  const top = `<button class="text-button back-button" data-nav="meetings">${icon("back")}Back to meetings</button><div class="page-heading detail-heading"><div><span class="eyebrow">MEETING ANALYSIS</span><h1>${escape(meeting.title)} <button class="icon-button" data-action="rename-meeting" aria-label="Rename meeting">${icon("edit")}</button></h1><div class="detail-meta"><span>${icon("calendar")}${date(meeting.created_at)}</span><span>${icon("clock")}${meeting.duration ? Math.ceil(meeting.duration / 60) + " min" : "Text transcript"}</span><span>${icon("people")}${meeting.speakers.length ? meeting.speakers.length + " speakers" : "Speakers not identified"}</span>${pill(meeting)}</div></div><div class="heading-actions"><a class="button secondary small" href="/api/meetings/${escape(meeting.id)}/export">${icon("download")}Export notes</a><a class="button secondary small" href="/api/meetings/${escape(meeting.id)}/report" target="_blank" rel="noopener">PDF report ↗</a>${!active ? `<button class="icon-button danger-link" data-action="delete-meeting" aria-label="Delete meeting">${icon("trash")}</button>` : ""}</div></div>`;
  if (active) {
    $("#content").innerHTML =
      top +
      `<div class="processing-box"><span class="spinner"></span><h3>${meeting.status === "transcribing" ? "Transcribing your meeting." : meeting.status === "analyzing" ? "Analyzing the conversation." : "Your meeting is in the queue."}</h3><p>${meeting.status === "transcribing" ? "Turning your recording into a timestamped transcript. Speaker labels are included when detection is enabled." : "Extracting the summary, decisions, and explicit action items."}<br>You can continue browsing while processing runs.</p><div class="processing-steps">${["Capture", "Transcription", "AI analysis", "Action items"].map((label, index) => `<span class="${(meeting.status === "queued" && index === 0) || (meeting.status === "transcribing" && index === 1) || (meeting.status === "analyzing" && index === 2) ? "active" : ""}">${index + 1}. ${label}</span>`).join("")}</div></div>`;
    return;
  }
  const waiting =
    meeting.status === "transcribed"
      ? `<div class="notice"><div><strong>Transcript ready.</strong><br>${escape(meeting.error)} You can review the transcript, name speakers, and add tasks.</div><button class="button secondary small" data-action="retry">${icon("bolt")}Run AI analysis</button></div>`
      : "";
  const error =
    meeting.status === "failed"
      ? `<div class="error-box"><h3>This meeting needs attention.</h3><p>${escape(meeting.error)}</p><button class="button secondary small" data-action="retry">Retry processing</button></div>`
      : "";
  const sample =
    meeting.source === "sample"
      ? '<div class="sample-notice">Example meeting · Curated notes for exploring the workflow. Upload your own recording to process a real meeting.</div>'
      : "";
  const audio = meeting.has_audio
    ? `<div class="audio-panel"><span>${icon("wave")}Meeting recording</span><audio class="audio-player" id="meeting-audio" controls preload="metadata" src="/api/meetings/${escape(meeting.id)}/audio"></audio></div>`
    : "";
  const tabs = `<div class="detail-tabs" role="tablist" aria-label="Meeting views">${[
    ["overview", "Overview"],
    ["transcript", "Transcript"],
    ["actions", "Action items"],
  ]
    .map(
      ([tab, label]) =>
        `<button role="tab" class="${state.tab === tab ? "active" : ""}" aria-selected="${state.tab === tab}" data-tab="${tab}">${label}${tab === "actions" ? `<small>${meeting.tasks.length}</small>` : ""}</button>`,
    )
    .join("")}</div>`;
  let content;
  if (state.tab === "transcript") {
    content = `<section class="panel"><div class="panel-label">${icon("note")}FULL TRANSCRIPT</div>${meeting.segments.length ? meeting.segments.map((segment) => `<div class="transcript-entry"><button class="timestamp" data-seek="${segment.start}" ${meeting.has_audio ? "" : "disabled"} aria-label="Play recording at ${time(segment.start)}">${time(segment.start)}</button><div><div class="speaker">${escape(segment.speaker === "Unknown" ? "Speaker not identified" : segment.speaker)}${segment.speaker !== "Unknown" ? `<button class="text-button" data-speaker="${escape(segment.speaker)}" aria-label="Rename ${escape(segment.speaker)}">${icon("edit")}</button>` : ""}</div><p>${escape(segment.text)}</p></div></div>`).join("") : `<div class="raw-transcript">${escape(meeting.transcript || "No transcript is available yet.")}</div>`}</section>`;
  } else if (state.tab === "actions") {
    content = `<div class="action-toolbar"><button class="button secondary small" data-action="add-task">${icon("plus")}Add task</button><div class="heading-actions"><a class="button secondary small" href="/api/meetings/${escape(meeting.id)}/tasks.csv">${icon("download")}CSV</a><button class="button primary small" data-action="send-all">Create pending Jira issues ↗</button></div></div>${meeting.tasks.map((task) => taskCard(task)).join("") || '<section class="panel muted">No action items yet. Add a task or run AI analysis.</section>'}`;
  } else {
    content = `<section class="panel"><div class="panel-label">${icon("note")}MEETING SUMMARY</div><p class="summary-text">${escape(meeting.summary || "The summary will appear after AI analysis. Your transcript is saved in the Transcript tab.")}</p><div class="topic-list">${meeting.topics.map((topic) => `<span class="topic">${escape(topic)}</span>`).join("")}</div></section><section class="panel"><div class="panel-label">${icon("branch")}DECISIONS & OUTCOMES</div>${meeting.decisions.map((decision, index) => `<div class="decision"><span class="decision-number">${String(index + 1).padStart(2, "0")}</span><p>${escape(decision)}</p></div>`).join("") || '<p class="muted">No decisions recorded yet.</p>'}</section><div class="section-heading"><h2>Action items <span>${meeting.tasks.length}</span></h2><button class="text-button" data-tab="actions">Review tasks ${icon("arrow")}</button></div>${meeting.tasks
      .slice(0, 3)
      .map((task) => taskCard(task))
      .join("")}`;
  }
  const aside = `<aside class="detail-aside"><section class="panel"><h3 class="side-title">AT A GLANCE</h3>${[
    ["Decisions", meeting.decisions.length],
    ["Action items", meeting.tasks.length],
    [
      "Completed",
      meeting.tasks.filter((task) => task.status === "done").length,
    ],
    ["In Jira", meeting.tasks.filter((task) => task.jira_key).length],
  ]
    .map(
      ([label, count]) =>
        `<div class="side-stat"><span>${label}</span><strong>${count}</strong></div>`,
    )
    .join(
      "",
    )}</section><section class="panel"><h3 class="side-title">PARTICIPANTS</h3>${meeting.speakers.map((speaker) => `<div class="participant"><span class="avatar">${escape(initials(speaker))}</span>${escape(speaker)}<button class="icon-button" data-speaker="${escape(speaker)}" aria-label="Rename ${escape(speaker)}">${icon("edit")}</button></div>`).join("") || '<p class="muted service-note">Speaker labels appear after speaker detection.</p>'}</section><div class="bottom-note">${icon("shield")}Review the source before sending tasks to Jira.</div></aside>`;
  $("#content").innerHTML =
    top +
    error +
    waiting +
    sample +
    audio +
    tabs +
    `<div class="detail-layout"><div>${content}</div>${aside}</div>`;
}
function renderTasks() {
  let tasks = allTasks();
  if (state.filter !== "all")
    tasks = tasks.filter((task) =>
      state.filter === "jira" ? task.jira_key : task.status === state.filter,
    );
  const controls = `<div class="action-toolbar"><div class="filter-bar">${[
    ["all", "All tasks"],
    ["open", "To do"],
    ["in_progress", "In progress"],
    ["done", "Completed"],
    ["jira", "In Jira"],
  ]
    .map(
      ([filter, label]) =>
        `<button class="${state.filter === filter ? "active" : ""}" data-filter="${filter}">${label}</button>`,
    )
    .join(
      "",
    )}</div><button class="button secondary small" data-action="toggle-board">${icon(state.board ? "library" : "dashboard")}${state.board ? "List view" : "Board view"}</button></div>`;
  let content = tasks.map((task) => taskCard(task, true)).join("");
  if (state.board)
    content = `<div class="task-board">${[
      ["open", "To do"],
      ["in_progress", "In progress"],
      ["done", "Done"],
    ]
      .map(([status, label]) => {
        const group = tasks.filter((task) => task.status === status);
        return `<section class="board-column"><div class="board-heading">${label}<span>${group.length}</span></div>${group.map((task) => taskCard(task, true)).join("") || '<p class="board-empty">No tasks in this column.</p>'}</section>`;
      })
      .join("")}</div>`;
  $("#content").innerHTML =
    heading(
      "TASK AUTOMATION",
      "From discussion to delivery.",
      "Review assignments, track progress, and turn action items into Jira issues.",
    ) +
    controls +
    (content ||
      '<div class="library empty-state"><div class="empty-icon">' +
        icon("check") +
        '</div><h3>No tasks in this view.</h3><p>Tasks from your analyzed meetings appear here.</p><button class="button secondary" data-action="sample">View example meeting</button></div>');
}
function renderDecisions() {
  const meetings = state.meetings.filter((meeting) => meeting.decisions.length);
  $("#content").innerHTML =
    heading(
      "DECISION HISTORY",
      "Keep the decisions. Keep the context.",
      "A record of what your team agreed, connected to its source conversation.",
    ) +
    (meetings
      .map(
        (meeting) =>
          `<section class="panel"><div class="section-heading"><h2>${escape(meeting.title)}</h2><button class="text-button" data-meeting="${escape(meeting.id)}">Open meeting ${icon("arrow")}</button></div>${meeting.decisions.map((decision, index) => `<div class="decision"><span class="decision-number">${String(index + 1).padStart(2, "0")}</span><p>${escape(decision)}</p></div>`).join("")}</section>`,
      )
      .join("") ||
      '<div class="library empty-state"><div class="empty-icon">' +
        icon("branch") +
        '</div><h3>Decisions will appear here.</h3><p>Analyze a meeting to capture the choices your team made.</p><button class="button secondary" data-action="sample">View example meeting</button></div>');
}
function findTask(id) {
  return (
    state.meeting?.tasks.find((task) => task.id === id) ||
    allTasks().find((task) => task.id === id)
  );
}
async function refreshView() {
  await refresh();
  if (state.meeting) state.meeting = await api("/meetings/" + state.meeting.id);
  render();
}
function confirmAction(title, message, action) {
  confirmation = action;
  $("#confirm-title").textContent = title;
  $("#confirm-message").textContent = message;
  $("#confirm-dialog").showModal();
}
function editTask(id = "") {
  const task = id
    ? findTask(id)
    : {
        id: "",
        title: "",
        description: "",
        owner: "Unassigned",
        due_date: "",
        priority: "medium",
        evidence: "",
      };
  if (task.jira_status && task.jira_status !== "not_sent") {
    toast(
      "Edit linked task details in Jira. You can still update local progress.",
    );
    return;
  }
  const form = $("#task-form");
  for (const field of [
    "id",
    "title",
    "description",
    "owner",
    "due_date",
    "priority",
  ])
    form.elements.namedItem(field).value = task[field];
  $("#task-dialog-title").textContent = id ? "Review task" : "Add action item";
  $("#task-evidence").textContent = task.evidence
    ? `Source quote: “${task.evidence}”`
    : "Review the transcript to confirm this action item.";
  $("#task-dialog").showModal();
}
async function sendTask(id) {
  return api("/tasks/" + id + "/jira", { method: "POST" });
}
async function sendAll() {
  const pending = state.meeting.tasks.filter(
    (task) => task.jira_status === "not_sent",
  );
  if (!pending.length) {
    toast("There are no pending Jira issues to create.");
    return;
  }
  if (!state.settings.jira) {
    toast("Jira credentials are not configured yet. All tasks remain saved.");
    return;
  }
  confirmAction(
    "Create Jira issues",
    `Create ${pending.length} Jira issues from the reviewed tasks in this meeting?`,
    async () => {
      let sent = 0;
      let error = "";
      for (const task of pending) {
        try {
          await sendTask(task.id);
          sent++;
        } catch (exception) {
          error = exception.message;
          break;
        }
      }
      await refreshView();
      toast(
        `${sent} Jira ${sent === 1 ? "issue" : "issues"} created.${error ? " " + error : ""}`,
      );
    },
  );
}
document.addEventListener("click", async (event) => {
  const button = event.target.closest("button,a");
  if (!button) return;
  try {
    if (button.dataset.nav) navigate(button.dataset.nav);
    if (button.dataset.meeting) navigate("meeting/" + button.dataset.meeting);
    if (button.dataset.tab)
      navigate("meeting/" + state.meeting.id + "/" + button.dataset.tab);
    if (button.dataset.capture) showNew(button.dataset.capture);
    if (button.id === "new-top") showNew("upload");
    if (button.dataset.close) $("#" + button.dataset.close).close();
    if (button.dataset.input) switchInput(button.dataset.input);
    if (button.dataset.filter) {
      state.filter = button.dataset.filter;
      renderTasks();
    }
    if (button.dataset.editTask) editTask(button.dataset.editTask);
    if (button.dataset.toggleTask) {
      button.disabled = true;
      const task = findTask(button.dataset.toggleTask);
      await api("/tasks/" + task.id, {
        method: "PATCH",
        body: JSON.stringify({
          status: task.status === "done" ? "open" : "done",
        }),
      });
      await refreshView();
    }
    if (button.dataset.jira) {
      button.disabled = true;
      button.textContent = "Creating…";
      const result = await sendTask(button.dataset.jira);
      await refreshView();
      toast("Created " + result.jira_key + " in Jira.");
    }
    if (button.dataset.deleteTask) {
      const task = findTask(button.dataset.deleteTask);
      confirmAction(
        "Delete action item",
        `Delete “${task.title}” from this meeting?`,
        async () => {
          await api("/tasks/" + task.id, { method: "DELETE" });
          await refreshView();
          toast("Task deleted.");
        },
      );
    }
    if (button.dataset.speaker) {
      $("#speaker-form").elements.speaker.value = button.dataset.speaker;
      $("#speaker-name").value = button.dataset.speaker;
      $("#speaker-dialog").showModal();
    }
    if (button.dataset.seek) {
      const player = $("#meeting-audio");
      if (player) {
        player.currentTime = Number(button.dataset.seek);
        await player.play();
      }
    }
    if (button.id === "sample-button" || button.dataset.action === "sample") {
      button.disabled = true;
      const sample = await api("/sample", { method: "POST" });
      await refresh();
      navigate("meeting/" + sample.id);
    }
    if (button.dataset.action === "retry") {
      button.disabled = true;
      await api("/meetings/" + state.meeting.id + "/retry", { method: "POST" });
      await refreshView();
    }
    if (button.dataset.action === "add-task") editTask();
    if (button.dataset.action === "send-all") await sendAll();
    if (button.dataset.action === "toggle-board") {
      state.board = !state.board;
      renderTasks();
    }
    if (button.dataset.action === "rename-meeting") {
      const title = window.prompt("Meeting title", state.meeting.title);
      if (title?.trim()) {
        await api("/meetings/" + state.meeting.id, {
          method: "PATCH",
          body: JSON.stringify({ title: title.trim() }),
        });
        await refreshView();
      }
    }
    if (button.dataset.action === "delete-meeting") {
      const meeting = state.meeting;
      confirmAction(
        "Delete meeting",
        `Delete “${meeting.title}”, its recording, notes, and local tasks? Existing Jira issues will remain in Jira.`,
        async () => {
          await api("/meetings/" + meeting.id, { method: "DELETE" });
          state.meeting = null;
          await refresh();
          navigate("meetings");
          toast("Meeting deleted.");
        },
      );
    }
    if (button.id === "confirm-action" && confirmation) {
      button.disabled = true;
      const action = confirmation;
      confirmation = null;
      $("#confirm-dialog").close();
      await action();
    }
  } catch (error) {
    toast(error.message);
    if (button.dataset.jira) await refreshView().catch(() => {});
  } finally {
    if (button.isConnected) button.disabled = false;
  }
});
document.addEventListener("change", async (event) => {
  const id = event.target.dataset.taskStatus;
  if (!id) return;
  event.target.disabled = true;
  try {
    await api("/tasks/" + id, {
      method: "PATCH",
      body: JSON.stringify({ status: event.target.value }),
    });
    await refreshView();
  } catch (error) {
    toast(error.message);
    event.target.disabled = false;
  }
});
document.addEventListener("input", (event) => {
  if (event.target.id !== "meeting-search") return;
  state.search = event.target.value;
  const version = ++searchVersion;
  clearTimeout(searchTimer);
  searchTimer = setTimeout(async () => {
    try {
      const results = await api(
        "/meetings?q=" + encodeURIComponent(state.search),
      );
      if (
        version === searchVersion &&
        !state.meeting &&
        state.page === "meetings"
      )
        $("#library-results").innerHTML = meetingList(results);
    } catch (error) {
      toast(error.message);
    }
  }, 250);
});
$("#task-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const values = Object.fromEntries(new FormData(event.currentTarget));
  const id = values.id;
  delete values.id;
  const button = $('button[type="submit"]', event.currentTarget);
  button.disabled = true;
  try {
    await api(
      id ? "/tasks/" + id : "/meetings/" + state.meeting.id + "/tasks",
      { method: id ? "PATCH" : "POST", body: JSON.stringify(values) },
    );
    $("#task-dialog").close();
    await refreshView();
    toast(id ? "Task updated." : "Task added.");
  } catch (error) {
    toast(error.message);
  } finally {
    button.disabled = false;
  }
});
$("#speaker-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = $('button[type="submit"]', event.currentTarget);
  button.disabled = true;
  try {
    await api("/meetings/" + state.meeting.id + "/speakers", {
      method: "PATCH",
      body: JSON.stringify(
        Object.fromEntries(new FormData(event.currentTarget)),
      ),
    });
    $("#speaker-dialog").close();
    await refreshView();
    toast("Speaker name updated.");
  } catch (error) {
    toast(error.message);
  } finally {
    button.disabled = false;
  }
});

let inputMode = "upload",
  selectedFile = null,
  recorder = null,
  stream = null,
  recordTimer = null,
  recordingBlob = null,
  previewURL = null,
  chunks = [],
  recordingStart = 0,
  recordedBytes = 0;
function showNew(mode) {
  switchInput(mode);
  $("#meeting-dialog").showModal();
  $("#meeting-title").focus();
}
function stopTracks() {
  stream?.getTracks().forEach((track) => track.stop());
  stream = null;
  clearInterval(recordTimer);
}
function stopRecording() {
  if (recorder?.state === "recording") recorder.stop();
  stopTracks();
}
function switchInput(mode) {
  if (recorder?.state === "recording") stopRecording();
  inputMode = mode;
  $$("[data-input]").forEach((button) => {
    button.classList.toggle("active", button.dataset.input === mode);
    button.setAttribute("aria-selected", String(button.dataset.input === mode));
  });
  $$(".input-panel").forEach((panel) =>
    panel.classList.toggle("hidden", panel.id !== "input-" + mode),
  );
  $("#form-error").classList.add("hidden");
}
function pickFile(file) {
  if (!file) return;
  if (file.size > 24 * 1024 * 1024) {
    selectedFile = null;
    $("#file-label").textContent = "Choose a recording or drop it here";
    toast("Choose a recording smaller than 24 MB.");
    return;
  }
  selectedFile = file;
  $("#file-label").textContent =
    `${file.name} · ${(file.size / 1024 / 1024).toFixed(1)} MB`;
  if (!$("#meeting-title").value.trim())
    $("#meeting-title").value = file.name.replace(/\.[^.]+$/, "").slice(0, 180);
}
$("#audio-file").addEventListener("change", (event) =>
  pickFile(event.target.files[0]),
);
for (const event of ["dragenter", "dragover"])
  $("#dropzone").addEventListener(event, (action) => {
    action.preventDefault();
    $("#dropzone").classList.add("dragover");
  });
for (const event of ["dragleave", "drop"])
  $("#dropzone").addEventListener(event, (action) => {
    action.preventDefault();
    $("#dropzone").classList.remove("dragover");
    if (event === "drop") pickFile(action.dataTransfer.files[0]);
  });
$("#record-button").addEventListener("click", async () => {
  if (recorder?.state === "recording") {
    stopRecording();
    return;
  }
  const button = $("#record-button");
  button.disabled = true;
  try {
    if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder)
      throw new Error(
        "Use a supported browser on localhost or HTTPS to record. Audio upload is also available.",
      );
    stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    if (!$("#meeting-dialog").open || inputMode !== "record") {
      stopTracks();
      return;
    }
    const mime = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4"].find(
      (type) => MediaRecorder.isTypeSupported(type),
    );
    recorder = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
    chunks = [];
    recordingBlob = null;
    recordedBytes = 0;
    recordingStart = Date.now();
    $("#record-time").textContent = "00:00";
    recorder.ondataavailable = (event) => {
      if (event.data.size) {
        chunks.push(event.data);
        recordedBytes += event.data.size;
        if (
          recordedBytes > 23 * 1024 * 1024 &&
          recorder.state === "recording"
        ) {
          stopRecording();
          toast("Recording stopped near the upload size limit.");
        }
      }
    };
    recorder.onstop = () => {
      stopTracks();
      recordingBlob = new Blob(chunks, { type: recorder.mimeType });
      if (previewURL) URL.revokeObjectURL(previewURL);
      previewURL = URL.createObjectURL(recordingBlob);
      $("#record-preview").src = previewURL;
      $("#record-preview").classList.remove("hidden");
      button.textContent = "Record again";
      $("#record-label").textContent =
        "Recording ready. Submit to transcribe and analyze.";
      $("#record-time").classList.remove("recording");
    };
    recorder.onerror = () => {
      stopTracks();
      toast("Recording failed. Check microphone permission and try again.");
    };
    recorder.start(1000);
    $("#record-preview").classList.add("hidden");
    button.textContent = "Stop recording";
    $("#record-label").textContent = "Recording from your microphone…";
    $("#record-time").classList.add("recording");
    recordTimer = setInterval(
      () =>
        ($("#record-time").textContent = time(
          (Date.now() - recordingStart) / 1000,
        )),
      500,
    );
  } catch (error) {
    stopTracks();
    toast(
      error.name === "NotAllowedError"
        ? "Microphone access was denied. Allow it in the browser or upload a recording."
        : error.message,
    );
  } finally {
    button.disabled = false;
  }
});
$("#meeting-dialog").addEventListener("close", stopRecording);
window.addEventListener("beforeunload", stopTracks);
$("#meeting-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = $("#submit-meeting");
  button.disabled = true;
  button.textContent = "Saving meeting…";
  const error = $("#form-error");
  error.classList.add("hidden");
  try {
    const title = $("#meeting-title").value.trim();
    if (!title) throw new Error("Enter a meeting title.");
    let meeting;
    if (inputMode === "text") {
      const transcript = $("#transcript-input").value.trim();
      if (transcript.length < 30)
        throw new Error("Paste at least 30 characters of transcript.");
      meeting = await api("/meetings", {
        method: "POST",
        body: JSON.stringify({ title, transcript }),
      });
    } else {
      if (recorder?.state === "recording")
        throw new Error("Stop the recording before submitting.");
      const file = inputMode === "upload" ? selectedFile : recordingBlob;
      if (!file)
        throw new Error(
          inputMode === "upload"
            ? "Choose a recording first."
            : "Record some audio first.",
        );
      const form = new FormData();
      form.append("title", title);
      form.append(
        "audio",
        file,
        inputMode === "upload"
          ? file.name
          : recordingBlob.type.includes("mp4")
            ? "recording.m4a"
            : "recording.webm",
      );
      meeting = await api("/upload", { method: "POST", body: form });
    }
    $("#meeting-dialog").close();
    await refresh();
    navigate("meeting/" + meeting.id);
    toast("Meeting saved.");
    $("#meeting-form").reset();
    selectedFile = null;
    recordingBlob = null;
    $("#file-label").textContent = "Choose a recording or drop it here";
    $("#record-preview").classList.add("hidden");
    $("#record-time").textContent = "00:00";
    $("#record-button").textContent = "Start recording";
    $("#record-label").textContent =
      "Capture your microphone. Processing starts when you submit.";
  } catch (exception) {
    error.textContent = exception.message;
    error.classList.remove("hidden");
  } finally {
    button.disabled = false;
    button.innerHTML = "Analyze meeting " + icon("arrow");
  }
});
window.addEventListener("hashchange", route);
$("#content").innerHTML =
  '<div class="loading"><span class="spinner"></span><p>Opening your meeting workspace…</p></div>';
try {
  state.settings = await api("/settings");
  await refresh();
  await route();
  const entry = new URLSearchParams(location.search);
  if (entry.get('sample') === '1') {
    const sample = await api('/sample', { method: 'POST' });
    await refresh();
    navigate('meeting/' + sample.id);
  } else if (entry.get('capture') === 'upload') {
    $('#new-top').click();
  }
  if (entry.has('sample') || entry.has('capture')) {
    history.replaceState(null, '', location.pathname + location.hash);
  }
} catch (error) {
  $("#content").innerHTML =
    `<div class="error-box"><h2>Unable to open the workspace.</h2><p>${escape(error.message)} Refresh after the server is running.</p></div>`;
}
setInterval(async () => {
  if (
    polling ||
    document.hidden ||
    !(
      state.meetings.some((meeting) =>
        activeStatuses.includes(meeting.status),
      ) || activeStatuses.includes(state.meeting?.status)
    )
  )
    return;
  polling = true;
  try {
    await refreshView();
  } catch (error) {
    toast("Could not refresh processing status. Reconnecting…");
  } finally {
    polling = false;
  }
}, 2500);
