import inspect
import pulumi


def get_caller_file():
    # Get the previous frame in the stack, that is, the caller of the function
    frame = inspect.stack()[2]
    module = inspect.getmodule(frame[0])
    return module.__file__ if module else None


# registerAutoTags registers a global stack transformation that merges a set
# of tags with whatever was also explicitly added to the resource definition.
def register_auto_tags(auto_tags):
    pulumi.runtime.register_stack_transformation(lambda args: auto_tag(args, auto_tags))


def register_standard_tags(environment="no-environment"):
    register_auto_tags(
        {
            "environment": environment,
            "pulumi-project": pulumi.get_project(),
            "pulumi-stack": pulumi.get_stack(),
            "iac-system": "pulumi",
            "iac-filepath": get_caller_file(),
        }
    )


# auto_tag applies the given tags to the resource properties if applicable.
def auto_tag(args, auto_tags):
    """Applies the given tags to the resource properties if applicable."""
    if hasattr(args.resource, "tags"):
        args.props["tags"] = {**(args.props["tags"] or {}), **auto_tags}
        return pulumi.ResourceTransformationResult(args.props, args.opts)
