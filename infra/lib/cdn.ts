import { Duration, aws_cloudfront as cloudfront, aws_cloudfront_origins as origins, aws_lambda as lambda, aws_s3 as s3 } from 'aws-cdk-lib';
import { Construct } from 'constructs';

export interface SiteDistributionProps {
  readonly bucket: s3.IBucket;
  readonly apiFunction: lambda.IFunction;
}

/**
 * Audio cache policy. CloudFront forwards the viewer's Range header to the origin and caches
 * partial responses on its own, so Range does NOT need to be in the cache key (adding it would
 * fragment the cache). Headers, cookies and query strings are not forwarded: an empty key means
 * one cached object per file. Files are keyed by immutable UUIDs, hence the long TTLs.
 * Compression is off because MP3 is already compressed and gzip would break byte-range math.
 */
function createAudioCachePolicy(scope: Construct): cloudfront.CachePolicy {
  return new cloudfront.CachePolicy(scope, 'AudioCachePolicy', {
    comment: 'Audio and timing files; Range requests handled natively by CloudFront',
    defaultTtl: Duration.days(1),
    minTtl: Duration.seconds(0),
    maxTtl: Duration.days(365),
    headerBehavior: cloudfront.CacheHeaderBehavior.none(),
    cookieBehavior: cloudfront.CacheCookieBehavior.none(),
    queryStringBehavior: cloudfront.CacheQueryStringBehavior.none(),
    enableAcceptEncodingGzip: false,
    enableAcceptEncodingBrotli: false,
  });
}

export function createSiteDistribution(scope: Construct, props: SiteDistributionProps): cloudfront.Distribution {
  const oac = new cloudfront.S3OriginAccessControl(scope, 'BucketOac');
  const appOrigin = origins.S3BucketOrigin.withOriginAccessControl(props.bucket, {
    originPath: '/app',
    originAccessControl: oac,
  });
  const dataOrigin = origins.S3BucketOrigin.withOriginAccessControl(props.bucket, {
    originAccessControl: oac,
  });

  // Function URL has AuthType AWS_IAM; CloudFront signs requests (SigV4) through OAC.
  // Signing a POST/PATCH body requires the VIEWER to send `x-amz-content-sha256` (hex SHA-256 of
  // the body). CloudFront cannot compute it and a CloudFront Function cannot read the body, so
  // there is no safe infra-side fix: the web client must add the header (see infra/README.md).
  // AllViewerExceptHostHeader forwards that header; Host must be excluded or SigV4 breaks.
  const apiOrigin = origins.FunctionUrlOrigin.withOriginAccessControl(
    props.apiFunction.addFunctionUrl({ authType: lambda.FunctionUrlAuthType.AWS_IAM }),
  );

  return new cloudfront.Distribution(scope, 'Distribution', {
    comment: 'Sound Along',
    defaultRootObject: 'index.html',
    priceClass: cloudfront.PriceClass.PRICE_CLASS_100,
    defaultBehavior: {
      origin: appOrigin,
      compress: true,
      viewerProtocolPolicy: cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
      cachePolicy: cloudfront.CachePolicy.CACHING_OPTIMIZED,
      responseHeadersPolicy: cloudfront.ResponseHeadersPolicy.SECURITY_HEADERS,
    },
    additionalBehaviors: {
      '/data/*': {
        origin: dataOrigin,
        allowedMethods: cloudfront.AllowedMethods.ALLOW_GET_HEAD,
        viewerProtocolPolicy: cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
        cachePolicy: createAudioCachePolicy(scope),
      },
      '/api/*': {
        origin: apiOrigin,
        allowedMethods: cloudfront.AllowedMethods.ALLOW_ALL,
        viewerProtocolPolicy: cloudfront.ViewerProtocolPolicy.HTTPS_ONLY,
        cachePolicy: cloudfront.CachePolicy.CACHING_DISABLED,
        originRequestPolicy: cloudfront.OriginRequestPolicy.ALL_VIEWER_EXCEPT_HOST_HEADER,
      },
    },
  });
}
