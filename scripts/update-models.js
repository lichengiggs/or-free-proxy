import { updateModelsDictionary } from '../src/model-dictionary.ts';

const result = await updateModelsDictionary();

if (!result.success) {
  console.error(`[update-models] failed: ${result.error || 'unknown_error'}`);
  process.exitCode = 1;
} else {
  console.log(`[update-models] updated ${result.count || 0} models -> ${result.path}`);
}
