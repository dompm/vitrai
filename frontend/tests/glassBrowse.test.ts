import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { recommendedGlass, type BrowseGlass } from '../src/utils/glassBrowse';
import { test } from 'vitest';
test('glassBrowse', () => {
const rows = JSON.parse(readFileSync('public/assets/glass_swatch_registry.json', 'utf8')) as (BrowseGlass & { category: string })[];
assert(rows.every(x => x.browse?.version === 1 && x.browse.reason && x.browse.family));
const sorted = recommendedGlass(rows);
assert.equal(sorted.length, rows.length);
assert.equal(new Set(sorted.map(x => x.id)).size, rows.length);
assert.deepEqual(recommendedGlass([...rows].reverse()).map(x => x.id), sorted.map(x => x.id));
const tier = (x: BrowseGlass) => ['everyday','character','specialty'].indexOf(x.browse!.group);
function check(list: BrowseGlass[]) {
 const result = recommendedGlass(list);
 assert.equal(result.length,list.length);
 for(let i=1;i<result.length;i++) assert(tier(result[i])>=tier(result[i-1]));
 return result;
}
check(rows);
for(const color of new Set(rows.map(x=>x.browse?.color ?? x.color_family))) check(rows.filter(x=>(x.browse?.color ?? x.color_family)===color));
for(const brand of new Set(rows.map(x=>x.manufacturer))) check(rows.filter(x=>x.manufacturer===brand));
for(const category of new Set(rows.map(x=>x.category))) check(rows.filter(x=>x.category===category));
for(const brand of new Set(rows.map(x=>x.manufacturer))) for(const color of new Set(rows.map(x=>x.browse?.color))) check(rows.filter(x=>x.manufacturer===brand && x.browse?.color===color));
for(const q of ['red','clear','wispy','iridescent']) check(rows.filter(x=>x.name.toLowerCase().includes(q)));
const first = sorted.slice(0,40);
assert(first.every(x=>x.browse!.group==='everyday'));
assert(new Set(first.map(x=>x.manufacturer)).size===4);
assert(new Set(first.map(x=>x.color_family)).size>=10);
assert(first.filter(x=>x.browse!.style==='blend').length>=6);
assert(first.some(x=>x.browse!.style==='waterglass'));
for(const id of ['wissmach-w01hirid','wissmach-wi9001cut','youghiogheny-yd5107x9','youghiogheny-yd9107x9']) assert.equal(rows.find(x=>x.id===id)?.browse?.group,'specialty');
for(const id of ['oceanside-of152w','oceanside-of161s','oceanside-of3771s','oceanside-of6337s']) assert.equal(rows.find(x=>x.id===id)?.browse?.group,'everyday');
assert.deepEqual(recommendedGlass([]),[]);
assert.deepEqual(recommendedGlass([rows[0]]),[rows[0]]);
const unknown={...rows[0],id:'future-glass',browse:undefined};assert.equal(recommendedGlass([unknown,...rows]).at(-1)?.id,unknown.id);
console.log('Catalog-wide ordering checks passed: coverage, determinism, tiers, filtered views, palette/style/brand diversity and user examples.');
});
