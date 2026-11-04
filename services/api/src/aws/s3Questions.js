import { GetObjectCommand, ListObjectsV2Command, PutObjectCommand } from "@aws-sdk/client-s3";
import { UUID } from "../recordings/rules.js";

const DRAFT_PREFIX = "raw/questions/";
const DRAFT_KEY = /^raw\/questions\/([0-9a-f-]{36})\.draft\.json$/;
// Same rule as the other data files: they change under the same name, so browsers and CloudFront check for a newer one every time.
const REVALIDATE = "public, max-age=0, must-revalidate";
const isMissing = (err) => err?.name === "NoSuchKey" || err?.$metadata?.httpStatusCode === 404;

/**
 * Question drafts and the served questions file on S3.
 *   drafts   raw/questions/<id>.draft.json (outside /data/*, so CloudFront cannot serve them)
 *   served   data/<id>.questions.json      (written only by publish)
 */
export function createS3Questions({ s3, bucket }) {
  return {
    async listDraftIds() {
      const ids = [];
      let token;
      do {
        const res = await s3.send(new ListObjectsV2Command({ Bucket: bucket, Prefix: DRAFT_PREFIX, ContinuationToken: token }));
        for (const { Key } of res.Contents ?? []) {
          const id = Key?.match(DRAFT_KEY)?.[1];
          if (id && UUID.test(id)) ids.push(id);
        }
        token = res.IsTruncated ? res.NextContinuationToken : undefined;
      } while (token);
      return ids;
    },
    async readDraft(id) {
      if (!UUID.test(id)) return null;
      try {
        const res = await s3.send(new GetObjectCommand({ Bucket: bucket, Key: `${DRAFT_PREFIX}${id}.draft.json` }));
        return JSON.parse(await res.Body.transformToString());
      } catch (err) {
        if (isMissing(err) || err instanceof SyntaxError) return null;
        throw err;
      }
    },
    async publish(id, doc) {
      if (!UUID.test(id)) throw new Error("Invalid passage id.");
      await s3.send(new PutObjectCommand({ Bucket: bucket, Key: `data/${id}.questions.json`, Body: JSON.stringify(doc), ContentType: "application/json", CacheControl: REVALIDATE }));
    },
  };
}
