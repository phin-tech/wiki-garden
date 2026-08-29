// Shared "active project" — the directory that project-scoped accepts target.
// Persisted per-viewer in localStorage; read by the sidebar control and the
// gate actions alike.
import { validateProject, type ProjectCheck } from "./api";

const KEY = "wg-project";

function initial(): string {
  try {
    return localStorage.getItem(KEY) ?? "";
  } catch {
    return "";
  }
}

export const project = $state<{ path: string; check: ProjectCheck | null }>({
  path: initial(),
  check: null,
});

let timer: ReturnType<typeof setTimeout> | undefined;

export function setProject(path: string) {
  project.path = path;
  try {
    localStorage.setItem(KEY, path);
  } catch {
    /* ignore */
  }
  clearTimeout(timer);
  if (!path.trim()) {
    project.check = null;
    return;
  }
  timer = setTimeout(async () => {
    project.check = await validateProject(path);
  }, 350);
}

// Validate whatever was restored, once, at startup.
if (project.path.trim()) {
  validateProject(project.path).then((c) => (project.check = c));
}
