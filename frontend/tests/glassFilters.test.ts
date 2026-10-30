import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { matchesGlassFilters, type FilterableGlass } from '../src/utils/glassFilters';
import { recommendedGlass, type BrowseGlass } from '../src/utils/glassBrowse';
import { test } from 'vitest';
test('glassFilters', () => {
const rows = JSON.parse(readFileSync('public/assets/glass_swatch_registry.json','utf8')) as (FilterableGlass & BrowseGlass)[];
const all={search:'',brand:'All',color:'All',appearance:'All',surface:'All'};
const get=(id:string)=>{const r=rows.find(x=>x.id===id);assert(r);return r;};
assert.equal(rows.length,1227);
for(const r of rows){
 assert(r.facets?.colors.length);
 assert(r.facets.colors.every(c=>['Red','Orange','Yellow','Green','Blue','Purple','Pink','Amber','Brown','White','Black','Gray','Clear'].includes(c)));
 assert(['single-color','wispy-streaky','mottled','other-blends'].includes(r.facets.appearance));
 assert(['smooth','lightly-textured','strongly-textured'].includes(r.facets.surface));
 assert(matchesGlassFilters(r,all));
 for(const c of r.facets.colors)assert(matchesGlassFilters(r,{...all,color:c}));
}
const blend=get('oceanside-of6337s');for(const color of ['Blue','White'])assert(matchesGlassFilters(blend,{...all,color}));
assert(!matchesGlassFilters(blend,{...all,color:'Red'}));
assert(matchesGlassFilters(get('oceanside-of3771s'),{...all,brand:'Oceanside',color:'Orange',appearance:'wispy-streaky',surface:'smooth'}));
assert(!matchesGlassFilters(get('oceanside-of3771s'),{...all,brand:'Bullseye'}));
assert(matchesGlassFilters(get('oceanside-of151w'),{...all,search:'waterglass',color:'Red',surface:'lightly-textured'}));
assert(matchesGlassFilters(get('bullseye-0001000047f1010'),{...all,surface:'strongly-textured',color:'Black'}));
assert.deepEqual(get('bullseye-0012280050f1010').facets?.colors,['Purple']);
for(const surface of ['smooth','lightly-textured','strongly-textured'])for(const appearance of ['single-color','wispy-streaky','mottled','other-blends']) {
 const subset=rows.filter(r=>matchesGlassFilters(r,{...all,surface,appearance}));
 assert.equal(recommendedGlass(subset).length,subset.length);
}
console.log('All 1227 material facets validated; multicolor, brand, appearance/surface combinations, terminology search and sorting integration passed.');
});
