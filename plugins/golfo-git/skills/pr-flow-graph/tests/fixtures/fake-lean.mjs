/**
 * Stands in for the `lean` executable, which CI does not install: accepts the file unless its
 * source contains the marker a test uses to ask for a rejection.
 */
import { readFileSync } from 'node:fs';

const REJECTION_MARKER = 'REJECT_THIS_MODEL';
const source = readFileSync(process.argv[2], 'utf8');

if (source.includes(REJECTION_MARKER)) {
  process.stderr.write('FlowModel.lean:3:2: error: unsolved goals\n');
  process.exit(1);
}
