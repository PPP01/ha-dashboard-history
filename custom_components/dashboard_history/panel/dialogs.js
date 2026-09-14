/**
 * Every dialog the panel opens, as markup.
 *
 * Out of `_render` because they are the half of it that never changes:
 * every one of them is in the shadow root whatever mode is on and
 * whichever dashboard is picked. What differs is what gets written into
 * their `.body` before they are shown, and that stays in the class,
 * where the data is.
 *
 * "the same five elements" until a sixth was added and this line was
 * not. A count is a claim about the whole set, and it has to be hunted
 * down every time the set changes - which nothing here would ever fail
 * over, so it goes stale silently. The sentence says the load-bearing
 * part instead, and anybody wanting the number can count the file.
 */

// The quiet line every confirmation ends on, above its buttons. Written
// once because two dialogs show it and it has to read identically in
// both: the moment it differs by a word it stops being the same
// reassurance and starts being two claims. Filled by `_sayFootnote`,
// which is also what hides it where there is nothing to say.
const FOOTNOTE = `
      <div class="footnote" data-footnote hidden>
        <svg viewBox="0 0 20 20" width="16" height="16" fill="currentColor"
             class="footnote__icon" aria-hidden="true">
          <path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clip-rule="evenodd"/>
        </svg>
        <span data-footnote-text></span>
      </div>`;

// The two fields a version's words are typed into, and the one place
// they are spelled. Two dialogs ask for them - one making a version,
// one renaming it - and they have to ask the same way: the classes are
// a contract with `panel.js` and with two test harnesses, and a
// `maxlength` that drifted would let one dialog accept a title the
// other refuses, against the same store.
const VERSION_FIELDS = `
      <input class="text title" type="text" maxlength="200"
             placeholder="What is this version?">
      <input class="text desc" type="text" maxlength="500"
             style="margin-top:8px"
             placeholder="Anything more worth remembering (optional)">`;

export const DIALOGS = `
  <dialog class="confirm">
    <h2></h2>
    <div class="body"></div>
    ${FOOTNOTE}
    <div class="confirm-footer">
      <div class="keep" data-keep hidden>
        <label class="save-checkbox-label">
          <input type="checkbox" class="keepbox">
          <span>Save the state you are leaving as a version</span>
        </label>
        <div class="keepfields" hidden>
          <input class="text keeptitle" type="text" maxlength="200"
                 placeholder="What to call it">
          <p class="muted" style="font-size:13px">
            Kept either way — without a name it is only findable in the
            advanced view. Nothing is deleted.
          </p>
        </div>
      </div>
      <div class="actions">
        <span class="note muted" style="margin-right:auto"></span>
        <button class="act ghost" value="cancel">Cancel</button>
        <button class="act" value="apply">Apply</button>
      </div>
    </div>
  </dialog>
  <dialog class="replace">
    <h2>Replace the whole dashboard</h2>
    <p class="why">The dashboard is set back to a full snapshot.
      Everything saved since is no longer what the dashboard holds.</p>
    <div class="replace-choice" data-replace-choice></div>
    <div class="body"></div>
    ${FOOTNOTE}
    <div class="confirm-footer">
      <div class="keep" data-keep hidden>
        <label class="save-checkbox-label">
          <input type="checkbox" class="keepbox">
          <span>Save the state you are leaving as a version</span>
        </label>
        <div class="keepfields" hidden>
          <input class="text keeptitle" type="text" maxlength="200"
                 placeholder="What to call it">
          <p class="muted" style="font-size:13px">
            Kept either way — without a name it is only findable in the
            advanced view. Nothing is deleted.
          </p>
        </div>
      </div>
      <div class="actions">
        <span class="note muted" style="margin-right:auto"></span>
        <button class="act ghost" value="cancel">Cancel</button>
        <button class="act replace-confirm" value="apply">Replace dashboard</button>
      </div>
    </div>
  </dialog>
  <dialog class="forget">
    <h2>Forget this dashboard for good</h2>
    <div class="body"></div>
    <div class="actions">
      <button class="act ghost" value="cancel">Cancel</button>
      <button class="act danger" value="forget">Delete for good</button>
    </div>
  </dialog>
  <dialog class="describe">
    <h2>Describe this change</h2>
    <div class="body" style="padding:0 16px 8px">
      <input class="text" type="text" maxlength="200"
             placeholder="Why did you change this?">
      <p class="muted" style="font-size:13px">
        This becomes the headline of the entry. The automatic message
        stays below it. Leave it empty to remove the description.
      </p>
    </div>
    <div class="actions">
      <button class="act ghost" value="cancel">Cancel</button>
      <button class="act" value="save">Save</button>
    </div>
  </dialog>
  <dialog class="version">
    <h2>Create a version</h2>
    <div class="body" style="padding:0 16px 8px">
      <p class="muted" style="font-size:13px" data-scope></p>
      <p class="carries" data-carries hidden></p>
      <div class="levels">
        <button type="button" data-level="patch" aria-pressed="true">
          <strong></strong><span>Patch</span>
        </button>
        <button type="button" data-level="minor" aria-pressed="false">
          <strong></strong><span>Minor</span>
        </button>
        <button type="button" data-level="major" aria-pressed="false">
          <strong></strong><span>Major</span>
        </button>
      </div>
      ${VERSION_FIELDS}
    </div>
    <div class="actions">
      <button class="act ghost" value="cancel">Cancel</button>
      <button class="act" value="create">Create</button>
    </div>
  </dialog>
  <dialog class="retitle">
    <h2>Rename this version</h2>
    <div class="body" style="padding:0 16px 8px">
      <p class="muted" style="font-size:13px" data-which></p>
      ${VERSION_FIELDS}
      <p class="muted" style="font-size:13px">
        The two fields of the create dialog, nothing else. The number
        stays as it is: it is the version's name, and going back to a
        version is done by that name. Nothing on the dashboard changes.
      </p>
    </div>
    <div class="actions">
      <button class="act ghost" value="cancel">Cancel</button>
      <button class="act" value="save">Save</button>
    </div>
  </dialog>
  <dialog class="remove">
    <h2>Remove this version</h2>
    <div class="body"></div>
    <div class="actions">
      <button class="act ghost" value="cancel">Cancel</button>
      <button class="act" value="remove">Remove version</button>
    </div>
  </dialog>
  <dialog class="compare">
    <h2>Compare two states</h2>
    <div class="body" data-compare-body></div>
    <div class="actions">
      <button class="act ghost" value="close">Close</button>
    </div>
  </dialog>`;
