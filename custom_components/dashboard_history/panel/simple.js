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
// The chip and the two controls this mode borrows. `rows.js` calls
// itself the pieces a history is drawn from - sections, heads, rows,
// chips - and says both modes build from exactly those; for these
// three that is now true. The pen renames a version, the bin removes
// it, both drawn the same way wherever a version is shown.
const { nowChip, pen, bin } = await import(`./rows.js${PARTS}`);

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
 * The loaded changes one version collected: from its own change
 * downwards, stopping at the next version below it.
 *
 * What has not been loaded is simply not in here. The head is what
 * somebody goes back to and it is always there, so a span the window
 * does not reach costs a fold, not a way back.
 *
 * Its own function because two places need it now: the row for the
 * version, and the current-state block for the version it has been
 * folded together with.
 */
const spanOf = (version, changes) => {
  const start = changes.findIndex((c) => c.revision === version.revision);
  if (start < 0) return [];
  const inside = [];
  for (let i = start; i < changes.length; i += 1) {
    if (i > start && (changes[i].versions || []).length) break;
    inside.push(changes[i]);
  }
  return inside;
};

/**
 * A version's span as the lines behind it, with the note saying how far
 * they reach.
 *
 * "The newest N", not "N": the span starts at the version's own change
 * and walks downwards, so it is cut at the older end whenever the
 * version holds more than the loaded window does. A flat "25 changes in
 * this version" was wrong for a version spanning a hundred - and this
 * mode has no "load older" that could ever make it right, so the label
 * carries the limit instead of waiting for a button that does not exist.
 *
 * Empty for an empty span, which is what makes the caller's fold
 * disappear rather than open onto nothing.
 */
const inThisVersion = (inside) =>
  inside.length
    ? `<p class="stephead">${
        inside.length === 1
          ? "The newest change in this version"
          : `The newest ${inside.length} changes in this version`
      }</p>
       ${steps(inside)}`
    : "";

/**
 * What makes a <details> a remembered fold: the key it is filed under,
 * and whether it is open right now.
 *
 * Both attributes at once, because they are one decision. Written out
 * at each of the two folds on this page, the "is it open" half stood
 * twice in one expression at the box alone - and the panel wires folds
 * by this attribute (`details[data-key]`), so the pair is a contract
 * with something outside this file rather than a bit of markup.
 */
const foldAt = (key, open) =>
  `data-key="${escape(key)}"${open.has(key) ? " open" : ""}`;

/**
 * The changes that are in no version yet, as the lines behind the
 * current-state block, with the note saying how far they reach.
 *
 * The same cut the advanced mode's top section makes, made here from
 * the same list. This is the one thing in that block which hangs on the
 * loaded window, because a change's words only exist for a change that
 * was loaded. The way back does not hang on it, and that is the point
 * of the two being worked out separately rather than from one index.
 *
 * Exact or hedged, and the word "newest" is the whole difference. Where
 * the version bounding these sits in the window, nothing is cut at the
 * older end and the count is the whole truth - the one place in this
 * mode that can say so, since a version row never knows where its own
 * span ends. Where it does not, every loaded change is still rightly in
 * here (the window holds the newest changes, and not one of them
 * carries a mark, so the last version is older than all of them) and
 * only the far end is unknown.
 *
 * Empty for an empty span, like `inThisVersion` - a block with nothing
 * behind it does not offer itself as a way in.
 */
const sinceLastVersion = (changes) => {
  const versioned = changes.findIndex((c) => (c.versions || []).length);
  const bounded = versioned >= 0;
  const loose = bounded ? changes.slice(0, versioned) : changes;
  if (!loose.length) return "";
  const reach = bounded ? "The" : "The newest";
  const span = loose.length === 1 ? "change" : `${loose.length} changes`;
  return `<p class="stephead">${reach} ${span} since the last version</p>
       ${steps(loose)}`;
};

/**
 * The line a version is known by: number, title, date, and the two
 * controls that belong to the tag itself.
 *
 * `back` is what the caller offers on the right - a button, a label, or
 * nothing at all where the caller says that in its own words. Drawn
 * here rather than in each caller because this is the line people read
 * down looking for a version, and two copies of it would drift.
 */
const vhead = (version, back) => {
  const auto = version.automatic
    ? `<span class="auto">saved automatically</span>`
    : "";
  // Nothing where the store has no time to give. A tag made by hand
  // carries none, and a row reading "1 Jan 1970" would put every
  // honest date beside it in doubt.
  const made = version.timestamp
    ? `<span class="made">${escape(when(version.timestamp))}</span>`
    : "";
  return `<span class="vhead penholder">
            <span class="name">${number(version)}</span>
            <span class="grow">${escape(version.title)}${auto}</span>
            ${made}
            ${back}
            ${pen(version)}
            ${bin(version)}
          </span>
          ${
            version.description
              ? `<p class="why">${escape(version.description)}</p>`
              : ""
          }`;
};

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
 * `open` are the folds somebody has opened, by key. It is the element's
 * own bookkeeping and not the browser's: a render builds new <details>,
 * and native state alone shuts the row being worked in - which here
 * would happen on the way to the confirm dialog, since the preview
 * fetch renders before the dialog opens. The advanced mode's sections
 * learned this first; this is the same set.
 *
 * Every fold on this page, the current-state box included. The box used
 * to keep its own flag beside this set, on the grounds that it stands
 * for the live state rather than for a version - and that held until it
 * started carrying a version, at which point which shelf the fact lived
 * on depended on the data. One fold, one store: the box's key is that
 * version's name where the two are drawn as one, and the bare word
 * `now` where they are not. The two cannot collide, because a version's
 * key is a dashboard and a number with a slash between them.
 */
export function renderSimple({
  versions,
  shown = versions,
  changes,
  searching = false,
  open = new Set(),
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

  // The one place you are standing, said in the only vocabulary this
  // mode has. `same_as_now` comes from the server and is worked out
  // against every version, so it is right whether or not that version's
  // commit is in the loaded window.
  //
  // Over every version, never over `shown`: see the note above.
  //
  // More than one version can hold what the dashboard holds - a routine
  // that saves every day collects them by the dozen - and the sentence
  // has always named exactly one of them: the highest numbered, which
  // over a list ordered by number is the first that matches. The rows
  // now name the same one, which is the whole of the fix. Before it,
  // every matching row said "where you are", and a screen answering
  // "where am I" six times answers it not at all.
  const standingOn = versions.find((v) => v.same_as_now) ?? null;
  // Whether the block and the row under it would be the same version
  // said twice - the block naming it in a sentence and the row naming
  // it again, with nothing on that row this block does not offer.
  //
  // Said of `shown[0]` rather than of `versions[0]`, because what the
  // block takes away is a *drawn row*, and the top drawn row is the
  // only one it can take. It reads the same on an unfiltered page and
  // needs no argument about two orderings agreeing; it also carries
  // `standingOn` being a real version, since a null could not equal a
  // row, and `shown` is never empty by the return above.
  //
  // Not merged where the dashboard stands on an *older* version's
  // state, which is where going back leaves you: newer versions are
  // then drawn above the one being stood on, and it is not the top row.
  //
  // Never while searching, and not because the block would read the
  // query - it reads `standingOn` and `changes`, neither of which a
  // search touches. Because the rows are the answer to what somebody
  // typed, and this would take one of the answers out of the list and
  // put it in a box above, where it no longer reads as a hit. With two
  // versions alike enough to match one word, one of them would simply
  // be missing from the list of matches.
  const merged = !searching && standingOn === shown[0];

  // Folded together, the block holds the version's own changes and not
  // its own span. Those two are not a choice between equals: where the
  // live state is a version's state, every change recorded *since* that
  // version is by definition one that left the state where it was -
  // metadata, or an edit and its undo - so the list of them answers
  // nothing. What the version collected is what somebody opened the
  // block to read. The advanced mode still has both.
  //
  // Two spans, two functions. Written as one nested expression with the
  // second span's five working names spelled out beside it, every one
  // of them was computed in the folded case as well and thrown away,
  // and a reader had to work out for each which branch it belonged to.
  const nowBody = merged
    ? inThisVersion(spanOf(standingOn, changes))
    : sinceLastVersion(changes);
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
  // Where the two are folded together the version itself stands where
  // the sentence about it stood - the same line the rows carry, so the
  // number, the title and the date are written where somebody reading
  // down the page already looks for them. The sentence is no loss: it
  // said one thing, and the line says it in the version's own words.
  //
  // Nothing on the right of that line. "where you are" is what the row
  // said there, and the chip beside "Right now" says it already; inside
  // one block the two would sit four lines apart saying one thing twice.
  //
  // Where they are not, the sentence. Kept a name of its own rather
  // than folded into the line below: it is the one thing on this page
  // written as prose, and a nested conditional inside a template inside
  // a ternary earns nothing but the half microsecond of not building it
  // in the folded case.
  //
  // Escaped as it is built, and only here: the sentence used to be
  // escaped a second time on its way out, which turned an ampersand in
  // a dashboard's title into &amp; on the screen.
  const standing = standingOn
    ? `The dashboard is in the state of ${number(standingOn)}${standingOn.title ? ` — ${escape(standingOn.title)}` : ""}.`
    : "The dashboard has changed since the last version was saved.";
  const says = merged ? vhead(standingOn, "") : `<p>${standing}</p>`;
  // What the block says with itself shut. The chip is the advanced
  // mode's - the same function, not the same words typed again - and
  // unlike there it needs no proof: a crowned row has to earn "current
  // state" by matching the live configuration, while "right now" *is*
  // the live state, and the chip labels the box rather than an entry.
  // `standingOn` is the same fact the box's own ring is coloured by.
  const nowHead = `<p class="heading">Right now ${nowChip(Boolean(standingOn))}</p>
      ${says}
      <span class="acts">
        <button class="act ghost" data-version="now">Save this as a version</button>
        ${undo}
      </span>`;
  // Under the version's own name where the box holds that version's
  // changes, and under the bare word otherwise. Where it is a version's
  // name it is the key the advanced mode folds that same span under, so
  // a version opened in one mode is open in the other - and a version
  // just made by the button above comes back open, since the panel puts
  // a created name into this very set.
  //
  // The one thing that must not be read out of this: which mode drew
  // it. The advanced mode folds a version section under the first name
  // its marks list, ordered by the time the tag was made; this reads
  // the first by *number*. Those coincide except where two versions sit
  // on one commit and somebody numbered them out of order, and there
  // the two modes fold under different names. Nobody is wrong, and
  // nothing worse happens than a row coming back shut.
  // The ring's own class, alongside the fold's: whether anything
  // recorded holds this content is a fact about the state, not about
  // whether the box happens to be foldable right now.
  const namedClass = standingOn ? " named" : "";
  const now = nowBody
    ? `<details class="standing${namedClass}" ${foldAt(merged ? standingOn.name : "now", open)}>
         <summary>${nowHead}</summary>
         <div class="vbody">${nowBody}</div>
       </details>`
    : `<div class="standing${namedClass}">${nowHead}</div>`;

  // The version drawn inside the block above is not drawn again here.
  // That is the whole of it: one version, one place on the page - and
  // it is the top row by the condition `merged` was built from, so this
  // takes it off the front rather than searching the list for it.
  const listed = merged ? shown.slice(1) : shown;

  const rows = listed.map((version) => {
    const folded = inThisVersion(spanOf(version, changes));
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
    // What stays visible when the row is shut: the head, and the words
    // somebody wrote about the version. The note is short, it is the
    // one thing on the row nobody else wrote, and putting it behind a
    // click would make the closed row say less than it does today.
    const head = vhead(version, back);
    // A row is a way in only where there is something behind it. Most
    // rows on a dashboard with hundreds of versions have nothing - the
    // window does not reach their changes - and a row that opens onto
    // an empty space is a promise broken as soon as it is taken up.
    if (!folded) return `<div class="vrow"><div class="vsum">${head}</div></div>`;
    return `<details class="vrow" ${foldAt(version.name, open)}>
              <summary class="vsum">${head}</summary>
              <div class="vbody">${folded}</div>
            </details>`;
  });

  return `
    ${now}
    ${rows.join("")}
    ${HINT}`;
}
