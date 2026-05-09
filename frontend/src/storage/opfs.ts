import type { Project } from '../types';
import { EMPTY_PROJECT } from '../defaultProject';

const FILENAME = 'vitraux-project.json';

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
