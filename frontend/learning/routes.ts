import type { Route } from './types';
import { courseIds, type CourseId } from './types';
const idPattern = /^[A-Za-z0-9_.:-]{1,100}$/;
export function parseRoute(route: string): { page: string; id: string | null; version: string | null; review: boolean } | null {
  const [page, query, extra] = route.split('?');
  if (extra !== undefined) return null;
  const params = new URLSearchParams(query || '');
  const keys = [...params.keys()];
  if (new Set(keys).size !== keys.length) return null;
  if (page === '#/learn/course') return keys.length === 1 && keys[0] === 'id' && courseIds.includes(params.get('id') as CourseId) ? { page, id: params.get('id'), version: null, review: false } : null;
  if (['#/family', '#/learn', '#/learn/first', '#/learn/courses', '#/learn/start', '#/learning-admin', '#/hackathon', '#/hackathon/intro', '#/portfolio'].includes(page)) return query === undefined ? { page, id: null, version: null, review: false } : null;
  if (!['#/learn/run', '#/learn/works', '#/learn/create'].includes(page)) return null;
  const allowed = page === '#/learn/run' ? ['id', 'view'] : page === '#/learn/create' ? ['id'] : ['id', 'version'];
  if (keys.some(k => !allowed.includes(k))) return null;
  const id = params.get('id'), version = params.get('version');
  if ((id !== null && !idPattern.test(id)) || (version !== null && (!id || !idPattern.test(version)))) return null;
  if (page === '#/learn/run' && (!id || (params.has('view') && params.get('view') !== 'review'))) return null;
  return { page, id, version, review: params.get('view') === 'review' };
}
export const validRoute = (r: string): r is Route => parseRoute(r) !== null;
export const runRoute = (id: string): Route => `#/learn/run?id=${encodeURIComponent(id)}`;
export const creativeRoute = (id: string): Route => `#/learn/create?id=${encodeURIComponent(id)}`;
export const courseRoute = (id: CourseId): Route => `#/learn/course?id=${id}`;
