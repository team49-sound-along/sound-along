import { GetObjectCommand } from "@aws-sdk/client-s3";

/** Reads the stored job input raw/<passageId>.json from S3. Returns null when it does not exist. */
export function createS3Sources({ s3, bucket }) {
  return {
    async read(passageId) {
      try {
        const res = await s3.send(new GetObjectCommand({ Bucket: bucket, Key: `raw/${passageId}.json` }));
        return JSON.parse(await res.Body.transformToString());
      } catch (err) {
        if (err?.name === "NoSuchKey" || err?.$metadata?.httpStatusCode === 404 || err instanceof SyntaxError) return null;
        throw err;
      }
    },
  };
}
