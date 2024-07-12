import pulumi
import pulumi_aws as aws
from shared.aws.tagging import register_standard_tags

from config import (
    stack,
    product_name,
    cloudfront_web_domain,
    route35_cloudfront_route35_zone_id,
)

register_standard_tags(environment=stack)

local_name = f"{product_name}_cf"

provider_useast1 = aws.Provider(
    f"{local_name}_provider_useast1",
    region="us-east-1",
    skip_credentials_validation=False,
    skip_metadata_api_check=False,
)
acm_certificate = aws.acm.Certificate(
    f"{local_name}_acm_certificate",
    domain_name=cloudfront_web_domain,
    validation_method="DNS",
    opts=pulumi.ResourceOptions(provider=provider_useast1),
)
acm_certificate_dns = aws.route53.Record(
    f"{local_name}_acm_certificate_dns",
    zone_id=route35_cloudfront_route35_zone_id,
    name=acm_certificate.domain_validation_options[0].resource_record_name,
    records=[acm_certificate.domain_validation_options[0].resource_record_value],
    ttl=60,
    type=acm_certificate.domain_validation_options[0].resource_record_type,
    opts=pulumi.ResourceOptions(depends_on=[acm_certificate]),
)
acm_certificate_validation = aws.acm.CertificateValidation(
    f"{local_name}_acm_certificate_validation",
    certificate_arn=acm_certificate.arn,
    validation_record_fqdns=[acm_certificate_dns.fqdn],
    opts=pulumi.ResourceOptions(provider=provider_useast1),
)

cf_oac = aws.cloudfront.OriginAccessControl(
    f"{local_name}_oac",
    description=f"Origin Access Control for {product_name}",
    origin_access_control_origin_type="s3",
    signing_behavior="always",
    signing_protocol="sigv4",
)

bucket_portal = aws.s3.BucketV2(
    f"{local_name}_bucket_portal",
    bucket=f"{product_name}-portal".replace("_", "-"),
    force_destroy=True,
)

pulumi.export("portal_bucket_name", bucket_portal.bucket)

cf_distribution = aws.cloudfront.Distribution(
    f"{local_name}_distribution",
    enabled=True,
    aliases=[cloudfront_web_domain],
    default_root_object="index.html",
    http_version="http2",
    is_ipv6_enabled=True,
    price_class="PriceClass_100",
    wait_for_deployment=False,
    custom_error_responses=[
        aws.cloudfront.DistributionCustomErrorResponseArgs(
            error_code=404,
            response_code=200,
            response_page_path="/index.html",
        ),
        aws.cloudfront.DistributionCustomErrorResponseArgs(
            error_code=403,
            response_code=200,
            response_page_path="/index.html",
        ),
        aws.cloudfront.DistributionCustomErrorResponseArgs(
            error_code=500,
            response_code=200,
            response_page_path="/index.html",
        ),
    ],
    default_cache_behavior=aws.cloudfront.DistributionDefaultCacheBehaviorArgs(
        allowed_methods=[
            "GET",
            "HEAD",
        ],
        cached_methods=[
            "GET",
            "HEAD",
        ],
        compress=True,
        default_ttl=86400,
        max_ttl=31536000,
        target_origin_id=f"S3_{product_name}",
        viewer_protocol_policy="redirect-to-https",
        forwarded_values=aws.cloudfront.DistributionDefaultCacheBehaviorForwardedValuesArgs(
            query_string=False,
            cookies=aws.cloudfront.DistributionDefaultCacheBehaviorForwardedValuesCookiesArgs(
                forward="none",
            ),
        ),
    ),
    origins=[
        aws.cloudfront.DistributionOriginArgs(
            connection_attempts=3,
            connection_timeout=10,
            domain_name=bucket_portal.bucket_regional_domain_name,
            origin_id=f"S3_{product_name}",
            origin_access_control_id=cf_oac.id,
        )
    ],
    restrictions=aws.cloudfront.DistributionRestrictionsArgs(
        geo_restriction=aws.cloudfront.DistributionRestrictionsGeoRestrictionArgs(
            restriction_type="none",
        ),
    ),
    viewer_certificate=aws.cloudfront.DistributionViewerCertificateArgs(
        acm_certificate_arn=acm_certificate.arn,
        minimum_protocol_version="TLSv1.1_2016",
        ssl_support_method="sni-only",
    ),
    opts=pulumi.ResourceOptions(depends_on=[acm_certificate_validation]),
)
pulumi.export("cf_distribution_id", cf_distribution.id)

bucket_policy_portal = aws.iam.get_policy_document(
    statements=[
        aws.iam.GetPolicyDocumentStatementArgs(
            actions=["s3:GetObject"],
            resources=[pulumi.Output.concat(bucket_portal.arn, "/*")],
            principals=[
                aws.iam.GetPolicyDocumentStatementPrincipalArgs(
                    type="Service",
                    identifiers=["cloudfront.amazonaws.com"],
                )
            ],
            conditions=[
                pulumi.Output.all(cf_distribution=cf_distribution.arn).apply(
                    lambda args: aws.iam.GetPolicyDocumentStatementConditionArgs(
                        test="StringEquals",
                        variable="AWS:SourceArn",
                        values=[args["cf_distribution"]],
                    )
                )
            ],
        )
    ]
)
aws.s3.BucketPolicy(
    f"{local_name}_bucket_policy_portal",
    bucket=bucket_portal.id,
    policy=bucket_policy_portal.json,
)

aws.route53.Record(
    f"{local_name}_route53_record",
    name=cloudfront_web_domain,
    zone_id=route35_cloudfront_route35_zone_id,
    type="A",
    aliases=[
        aws.route53.RecordAliasArgs(
            name=cf_distribution.domain_name,
            zone_id=cf_distribution.hosted_zone_id,
            evaluate_target_health=False,
        )
    ],
)
