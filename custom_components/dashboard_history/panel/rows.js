/**
 * The pieces a history is drawn from: sections, heads, rows, chips.
 *
 * Pure on purpose - data in, markup out, no `this`. Both modes build
 * their list from exactly these, which is why the split runs along
 * responsibility rather than along the modes: a cut by mode would have
 * made two of each of them.
 */

const PARTS = new URL(import.meta.url).search;
const { escape, when, joinNames } = await import(`./render.js${PARTS}`);

/**
 * The history, cut into sections at the versions.
 *
 * A version marks a state, so it marks the *newest* change it contains
 * - the section it heads runs from that change downwards to the next
 * version below. Everything above the topmost version is not in a
 * version yet, and that is the section people work in.
 */
export function sections(changes) {
  const out = [];
  let head = null;
  let rows = [];
  changes.forEach((change, index) => {
    const marks = change.versions || [];
    if (marks.length) {
      if (rows.length || head) out.push({ versions: head, rows });
      head = marks;
      rows = [index];
    } else {
      rows.push(index);
    }
  });
  if (rows.length || head) out.push({ versions: head, rows });
  return out;
}

/**
 * The label for the state the dashboard holds right now.
 *
 * Exported because two modes draw it: the advanced one hangs it on the
 * crowned row, the simple one on its current-state box. It was written
 * out in both for a while, held equal by a comment in each place saying
 * it matched the other - which is the invariant a copy breaks first.
 * The word "state" is load-bearing (see `renderRow` below), and so is
 * the tooltip; neither belongs to whichever mode happens to draw it.
 *
 * `named` is the same fact the ring around this chip's own box answers:
 * does anything recorded hold this content. A function and not a
 * constant since that answer differs by dashboard and by the minute -
 * unlike the chip's words and tooltip, which never do.
 */
export const nowChip = (named) => `<span class="chip now${named ? " named" : ""}"
       title="This is the state the dashboard holds right now."
       >current state</span>`;

/**
 * A couple of names, and how many were left out.
 *
 * Measured on the test bench: eighteen versions sat on states equal to
 * the live one, and the chip listed every one of them - a label longer
 * than the row it labelled. A history that goes back and forth while
 * versions are made collects these, and the count is unbounded.
 *
 * Cut, never silently: the project's own rule for the explanation lists
 * is that a summary which omits without saying so is worse than a long
 * one. The tooltip carries all of them.
 *
 * The one named is the first, which is the version on the most recent
 * matching state - not the highest number. Those usually coincide and
 * need not: a version made today on an old state sorts by that state.
 */
export function someNames(names) {
  if (names.length <= 2) return joinNames(names);
  return `${names[0]} and ${names.length - 1} more`;
}

/**
 * A section head. Two versions can sit on the same state; both are
 * named rather than one of them being silently dropped.
 *
 * The button disappears when its target is what the dashboard holds
 * already - the same rule the row buttons follow, and for the same
 * reason: offering it there opens a dialog reading "No difference."
 * above a live Apply button.
 *
 * `here` is whether the newest change in this section is the state the
 * dashboard holds. It comes in rather than being worked out, because
 * working it out needs the change list and this function has only the
 * section.
 */
export function versionHead({ section, here, top, compareMode = false, compareChecked = false }) {
  const [first, ...also] = section.versions;
  const count = section.rows.length;
  const extra = also
    .map(
      (v) =>
        `<span class="also">also ${escape(v.name)} — ${escape(v.title)}${pen(v)}${bin(v)}</span>`,
    )
    .join("");
  // Two different truths, and one wording for both was an overclaim.
  // A version sitting on the newest entry *is* where the dashboard is.
  // A version further down whose state matches only holds the same
  // thing: going back to it wrote a newer entry, and that entry, not
  // this version, is where you are. Saying "current state" there
  // invites the reading Decision 9 exists to prevent.
  //
  // "same state as now" and not a wording of its own: three places say
  // this one fact, and they said it in two vocabularies until somebody
  // read all three together and asked whether they meant the same
  // thing. They do.
  const back = here
    ? `<span class="count">${top === 0 ? "current state" : "same state as now"}</span>`
    : `<button class="act ghost" data-state="${escape(first.name)}"
               >Back to this version</button>`;
  return `
    <summary class="penholder">
      ${compareMode
      ? `<input type="checkbox" class="compare-check" data-compare="${escape(first.name)}"
                 data-compare-label="${escape(first.title || first.name)}"
                 ${here && top === 0 ? 'data-compare-now="1"' : ""}
                 ${compareChecked ? "checked" : ""}>`
      : ""}
      <span class="name">${escape(first.name.split("/").pop())}</span>
      <span class="grow">${escape(first.title || first.name)}${extra}</span>
      <span class="count">${count} change${count === 1 ? "" : "s"}</span>
      ${back}
      ${pen(first)}
      ${bin(first)}
    </summary>`;
}

/**
 * The way to give one version new words. Exported so that both modes
 * draw the same control rather than two that drift.
 *
 * Offered only where there are words to change, and the server says so:
 * a lightweight tag is the ref itself and has no message, so the store
 * refuses to rename it. A button that could only ever produce that
 * sentence is not an offer.
 *
 * `annotated` and not "does it have a title", which is what this asked
 * first. A title is a field a person is now allowed to rewrite, so
 * reading the kind of tag out of it was reading a fact out of a name -
 * the same mistake the day mark was just repaired for. It was wrong in
 * both directions: a hand-made *annotated* tag with an empty first line
 * can be renamed and would have been refused a pen, and any future
 * version without a title would lose its pen without a word.
 */
export function pen(version) {
  if (!version.annotated) return "";
  return `<button class="pen" data-retitle="${escape(version.name)}"
               title="Rename this version">✎</button>`;
}

/**
 * The way to take one version's mark away. Exported beside `pen` so
 * that both modes draw the same control rather than two that drift.
 *
 * Offered on **every** version, which is where it parts company with
 * the pen - and the difference is the point rather than an oversight. A
 * lightweight tag cannot be renamed, so a pen on one could only ever
 * produce the server's refusal; it can be removed, and it has to be,
 * because it counts when the next number is worked out.
 *
 * It carries the pen's class as well as its own. The stylesheet reveals
 * `.pen` from a class on whatever holds the control, not from a list of
 * the controls that exist - the comment there says why, and the failure
 * mode of a fourth place forgetting itself is silent invisibility. So
 * this earns no fifth selector; `.bin` adds only what differs.
 */
export function bin(version) {
  return `<button class="pen bin" data-remove="${escape(version.name)}"
               title="Remove this version">🗑</button>`;
}

/**
 * One change, as a row.
 *
 * The word "state" in both chips is load-bearing, and it was missing.
 * A row says two things about two different subjects: the message is
 * about the *change*, the chip about the *state it left behind*. Read
 * as one sentence, "4 moved · same as now" is a contradiction - four
 * cards moved, and yet nothing differs? Both halves were true and the
 * row still misled, because nothing named what each half was about.
 *
 * The other difference the chips carry: the top entry is where you are.
 * A lower entry can hold byte-identical content without being where you
 * are - move a card up and down and there is a whole run of them, all
 * worded alike.
 *
 * `spokenFor` is the first row of a version section, whose head carries
 * the same chip a few pixels above it. Two identical labels stacked is
 * not emphasis, it is noise - and it was measurable: the head read
 * "same content as now" while the row under it read "same state as
 * now", one fact wearing two coats.
 *
 * `matching` are versions holding what this row's state holds without
 * sitting on it; `detail` is the already-built detail block, or "".
 */
export function renderRow({
  change,
  newest = false,
  spokenFor = false,
  matching = [],
  detail = "",
  compareMode = false,
  compareChecked = false,
}) {
  const chip =
    spokenFor || !change.same_as_now
      ? ""
      : newest
        ? nowChip(matching.length > 0)
        : `<span class="chip sameas"
                 title="The change described here left the dashboard in exactly the state it holds right now."
                 >same state as now</span>`;
  // Beside "current state" rather than in a sentence under the card.
  // Both said the same thing; only one of them sits inside the frame
  // the eye stops at, and the sentence below was read past. Kept short
  // for the same reason - a chip is a label, not a statement - with the
  // part that cannot fit moved into the tooltip, where "a different
  // entry" is spelled out. It says "identical in content to", never
  // "is": going back to a version writes a new entry, and this is that
  // entry, not that version.
  const named = matching.length
    ? `<span class="chip ver"
             title="A different entry that holds exactly what ${escape(joinNames(matching))} holds. Going back to a version writes a new entry; this is that entry."
             >same state as ${escape(someNames(matching))}</span>`
    : "";
  // `spokenFor` only mutes the chip's own text - the row underneath a
  // version head that sits on the newest change still IS that state,
  // and compare mode needs to know that regardless of whether anything
  // on screen says so out loud.
  const isNow = newest && change.same_as_now;
  return `
      <div class="card">
        <div class="change penholder" data-revision="${escape(change.revision)}">
          ${compareMode
      ? `<input type="checkbox" class="compare-check" data-compare="${escape(change.revision)}"
                 data-compare-label="${escape(change.description || change.message)}"
                 ${isNow ? 'data-compare-now="1"' : ""}
                 ${compareChecked ? "checked" : ""}>`
      : ""}
          <span class="what">${escape(change.description || change.message)}${chip}${named}
            ${change.description ? `<span class="auto">${escape(change.message)}</span>` : ""}
          </span>
          <span class="when">${escape(when(change.timestamp))}</span>
          <span class="rev">${escape(change.revision.slice(0, 7))}</span>
          <button class="pen" data-describe="${escape(change.revision)}"
                  title="Describe this change">✎</button>
        </div>
        ${detail}
      </div>`;
}

/**
 * The compare mode's one pick that is not a row: "Current state".
 * Pinned above the list rather than drawn from `_changes[0]`, because
 * the newest entry is not always the current state (decision 9) - and
 * unlike every row, this pick's `data-compare` carries no revision.
 */
export function currentStateRow(checked) {
  return `
      <div class="card current-pick">
        <div class="change penholder">
          <input type="checkbox" class="compare-check" data-compare=""
                 data-compare-label="Current state" ${checked ? "checked" : ""}>
          <span class="what">Current state</span>
        </div>
      </div>`;
}
