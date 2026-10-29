import assert from 'node:assert/strict';
import { swatchAssetUrl } from '../src/utils/swatchAssets';
import { test } from 'vitest';
test('swatchAssets', () => {
assert.equal(swatchAssetUrl('/assets/a.png'),'/assets/a.png');
assert.equal(swatchAssetUrl('assets/a.png','https://cdn.example/releases/v1/'),'https://cdn.example/releases/v1/assets/a.png');
assert.equal(swatchAssetUrl('/assets/glass_swatch_registry.json','https://cdn.example/releases/v1'),'https://cdn.example/releases/v1/assets/glass_swatch_registry.json');
assert.equal(swatchAssetUrl('https://other.example/a.png','https://cdn.example'),'https://other.example/a.png');
console.log('Local and remote release asset URLs passed.');
});
