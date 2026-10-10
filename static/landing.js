const panels = {
  tasks: `<div class="task-row"><span class="task-checkbox"></span><div><strong>Review the launch checklist</strong><small>Alex · Friday</small></div><span class="task-priority">Medium</span></div><div class="task-row"><span class="task-checkbox"></span><div><strong>Send updated designs</strong><small>Priya · Wednesday</small></div><span class="task-priority">Medium</span></div><div class="task-row"><span class="task-checkbox"></span><div><strong>Fix the login bug</strong><small>Jamie · Thursday</small></div><span class="task-priority high">High</span></div>`,
  summary: `<p class="preview-summary"><strong>A launch plan everyone can follow.</strong>The team kept Friday as the launch date, agreed to prioritize the login fix, and moved the dashboard redesign to the next sprint. Alex, Priya, and Jamie each have a clear next step.</p>`,
  decisions: `<div class="task-row"><span class="check-circle">✓</span><div><strong>Keep Friday as the launch date.</strong><small>Source: Alex · 02:14</small></div></div><div class="task-row"><span class="check-circle">✓</span><div><strong>Move the dashboard to the next sprint.</strong><small>Source: Jamie · 03:08</small></div></div>`,
};
const tabs = [...document.querySelectorAll("[data-preview]")];
function selectTab(tab) {
  for (const item of tabs) {
    item.setAttribute("aria-selected", String(item === tab));
    item.tabIndex = item === tab ? 0 : -1;
  }
  const content = document.querySelector("#preview-content");
  content.innerHTML = panels[tab.dataset.preview];
  content.setAttribute("aria-labelledby", tab.id);
}
for (const tab of tabs) {
  tab.addEventListener("click", () => selectTab(tab));
  tab.addEventListener("keydown", (event) => {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
    event.preventDefault();
    let index = tabs.indexOf(tab);
    index =
      event.key === "Home"
        ? 0
        : event.key === "End"
          ? tabs.length - 1
          : (index + (event.key === "ArrowRight" ? 1 : -1) + tabs.length) %
            tabs.length;
    selectTab(tabs[index]);
    tabs[index].focus();
  });
}
selectTab(document.querySelector('[data-preview="tasks"]'));
document
  .querySelector(".waveform")
  .replaceChildren(
    ...Array.from({ length: 75 }, () => document.createElement("i")),
  );
for (const button of document.querySelectorAll("[data-view]")) {
  button.addEventListener("click", () => {
    const after = button.dataset.view === "after";
    document.querySelector(".conversation-panel").hidden = after;
    document.querySelector(".clarity-panel").hidden = !after;
    for (const item of document.querySelectorAll("[data-view]"))
      item.setAttribute("aria-pressed", String(item === button));
  });
}
