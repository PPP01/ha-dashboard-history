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

/**
 * A unified diff, coloured the way people expect to read one.
 *
 * Every line becomes its own block-level span (style.js relies on
 * this for the full-row background behind a "+"/"-"/"@@" line), and
 * there is no separating "\n" text node left between them - a block
 * sitting next to a literal newline renders as an extra blank line in
 * a real browser, a known trap of block-in-inline layout.
 */
export const renderDiff = (diff) => {
  if (!diff) return '<p class="muted">No difference.</p>';
  const body = diff
    .split("\n")
    .map((line) => {
      // The two file markers first, and not folded into the plain
      // "+"/"-" checks below: unified diff spells them "---"/"+++",
      // which both start with a single "+" or "-" too, and without this
      // the file's own name got the same full-row block a changed line
      // gets - reading as one more change in the list rather than as
      // the header sitting above all of them.
      const cls = line.startsWith("+++")
        ? "hdr-add"
        : line.startsWith("---")
          ? "hdr-del"
          : line.startsWith("+")
            ? "add"
            : line.startsWith("-")
              ? "del"
              : line.startsWith("@@")
                ? "at"
                : "";
      return `<span${cls ? ` class="${cls}"` : ""}>${escape(line)}</span>`;
    })
    .join("");
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
        <strong>${group.scope === "dashboard" ? "On the dashboard itself" : `In the view ${escape(group.view)}`}</strong>
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

/**
 * A span of time as one line: one date and two times where both ends
 * fall on the same day, `when(from) – when(to)` where they do not - the
 * create-version dialog's own pending span usually opens and closes
 * within minutes of each other, and repeating the date on both sides of
 * the dash reads as a stutter where it never changed.
 */
export const whenRange = (fromTimestamp, toTimestamp) => {
  const from = new Date(fromTimestamp * 1000);
  const to = new Date(toTimestamp * 1000);
  const sameDay =
    from.getFullYear() === to.getFullYear() &&
    from.getMonth() === to.getMonth() &&
    from.getDate() === to.getDate();
  if (!sameDay) return `${when(fromTimestamp)} – ${when(toTimestamp)}`;
  const date = from.toLocaleDateString(undefined, { dateStyle: "medium" });
  const time = (value) =>
    value.toLocaleTimeString(undefined, { timeStyle: "short" });
  return `${date}, ${time(from)} – ${time(to)}`;
};
