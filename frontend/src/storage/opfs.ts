import type { Project } from '../types';

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

export async function loadProjectFromOPFS(name: string = 'default'): Promise<Project | null> {
  try {
    const root = await navigator.storage.getDirectory();
    const handle = await root.getFileHandle(`${name}.json`);
    const file = await handle.getFile();
    return JSON.parse(await file.text()) as Project;
  } catch {
    return null;
  }
}

export async function saveToOPFS(project: Project, name: string = 'default'): Promise<void> {
  try {
    const root = await navigator.storage.getDirectory();
    const handle = await root.getFileHandle(`${name}.json`, { create: true });
    const writable = await (handle as any).createWritable();
    await writable.write(JSON.stringify(project));
    await writable.close();
  } catch (e) {
    console.error('[OPFS] save failed', e);
  }
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
    const project = await loadProjectFromOPFS(name);
    if (!project) continue;
    for (const sheet of project.sheets) {
      if (!sheet.imageUrl || seen.has(sheet.imageUrl)) continue;
      seen.add(sheet.imageUrl);
      out.push({ url: sheet.imageUrl, label: sheet.label, projectName: name });
    }
  }
  return out;
}
