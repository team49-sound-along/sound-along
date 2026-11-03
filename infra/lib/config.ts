import * as path from 'node:path';

export const REGION = 'us-west-2';
export const PROJECT_TAG = 'sound-along';
export const BUDGET_LIMIT_USD = 500;
export const BUDGET_THRESHOLD_PERCENTS: readonly number[] = [25, 50, 80];

export interface SourcePaths {
  /** services/api root: contains src/aws/lambda.js and package-lock.json. */
  readonly apiRoot: string;
  /** services/generator root: contains the Dockerfile. */
  readonly generatorDir: string;
  /** Built web app (web/dist). Optional at synth time. */
  readonly webDist: string;
}

export function defaultSourcePaths(): SourcePaths {
  const repoRoot = path.resolve(__dirname, '..', '..');
  return {
    apiRoot: path.join(repoRoot, 'services', 'api'),
    generatorDir: path.join(repoRoot, 'services', 'generator'),
    webDist: path.join(repoRoot, 'web', 'dist'),
  };
}
