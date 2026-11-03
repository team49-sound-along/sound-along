import { randomUUID } from "node:crypto";
import { HeadObjectCommand, PutObjectCommand } from "@aws-sdk/client-s3";
import { MAX_RECORDING_BYTES, UUID, recordingKey } from "../recordings/rules.js";

const URL_TTL_SECONDS = 15 * 60;
const isMissing = (err) => err?.name === "NotFound" || err?.$metadata?.httpStatusCode === 404;

/**
 * Recordings on S3: the browser PUTs straight to a presigned URL for raw/<id>.audio.
 * `presign(command, { expiresIn })` returns a URL; production binds it to getSignedUrl(s3, ...), tests inject a fake.
 * The signed ContentLength is the declared size (already capped at 25 MB), so S3 rejects a larger body.
 */
export function createS3Recordings({ s3, bucket, presign, expiresIn = URL_TTL_SECONDS }) {
  return {
    async create({ contentType, size }) {
      const recordingId = randomUUID();
      const command = new PutObjectCommand({
        Bucket: bucket,
        Key: recordingKey(recordingId),
        ContentType: contentType,
        ContentLength: Math.min(size, MAX_RECORDING_BYTES),
      });
      const url = await presign(command, { expiresIn });
      return { recordingId, upload: { method: "PUT", url, headers: { "Content-Type": contentType } } };
    },
    async exists(id) {
      if (!UUID.test(id)) return false;
      try {
        await s3.send(new HeadObjectCommand({ Bucket: bucket, Key: recordingKey(id) }));
        return true;
      } catch (err) {
        if (isMissing(err)) return false;
        throw err;
      }
    },
    ref: (id) => ({ key: recordingKey(id) }),
  };
}
