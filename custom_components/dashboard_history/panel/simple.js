/**
 * The simple mode: versions, and the saves folded under them.
 *
 * Not a tidied version of the other one but a different offer. It
 * answers one question - "take me back to how it was" - and it answers
 * it with numbers, names and dates rather than with hashes and diffs.
 *
 * The number is here against the mode's first draft, which left it out
 * as machinery. On an installation it turned out to be the opposite:
 * the titles were the machinery, written by whatever made the version,
 * and the number was the only thing on the row a person could hold on
 * to. What this mode leaves to the advanced one is the revision, the
 * diff and the single step - not the one mark that says which of two
 * lookalike rows is the newer.
 *
 * The list is built from the *complete* set of versions, never from the
 * versions that happen to sit on a loaded change. A mark that vanishes
 * once its commit slides out of the window is the finding project G
 * exists for, and here it would be the whole mode going dark.
 */

const PARTS = new URL(import.meta.url).search;
const { escape, when } = await import(`./render.js${PARTS}`);
// The chip and the pen this mode borrows. `rows.js` calls itself the
// pieces a history is drawn from - sections, heads, rows, chips - and
// says both modes build from exactly those; for these two that is now
// true. The pen especially: one control renaming a version, drawn the
// same way wherever a version is shown.
const { NOW_CHIP, pen } = await import(`./rows.js${PARTS}`);

// The way over to the other mode. Offered in both of this mode's
// states - with versions and without - and written once, because two
// copies of one offer drift until they say different things.
const HINT = `<p class="why hint">Taking back a single step, or putting back one
  deleted card, lives in the advanced mode.
  <button class="linky" data-mode="advanced">Switch to it</button></p>`;

/**
 * The number a version is known by: `v1.2.0` out of `dash/v1.2.0`.
 *
 * Escaped here, so that every place using it is one place fewer to
 * forget. The same derivation the advanced mode's head makes, and the
 * reason this mode needs it too was measured rather than argued: on an
 * installation whose versions are made by a routine, twelve rows
 * carried four titles between them and nothing else to tell them apart.
 * A title repeats and a number does not - and a number sorts, which is
 * the second thing a person reading down a list wants from it.
 */
const number = (version) => escape(version.name.split("/").pop());

/**
 * The loaded changes of one span, as the lines under an opened row.
 *
 * One function for the version rows and for the current-state block:
 * they say the same thing about two different spans. Written twice in
 * this file's first draft of the second one, and the two copies had
 * already begun to differ before either was read.
 */
const steps = (list) =>
  list
    .map(
      (c) =>
        `<p class="step">${escape(c.description || c.message)}
           <span class="when">${escape(when(c.timestamp))}</span></p>`,
    )
    .join("");

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
 *
 * `open` are the rows somebody has opened, by version name. It is the
 * element's own bookkeeping and not the browser's: a render builds new
 * <details>, and native state alone shuts the row being worked in -
 * which here would happen on the way to the confirm dialog, since the
 * preview fetch renders before the dialog opens. The advanced mode's
 * sections learned this first; this is the same set.
 *
 * `nowOpen` is the same fact about the current-state box, and a flag
 * rather than a member of that set: the set is keyed by version name,
 * and this box is not a version. It rides the panel's fold bookkeeping
 * instead, which is what that exists for.
 */
export function renderSimple({
  versions,
  shown = versions,
  changes,
  searching = false,
  open = new Set(),
  nowOpen = false,
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
  // The one place you are standing. More than one version can hold what
  // the dashboard holds - a routine that saves every day collects them
  // by the dozen - and the sentence has always named exactly one of
  // them: the highest numbered. The rows now name the same one, which
  // is the whole of the fix. Before it, every matching row said "where
  // you are", and a screen answering "where am I" six times answers it
  // not at all.
  // Escaped as it is built, and only here: the sentence used to be
  // escaped a second time on its way out, which turned an ampersand in
  // a dashboard's title into &amp; on the screen.
  const standingOn = here.length ? here[0] : null;
  const standing = standingOn
    ? `The dashboard is in the state of ${number(standingOn)}${standingOn.title ? ` — ${escape(standingOn.title)}` : ""}.`
    : "The dashboard has changed since the last version was saved.";

  // The changes that are in no version yet - the same cut the advanced
  // mode's top section makes, made here from the same list. This is the
  // one thing in the block below that still hangs on the loaded window,
  // because a change's words only exist for a change that was loaded.
  // The way back does not hang on it, and that is the point of the two
  // being worked out separately rather than from one index.
  const versioned = changes.findIndex((c) => (c.versions || []).length);
  // Whether the version these changes stop at is itself in the window.
  // Named because three lines below ask it, and the answer decides both
  // what the fold holds and how far the count may claim to reach.
  const bounded = versioned >= 0;
  const loose = bounded ? changes.slice(0, versioned) : changes;
  // Exact or hedged, and the word "newest" is the whole difference.
  // Where the version bounding these sits in the window, nothing is cut
  // at the older end and the count is the whole truth - the one place in
  // this mode that can say so, since a version row never knows where
  // its own span ends. Where it does not, every loaded change is still
  // rightly in here (the window holds the newest changes, and not one of
  // them carries a mark, so the last version is older than all of them)
  // and only the far end is unknown.
  const reach = bounded ? "The" : "The newest";
  const span = loose.length === 1 ? "change" : `${loose.length} changes`;
  const nowBody = loose.length
    ? `<p class="stephead">${reach} ${span} since the last version</p>
       ${steps(loose)}`
    : "";
  // One press that takes the dashboard off everything since the last
  // saved state. It is the top row's "Go back to this" under a name
  // that says how far it reaches - the same service, the same preview,
  // the same dialog, which is why it needs no wiring of its own.
  //
  // Offered exactly when the sentence above says the dashboard has
  // drifted, out of the same fact, so the two cannot come to disagree -
  // and on that one condition alone. There is always a version to name:
  // with none, the early return above has already had the last word.
  // Standing in *some* version's state is enough to withhold the
  // button: from an older version's state "back to v1.2.0" would be a
  // jump forwards wearing the word "undo", and the row for it is right
  // there in the list saying "Go back to this".
  //
  // `versions[0]`, never something read off the window. That list is
  // complete and ordered by number, so this is the newest version
  // whether or not its commit is anywhere near the loaded changes. A
  // way back that vanished once the window slid past it would be the
  // finding this mode exists to avoid, on the one button nobody can do
  // without.
  const undo = standingOn
    ? ""
    : `<button class="act ghost" data-state="${escape(versions[0].name)}"
           >Undo / Go back to ${number(versions[0])}</button>`;
  // What the block says with itself shut. The chip is the advanced
  // mode's - the same constant, not the same words typed again - and
  // unlike there it needs no proof: a crowned row has to earn "current
  // state" by matching the live configuration, while "right now" *is*
  // the live state, and the chip labels the box rather than an entry.
  const nowHead = `<p class="heading">Right now ${NOW_CHIP}</p>
      <p>${standing}</p>
      <span class="acts">
        <button class="act ghost" data-version="now">Save this as a version</button>
        ${undo}
      </span>`;
  // A way in only where there is something behind it - the same rule the
  // rows below follow, and it bites here too: with the dashboard changed
  // at Home Assistant's back there is no recorded change since the
  // version, and an opener would lead onto an empty space.
  const now = nowBody
    ? `<details class="standing" data-fold="now"${nowOpen ? " open" : ""}>
         <summary>${nowHead}</summary>
         <div class="vbody">${nowBody}</div>
       </details>`
    : `<div class="standing">${nowHead}</div>`;

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
    //
    // The sentence is a heading inside the opened row now rather than
    // the thing you click. What you click is the row - so this line no
    // longer has to be a place to aim at, and it can go back to being
    // what it always was: the note saying how far the list under it
    // reaches.
    const folded = inside.length
      ? `<p class="stephead">${inside.length === 1
        ? "The newest change in this version"
        : `The newest ${inside.length} changes in this version`}</p>
           ${steps(inside)}`
      : "";
    // No button where its target is what the dashboard already holds.
    // A button that does nothing is a question without an answer.
    //
    // Three cases and not two. A version that holds the live state
    // without being the one you stand on gets the wording the advanced
    // mode uses for exactly this, word for word: one fact, one
    // vocabulary, however many places say it.
    const back =
      standingOn && version.name === standingOn.name
        ? `<span class="count">where you are</span>`
        : version.same_as_now
          ? `<span class="count">same state as now</span>`
          : `<button class="act ghost" data-state="${escape(version.name)}"
                 >Go back to this</button>`;
    const auto = version.automatic
      ? `<span class="auto">saved automatically</span>`
      : "";
    // Nothing where the store has no time to give. A tag made by hand
    // carries none, and a row reading "1 Jan 1970" would put every
    // honest date beside it in doubt.
    const made = version.timestamp
      ? `<span class="made">${escape(when(version.timestamp))}</span>`
      : "";
    // What stays visible when the row is shut: the head, and the words
    // somebody wrote about the version. The note is short, it is the
    // one thing on the row nobody else wrote, and putting it behind a
    // click would make the closed row say less than it does today.
    const head = `<span class="vhead penholder">
                <span class="name">${number(version)}</span>
                <span class="grow">${escape(version.title)}${auto}</span>
                ${made}
                ${back}
                ${pen(version)}
              </span>
              ${version.description
        ? `<p class="why">${escape(version.description)}</p>`
        : ""}`;
    // A row is a way in only where there is something behind it. Most
    // rows on a dashboard with hundreds of versions have nothing - the
    // window does not reach their changes - and a row that opens onto
    // an empty space is a promise broken as soon as it is taken up.
    if (!folded) return `<div class="vrow"><div class="vsum">${head}</div></div>`;
    return `<details class="vrow" data-key="${escape(version.name)}"${open.has(version.name) ? " open" : ""}>
              <summary class="vsum">${head}</summary>
              <div class="vbody">${folded}</div>
            </details>`;
  });

  return `
    ${now}
    ${rows.join("")}
    ${HINT}`;
}
