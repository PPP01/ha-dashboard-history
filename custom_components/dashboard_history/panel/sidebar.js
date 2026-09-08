/**
 * The sidebar's order, borrowed rather than invented.
 *
 * People know their dashboards by where they sit in the sidebar. A list
 * in any other order is a list they have to read; a list in that order
 * is one they recognise. So this does not sort - it reproduces what
 * Home Assistant's own `ha-sidebar` would show, and the rules below
 * were read out of the frontend it ships with (`computePanels` and its
 * `panelSorter`, frontend 20260729.7) rather than guessed at.
 *
 * That order cannot come from the server. It is not a property of a
 * dashboard at all: it lives in each user's own frontend data
 * (`frontend/get_user_data`, key `sidebar`), so two people in one house
 * have two different ones. Hence a pure function here, fed from the
 * browser, and a caller that leaves the list alone when it cannot be
 * fed - see `_renderSide`.
 */

// A dashboard's key *is* its url_path. The exception is the default
// dashboard, which has no path of its own: the store calls it
// `_default` (DEFAULT_DASHBOARD_KEY in const.py) and Home Assistant
// registers its panel under the domain name. An installation that gave
// it a registry entry has both spellings for one dashboard.
const DEFAULT_KEY = "_default";
const DEFAULT_PATH = "lovelace";

const pathFor = (key) => (key === DEFAULT_KEY ? DEFAULT_PATH : key);

/**
 * Compare two titles the way the sidebar does.
 *
 * A collator and not `<`: "Ubersicht" belongs after "Mine", which is
 * where a reader looks for it and where a byte comparison does not put
 * it. Guarded, because everything that reaches for the platform here
 * can be missing from it.
 */
function collate(language) {
  try {
    return new Intl.Collator(language).compare;
  } catch {
    return (left, right) => (left < right ? -1 : left > right ? 1 : 0);
  }
}

/**
 * Whether this panel is in the sidebar in front of *this* user.
 *
 * Three ways to be out of it, and the panel makes nothing of the
 * difference: hidden for everybody (`show_in_sidebar`), hidden by this
 * user (`hidden`), or not shown unless asked for (`default_visible`).
 * All three say the same thing to somebody looking for a dashboard -
 * it is not where you last saw it.
 */
const inSidebar = (panel, defaultPanel, order, hidden) =>
  panel.url_path === defaultPanel ||
  (Boolean(panel.title) &&
    panel.show_in_sidebar !== false &&
    !hidden.includes(panel.url_path) &&
    (panel.default_visible !== false || order.includes(panel.url_path)));

/**
 * The recorded dashboards, split into the sidebar's own and the rest.
 *
 * `view` is what the browser knows: `panels` as Home Assistant hands
 * them over, the `defaultPanel` url_path, this user's `order` and
 * `hidden` lists, and the `language` the collator sorts in.
 *
 * Only live dashboards belong here. A deleted one has no panel and no
 * place in a sidebar, and it has a fold of its own.
 */
export function splitBySidebar(dashboards, view) {
  const { panels, defaultPanel, order, hidden, language } = view;
  const compare = collate(language);
  const sidebar = [];
  const apart = [];

  for (const dashboard of dashboards) {
    const panel = panels[pathFor(dashboard.key)];
    // The panel's title over the recorded one wherever there is a
    // panel: it is what the sidebar sorted by, and the recorded one is
    // only as fresh as the last save.
    const entry = {
      dashboard,
      path: panel ? panel.url_path : null,
      title: panel?.title || dashboard.title || "",
    };
    if (panel && inSidebar(panel, defaultPanel, order, hidden)) sidebar.push(entry);
    else apart.push(entry);
  }

  // Reversed, as the sidebar reverses it: the index of a panel nobody
  // arranged is -1, and reading the list backwards makes that the
  // *last* position instead of the first.
  const arranged = [...order].reverse();
  sidebar.sort((left, right) => {
    const here = arranged.indexOf(left.path);
    const there = arranged.indexOf(right.path);
    if (here !== there) return here < there ? 1 : -1;
    // The default dashboard leads whatever else the titles say. The
    // sidebar's further rules - Lovelace before everything, then energy,
    // map, logbook, history - cannot separate two dashboards, and are
    // left where they are rather than copied to no effect.
    if (left.path === defaultPanel) return -1;
    if (right.path === defaultPanel) return 1;
    return compare(left.title, right.title);
  });
  // These have no arrangement by definition, so the title is all there
  // is to go on.
  apart.sort((left, right) => compare(left.title, right.title));

  return {
    sidebar: sidebar.map((entry) => entry.dashboard),
    apart: apart.map((entry) => entry.dashboard),
  };
}

/**
 * A remembered list of url_paths, or nothing.
 *
 * Everything here can throw - a private window, site data switched off
 * - and every failure costs an ordering and never the page.
 */
function remembered(key) {
  try {
    const found = JSON.parse(localStorage.getItem(key));
    if (Array.isArray(found)) return found;
  } catch {
    // Nothing to do and nothing to report: the empty list below is a
    // sidebar nobody has arranged, which is the common case anyway.
  }
  return [];
}

/**
 * This user's arrangement, from their user data or from before it.
 *
 * Home Assistant kept both lists in `localStorage` until it moved them
 * into per-user data, and still falls back to them for anyone who has
 * not been migrated. Falling back on *absence* and not on emptiness is
 * the frontend's own rule, and the right one: an empty `panelOrder` in
 * user data is a deliberate reset, and reaching past it to a stale
 * `localStorage` would undo it.
 */
export function arrangementFrom(stored) {
  return {
    order: stored?.panelOrder ?? remembered("sidebarPanelOrder"),
    hidden: stored?.hiddenPanels ?? remembered("sidebarHiddenPanels"),
  };
}

/**
 * Which panel this user lands on, as the frontend works it out.
 *
 * Only ever matters when it is one of the dashboards: it leads the
 * sidebar, and a list that put it elsewhere would be wrong at the very
 * first line. The three sources and the fallback are the frontend's
 * own, including the check that keeps a stale `lovelace` preference
 * from naming a dashboard that is no longer registered.
 */
export function defaultPanelPath(hass) {
  let preferred = null;
  try {
    preferred = JSON.parse(localStorage.getItem("defaultPanel"));
  } catch {
    // No storage, or nothing valid in it. The sources above it stand.
  }
  const chosen =
    hass.userData?.default_panel ||
    hass.systemData?.default_panel ||
    preferred ||
    "home";
  return chosen !== "lovelace" || hass.panels?.lovelace?.config ? chosen : "home";
}
