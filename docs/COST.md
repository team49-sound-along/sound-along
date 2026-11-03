# Long-run cost for ReadWorks (a free product)

Everything here is an estimate built from ReadWorks' own numbers and AWS list prices. Verify against ReadWorks' CloudFront logs and the AWS pricing pages before relying on it.

## Where the money goes

| Item | When | Cost | Notes |
|---|---|---|---|
| Generating audio for the whole catalog (20M characters) | Once | Kokoro on Lambda: about $26 (estimate: assumes a 4 GB Lambda is 5x slower than the development laptop; not yet measured). On one laptop: free, about 20 hours | Polly Neural for the same text: $320; Polly Standard: $80 |
| Generating a new passage | Per passage | A few cents or less | Only when ReadWorks publishes new content |
| Storing the audio and timing files | Monthly | About 9 GB at 48 kbps: about $0.20 | S3 Standard |
| Serving a passage to a student | Per play | Static files from S3 through CloudFront: no compute | **This is the only cost that grows with usage** |
| Teacher assignments, events (demo API and DynamoDB) | Monthly | Cents | Demo scaffolding; ReadWorks' own CMS replaces it |

## The one large lever: audio file size

Inputs: 1,818,026 audio plays per week (ReadWorks vision document), average passage 212 seconds (20M characters / 6,893 passages at the measured speaking rate). Assumes every play downloads the whole file (upper bound), CloudFront list price of $0.085/GB for the first 10 TB and $0.080/GB for the next 40 TB (second tier from memory), no free tier, no discounts.

| MP3 bitrate | Per play | Per month | CloudFront per month |
|---|---|---|---|
| 128 kbps (the ReadWorks human recording we examined) | 3.39 MB | 26.1 TB | about $2,187 |
| 64 kbps | 1.69 MB | 13.0 TB | about $1,119 |
| **48 kbps (our default)** | 1.27 MB | 9.8 TB | **about $851** |
| 32 kbps | 0.85 MB | 6.5 TB | about $567 |

Measured quality (UTMOS predicted MOS, one generated passage): 32 kbps 4.49, 48 kbps 4.50, 64 kbps 4.51, 128 kbps 4.52. The predictor is a proxy; listen before choosing 32 kbps. The bitrate is the `SOUND_ALONG_MP3_KBPS` setting.

## Ways to bring the bill down further
1. **Lower bitrate** (above): halving the file halves the bill.
2. **AWS nonprofit credits and CloudFront committed-use savings**: both reduce the list price. Check eligibility and current terms.
3. **Serve from any CDN**: the output is plain MP3 and JSON files. A CDN with no egress fee could remove this line; that moves delivery off AWS, so it is ReadWorks' decision.

## How tied to AWS is the build?
- The generator is a Docker image and a Python command line. It ran fully offline on a laptop.
- The product's output is static files (MP3 + JSON) that any host can serve.
- AWS-specific code is thin adapters: S3 and DynamoDB for storage, Step Functions for starting a job, CDK for deployment. The local versions of the same interfaces already exist and are tested.
- The demo API, assignments and dashboard are scaffolding. ReadWorks' production needs the generator, the file format, and the highlighting component.
