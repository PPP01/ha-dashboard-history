/*
 * Turning answers into markup. Pure functions: no element, no state, no
 * calls of their own. That is what makes them worth having apart - each
 * one can be read and reasoned about without the element around it.
 */

export const escape = (value) =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (character) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        character
      ],
  );

/** A unified diff, coloured the way people expect to read one. */
export const renderDiff = (diff) => {
  if (!diff) return '<p class="muted">No difference.</p>';
  const body = diff
    .split("\n")
    .map((line) => {
      const cls = line.startsWith("+")
        ? "add"
        : line.startsWith("-")
          ? "del"
          : line.startsWith("@@")
            ? "at"
            : "";
      return cls
        ? `<span class="${cls}">${escape(line)}</span>`
        : escape(line);
    })
    .join("\n");
  return `<pre>${body}</pre>`;
};

/**
 * The same difference in words. It sits above the diff, not instead of
 * it: the diff is the exact account, and it stays.
 */
export const renderPlain = (explanation, heading) => {
  if (!explanation) return "";
  const groups = (explanation.groups || [])
    .map(
      (group) => `
      <div class="view">
        <strong>In the view ${escape(group.view)}</strong>
        <ul>
          ${group.entries
            .map(
              (entry) =>
                `<li class="${escape(entry.kind)}">${escape(entry.text)}</li>`,
            )
            .join("")}
          ${group.more ? `<li class="muted">and ${escape(group.more)} more</li>` : ""}
        </ul>
      </div>`,
    )
    .join("");
  const note = explanation.note
    ? `<p class="note muted">${escape(explanation.note)}</p>`
    : "";
  return `<div class="plain"><h3>${escape(heading)}</h3>${groups}${note}</div>`;
};

/**
 * Names in a sentence: "v1.0.0", or "v1.0.0 and v1.1.0", or "v1.0.0,
 * v1.1.0 and v2.0.0". The plural is not hypothetical - two versions may
 * sit on one state, and two different states may both hold what the
 * dashboard holds now - and a bare comma list reads like a stutter in
 * the middle of a sentence.
 */
export const joinNames = (names) =>
  names.length < 2
    ? names.join("")
    : `${names.slice(0, -1).join(", ")} and ${names[names.length - 1]}`;

export const when = (timestamp) =>
  new Date(timestamp * 1000).toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  });
