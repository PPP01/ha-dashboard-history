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

// The way over to the other mode. Offered in both of this mode's
// states - with versions and without - and written once, because two
// copies of one offer drift until they say different things.
const HINT = `<p class="why hint">Taking back a single step, or putting back one
  deleted card, lives in the advanced mode.
  <button class="linky" data-mode="advanced">Switch to it</button></p>`;

/**
 * `versions` is every version of this dashboard, newest number first
 * and complete. `shown` is the part of it a search has left, and
 * defaults to all of them. `changes` is the loaded window, newest
 * first, and may hold nothing at all for the older versions - which is
 * why the head carries the way back rather than the rows under it.
 *
 * Both lists, and not one filtered one, because the two halves of this
 * page have two different subjects. The rows are the answer to what
 * was typed in the box; the sentence at the top is about the
 * dashboard, and the dashboard does not change when somebody types.
 * Given only the filtered list it read "The dashboard has changed since
 * the last version was saved." the moment a search removed the version
 * the dashboard is actually standing on - the one place this mode took
 * a fact the server had answered and quietly recomputed it over a
 * display list.
 */
export function renderSimple({
  versions,
  shown = versions,
  changes,
  searching = false,
}) {
  if (!shown.length)
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
         ${HINT}`;

  // Where the dashboard stands, said in the only vocabulary this mode
  // has. `same_as_now` comes from the server and is worked out against
  // every version, so it is right whether or not that version's commit
  // is in the loaded window.
  // Over every version, never over `shown`: see the note above.
  const here = versions.filter((v) => v.same_as_now);
  const standing = here.length
    ? `The dashboard is in the state of ${escape(here[0].title || here[0].name)}.`
    : "The dashboard has changed since the last version was saved.";

  const rows = shown.map((version) => {
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
    // "The newest N", not "N": `inside` starts at the version's own
    // change and walks downwards, so it is cut at the older end
    // whenever the version spans more than the loaded window holds. A
    // flat "25 changes in this version" was wrong for a version
    // spanning a hundred - and this mode has no "load older" that could
    // ever make it right, so the label carries the limit instead of
    // waiting for a button that does not exist.
    //
    // Where the version's own change is below the window there is no
    // fold at all, which stays as it is: on a dashboard with many
    // versions that is most of the rows, and a line on each of them
    // saying so would be noise. An absent fold claims nothing; a
    // wrong number claims something false.
    const folded = inside.length
      ? `<details class="steps">
           <summary>${inside.length === 1
        ? "The newest change in this version"
        : `The newest ${inside.length} changes in this version`}</summary>
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
    ${HINT}`;
}
