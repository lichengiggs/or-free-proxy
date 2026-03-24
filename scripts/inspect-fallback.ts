#!/usr/bin/env tsx
import { fetchAllModels, isEffectivelyFreeModel } from '../src/models';
import { loadModelDictionary } from '../src/model-dictionary';

async function main() {
  const all = await fetchAllModels();
  const free = all.filter(isEffectivelyFreeModel);
  const dict = await loadModelDictionary();

  const dictIds = new Set((dict?.models || []).map(m => m.id));
  const freeIds = new Set(free.map(m => m.id));

  const missingFromDict = [...freeIds].filter(id => !dictIds.has(id));
  const missingFromFree = [...dictIds].filter(id => !freeIds.has(id));

  console.log(`discovered_total=${all.length}`);
  console.log(`discovered_free=${free.length}`);
  console.log(`dictionary_total=${(dict?.models.length) ?? 0}`);
  console.log(`missing_from_dict=${missingFromDict.length}`);
  if (missingFromDict.length > 0) console.log('missing_from_dict_sample=', missingFromDict.slice(0, 50).join(', '));
  console.log(`missing_from_free=${missingFromFree.length}`);
  if (missingFromFree.length > 0) console.log('missing_from_free_sample=', missingFromFree.slice(0, 50).join(', '));
}

main().catch(err => {
  console.error(err);
  process.exit(1);
});
