/**
 * Every dialog the panel opens, as markup.
 *
 * Out of `_render` because they are the half of it that never changes:
 * the same four elements are in the shadow root whatever mode is on and
 * whichever dashboard is picked. What differs is what gets written into
 * their `.body` before they are shown, and that stays in the class,
 * where the data is.
 */

export const DIALOGS = `
  <dialog class="confirm">
    <h2></h2>
    <div class="body"></div>
    <div class="keep" data-keep hidden>
      <label>
        <input type="checkbox" class="keepbox">
        <span>Save the state you are leaving as a version</span>
      </label>
      <input class="text keeptitle" type="text" maxlength="200"
             placeholder="What to call it">
      <p class="muted" style="font-size:13px">
        Kept either way — without a name it is only findable in the
        advanced view. Nothing is deleted.
      </p>
    </div>
    <div class="actions">
      <span class="note muted" style="margin-right:auto"></span>
      <button class="act ghost" value="cancel">Cancel</button>
      <button class="act" value="apply">Apply</button>
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
      <input class="text title" type="text" maxlength="200"
             placeholder="What is this version?">
      <input class="text desc" type="text" maxlength="500"
             style="margin-top:8px"
             placeholder="Anything more worth remembering (optional)">
    </div>
    <div class="actions">
      <button class="act ghost" value="cancel">Cancel</button>
      <button class="act" value="create">Create</button>
    </div>
  </dialog>`;
