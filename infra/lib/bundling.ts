import * as path from 'node:path';
import { AssetHashType, BundlingOutput, DockerImage, ILocalBundling } from 'aws-cdk-lib';
import { Code } from 'aws-cdk-lib/aws-lambda';
import { buildSync } from 'esbuild';

/**
 * Bundles the API with the esbuild installed in infra/, so synth works offline and without Docker.
 * (NodejsFunction shells out to `npx esbuild` inside services/api, where esbuild is not installed.)
 * @aws-sdk/* is provided by the Node 22 Lambda runtime.
 */
export function bundleNodeEntry(apiRoot: string, entryRelative: string): Code {
  const local: ILocalBundling = {
    tryBundle(outputDir: string): boolean {
      buildSync({
        entryPoints: [path.join(apiRoot, entryRelative)],
        outfile: path.join(outputDir, 'index.js'),
        bundle: true,
        platform: 'node',
        target: 'node22',
        format: 'cjs',
        minify: true,
        sourcemap: true,
        external: ['@aws-sdk/*'],
        logLevel: 'warning',
      });
      return true;
    },
  };
  return Code.fromAsset(apiRoot, {
    assetHashType: AssetHashType.OUTPUT,
    bundling: {
      // Never used: tryBundle either succeeds or throws. Present only because the API requires an image.
      image: DockerImage.fromRegistry('public.ecr.aws/docker/library/node:22'),
      local,
      outputType: BundlingOutput.AUTO_DISCOVER,
    },
    exclude: ['node_modules', 'test', 'data'],
  });
}
