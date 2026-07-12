/**
 * Late-bound app registry to avoid circular ES module imports between views.
 * main.js assigns render / navigate / action handlers after all modules load.
 */
export const app = {
  render: null,
  navigate: null,
  actions: {},
};

export function registerActions(map) {
  Object.assign(app.actions, map);
}
