import pulumi
import pulumi_aws as aws

stack = pulumi.get_stack()
aws_account_id = aws.get_caller_identity().account_id
aws_region = aws.get_region().name
product_name = f"{stack}_email_catcher"
ses_email_domain = (
    "emails.baldanzasolutions.com"
    if stack.lower() == "prod"
    else f"{stack}-emails.baldanzasolutions.com"
)
pulumi.export("ses_email_domain", ses_email_domain)
cloudfront_web_domain = (
    "emails.baldanzasolutions.com"
    if stack.lower() == "prod"
    else f"{stack}-emails.baldanzasolutions.com"
)
pulumi.export("web_url", f"https://{cloudfront_web_domain}")
log_level = "INFO"
xray_enabled = "true"
disable_public_registration = True
initial_user = {
    "enabled": True,
    "username": f"user@{ses_email_domain}",
    "temporary_password": "F1rstP@ss!",
}

### Stack References ###
route53_stack = pulumi.StackReference("BaldanzaSolutions/aws.922023841991.route53/prod")
route35_email_zone_id = route53_stack.get_output("baldanzasolutions.zone.id")
route35_cloudfront_route35_zone_id = route53_stack.get_output(
    "baldanzasolutions.zone.id"
)

ses_stack = pulumi.StackReference("BaldanzaSolutions/aws.922023841991.ses/prod")
ses_domain_rule_set_name = ses_stack.get_output("baldanza_ses_receiving_rule_set")
