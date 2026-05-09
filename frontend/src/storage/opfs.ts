import type { Project } from '../types';
import { EMPTY_PROJECT } from '../defaultProject';

const FILENAME = 'vitraux-project.json';
const LS_MIGRATION_KEY = 'vitraux-project';

export async function loadProjectFromOPFS(): Promise<Project> {
  try {
    const root = await navigator.storage.getDirectory();
    const handle = await root.getFileHandle(FILENAME);
    const file = await handle.getFile();
    return JSON.parse(await file.text()) as Project;
  } catch {
    return migrateFromLocalStorage();
  }
}

async function migrateFromLocalStorage(): Promise<Project> {
  try {
    const raw = localStorage.getItem(LS_MIGRATION_KEY);
    if (!raw) return EMPTY_PROJECT;
    const project = JSON.parse(raw) as Project;
    await saveToOPFS(project);
    localStorage.removeItem(LS_MIGRATION_KEY);
    return project;
  } catch {
    return EMPTY_PROJECT;
  }
}

export async function saveToOPFS(project: Project): Promise<void> {
  try {
    const root = await navigator.storage.getDirectory();
    const handle = await root.getFileHandle(FILENAME, { create: true });
    const writable = await handle.createWritable();
    await writable.write(JSON.stringify(project));
    await writable.close();
  } catch (e) {
    console.error('[OPFS] save failed', e);
  }
}

export async function deleteFromOPFS(): Promise<void> {
  try {
    const root = await navigator.storage.getDirectory();
    await root.removeEntry(FILENAME);
  } catch {
    // file may not exist yet
  }
}
