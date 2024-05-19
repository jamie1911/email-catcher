import pulumi
import pulumi_aws as aws

stack = pulumi.get_stack()
aws_account_id = aws.get_caller_identity().account_id
aws_region = aws.get_region().name
product_name = f"{stack}_email_catcher"
email_domain = "emails.baldanzasolutions.com"
cloudfront_web_domain = "emails.baldanzasolutions.com"
log_level = "INFO"
xray_enabled = "true"
disable_public_registration = True

### Stack References ###
route53_stack = pulumi.StackReference("BaldanzaSolutions/922023841991-route53/prod")
email_route35_zone_id = route53_stack.get_output("baldanzasolutions.zone.id")
cloudfront_route35_zone_id = route53_stack.get_output("baldanzasolutions.zone.id")
ses_stack = pulumi.StackReference("BaldanzaSolutions/aws.922023841991.ses/prod")
ses_domain_rule_set_name = ses_stack.get_output("baldanza_ses_receiving_rule_set")

# outputs
pulumi.export("email_domain", email_domain)
