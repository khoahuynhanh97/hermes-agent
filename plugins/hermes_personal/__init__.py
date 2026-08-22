from hermes_personal.gateway.plugin import register as register_gateway


def register(ctx) -> None:
    register_gateway(ctx)
