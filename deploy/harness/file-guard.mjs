// Copyright (c) 2026 2292576833. Upstream retains its MIT license.
// Pinned Harness ToolsService.guard: a monotonic denial before tool dispatch.
import { lstatSync } from 'node:fs';

export const name = 'songban-file-guard';
export const inject = ['tools'];
export const allowedFiles = Object.freeze(['index.html', 'style.css', 'script.js']);

/** Pure policy seam; production supplies lstat, offline tests supply metadata. */
export function fileDenial(execution, stat = lstatSync) {
  if (!['read', 'write', 'edit'].includes(execution.name)) return 'Only project file tools are allowed.';
  const args = execution.arguments;
  if (!args || typeof args !== 'object' || Array.isArray(args)) return 'Invalid file arguments.';
  const path = args.file_path;
  // No canonicalization: reject traversal, alternate separators and aliases.
  const file = allowedFiles.find(file => [file, './' + file, '/work/' + file].includes(path));
  if (!file || args.sandbox_permissions || args.justification) return 'Only the three /work project files are allowed.';
  for (const key of ['content', 'old_string', 'new_string']) {
    if (key in args && (typeof args[key] !== 'string' || args[key].length > 18000)) return 'Project file input exceeds limit.';
  }
  try {
    const info = stat('/work/' + file);
    if (info.isSymbolicLink() || !info.isFile() || info.size > 54000) return 'Project target must be a bounded regular file.';
  } catch (error) {
    if (error.code !== 'ENOENT' || execution.name !== 'write') return 'Project target is unavailable.';
  }
  return undefined;
}

export function apply(ctx) {
  ctx.tools.guard(execution => fileDenial(execution));
  // The SDK server explicitly injects this marker before serving initialize.
  ctx.provide('songbanFileGuard', { ready: true });
}
