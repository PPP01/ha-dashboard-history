/**
 * The simple mode: versions, and the saves folded under them.
 *
 * Not a tidied version of the other one but a different offer. It
 * answers one question - "take me back to how it was" - and it answers
 * it with names and dates rather than with hashes and semver.
 *
 * The list is built from the *complete* set of versions, never from the
 * versions that happen to sit on a loaded change. A mark that vanishes
 * once its commit slides out of the window is the finding project G
 * exists for, and here it would be the whole mode going dark.
 */

const PARTS = new URL(import.meta.url).search;
const { escape, when } = await import(`./render.js${PARTS}`);

/**
 * `versions` is every version of this dashboard, newest number first
 * and complete. `changes` is the loaded window, newest first, and may
 * hold nothing at all for the older versions - which is why the head
 * carries the way back rather than the rows under it.
 */
export function renderSimple({ versions, changes, searching = false }) {
  if (!versions.length)
    // Two different reasons for an empty list, and each gets its own
    // sentence: while searching, an empty list means "no match" - the
    // button and the way out belong to the other case, where there are
    // no versions at all yet.
    return searching
      ? `<p class="empty muted">No version matches.</p>`
      : // The button and the way out come *with* the sentence. Behind an
      // early return they would not exist, and somebody in the default
      // mode with no versions yet would have neither a way to make one
      // nor a visible way to the other mode.
      `<p class="empty muted">This dashboard has no versions yet.</p>
         <button class="act ghost" data-version="now">Save this as a version</button>
         <p class="why hint">Taking back a single step, or putting back one
           deleted card, lives in the advanced mode.
           <button class="linky" data-mode="advanced">Switch to it</button></p>`;

  // Where the dashboard stands, said in the only vocabulary this mode
  // has. `same_as_now` comes from the server and is worked out against
  // every version, so it is right whether or not that version's commit
  // is in the loaded window.
  const here = versions.filter((v) => v.same_as_now);
  const standing = here.length
    ? `The dashboard is in the state of ${escape(here[0].title || here[0].name)}.`
    : "The dashboard has changed since the last version was saved.";

  const rows = versions.map((version) => {
    // Its changes are the loaded ones from this version's own state
    // downwards, stopping at the next version. What has not been loaded
    // is simply not folded in; the head is what somebody goes back to,
    // and it is always there.
    const start = changes.findIndex((c) => c.revision === version.revision);
    const inside = [];
    if (start >= 0)
      for (let i = start; i < changes.length; i += 1) {
        if (i > start && (changes[i].versions || []).length) break;
        inside.push(changes[i]);
      }
    const folded = inside.length
      ? `<details class="steps">
           <summary>${inside.length} change${inside.length === 1 ? "" : "s"}
             in this version</summary>
           ${inside
        .map(
          (c) =>
            `<p class="step">${escape(c.description || c.message)}
                   <span class="when">${escape(when(c.timestamp))}</span></p>`,
        )
        .join("")}
         </details>`
      : "";
    // No button where its target is what the dashboard already holds.
    // A button that does nothing is a question without an answer.
    const back = version.same_as_now
      ? `<span class="count">where you are</span>`
      : `<button class="act ghost" data-state="${escape(version.name)}"
                 >Go back to this</button>`;
    const made = version.automatic
      ? `<span class="auto">saved automatically</span>`
      : "";
    return `<div class="vrow">
              <div class="vhead">
                <span class="grow">${escape(version.title || version.name)}${made}</span>
                ${back}
              </div>
              ${version.description
        ? `<p class="why">${escape(version.description)}</p>`
        : ""}
              ${folded}
            </div>`;
  });

  return `
    <div class="standing">
      <p class="heading">Right now</p>
      <p>${escape(standing)}</p>
      <button class="act ghost" data-version="now">Save this as a version</button>
    </div>
    ${rows.join("")}
    <p class="why hint">Taking back a single step, or putting back one
      deleted card, lives in the advanced mode.
      <button class="linky" data-mode="advanced">Switch to it</button></p>`;
}
