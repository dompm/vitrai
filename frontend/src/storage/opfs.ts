import type { Project } from '../types';
import { parseProject } from './projectSchema';

export async function listProjects(): Promise<string[]> {
  try {
    const root = await navigator.storage.getDirectory();
    const names: string[] = [];
    for await (const name of (root as any).keys()) {
      if (name.endsWith('.json')) names.push(name.replace('.json', ''));
    }
    return names;
  } catch {
    return [];
  }
}

/**
 * Load a project. Returns null only when the file genuinely doesn't exist;
 * any other failure (corrupt JSON, failed validation, transient OPFS error)
 * throws so callers never mistake a broken-but-present project for a fresh
 * start.
 *
 * Runs the file through `parseProject`, so legacy unversioned files are
 * migrated and a file with a newer-than-supported `version` is rejected.
 * Any pieces/sheets dropped during repair are logged but not surfaced —
 * auto-loads stay lenient; explicit imports (App.tsx) show the warning.
 */
export async function loadProjectFromOPFS(name: string = 'default'): Promise<Project | null> {
  const root = await navigator.storage.getDirectory();
  let handle: FileSystemFileHandle;
  try {
    handle = await root.getFileHandle(`${name}.json`);
  } catch (e) {
    if (e instanceof DOMException && e.name === 'NotFoundError') return null;
    throw e;
  }
  const file = await handle.getFile();
  const raw = JSON.parse(await file.text());
  const result = parseProject(raw);
  if (!result.ok) {
    throw new Error(`Project "${name}" failed validation: ${result.reasonKey}`);
  }
  if (result.repairs.length > 0) {
    console.warn(`[opfs] repaired project "${name}" on load:`, result.repairs);
  }
  return result.project;
}

export async function saveToOPFS(project: Project, name: string = 'default'): Promise<void> {
  const root = await navigator.storage.getDirectory();
  const handle = await root.getFileHandle(`${name}.json`, { create: true });
  const writable = await (handle as any).createWritable();
  await writable.write(JSON.stringify(project));
  await writable.close();
}

export async function deleteFromOPFS(name: string): Promise<void> {
  try {
    const root = await navigator.storage.getDirectory();
    await root.removeEntry(`${name}.json`);
  } catch {
    // file may not exist
  }
}

export interface RecentSheet {
  url: string;
  label: string;
  projectName: string;
}

/**
 * Scan every project in OPFS and return each unique sheet image (by URL).
 * Used by the "Add sheet" dropdown to surface glass the user has already used.
 */
export async function listAllSheetsAcrossProjects(excludeProjectName?: string): Promise<RecentSheet[]> {
  const names = await listProjects();
  const seen = new Set<string>();
  const out: RecentSheet[] = [];
  for (const name of names) {
    if (name === excludeProjectName) continue;
    let project: Project | null = null;
    try {
      project = await loadProjectFromOPFS(name);
    } catch {
      // skip unreadable projects; this list is best-effort
    }
    if (!project) continue;
    for (const sheet of project.sheets) {
      if (!sheet.imageUrl || seen.has(sheet.imageUrl)) continue;
      seen.add(sheet.imageUrl);
      out.push({ url: sheet.imageUrl, label: sheet.label, projectName: name });
    }
  }
  return out;
}
