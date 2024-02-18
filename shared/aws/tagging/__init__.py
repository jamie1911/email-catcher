import pulumi


# registerAutoTags registers a global stack transformation that merges a set
# of tags with whatever was also explicitly added to the resource definition.
def register_auto_tags(auto_tags):
    pulumi.runtime.register_stack_transformation(lambda args: auto_tag(args, auto_tags))


def register_standard_tags(environment="no-environment"):
    register_auto_tags(
        {
            "pulumi-project": pulumi.get_project(),
            "pulumi-stack": pulumi.get_stack(),
            "iac-system": "pulumi",
            "environment": environment,
        }
    )


# auto_tag applies the given tags to the resource properties if applicable.
def auto_tag(args, auto_tags):
    """Applies the given tags to the resource properties if applicable."""
    if hasattr(args.resource, "tags"):
        args.props["tags"] = {**(args.props["tags"] or {}), **auto_tags}
        return pulumi.ResourceTransformationResult(args.props, args.opts)
