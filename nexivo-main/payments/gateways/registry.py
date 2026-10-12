from payments.gateways.flutterwave import FlutterwaveClient
from payments.gateways.paystack import PaystackClient
from payments.gateways.stripe_gateway import StripeClient
from payments.models import Payment

_REGISTRY = {
    Payment.Gateway.PAYSTACK: PaystackClient,
    Payment.Gateway.FLUTTERWAVE: FlutterwaveClient,
    Payment.Gateway.STRIPE: StripeClient,
}


def get_gateway_client(gateway_name):
    client_class = _REGISTRY.get(gateway_name)
    if not client_class:
        raise ValueError(f"Unsupported gateway: {gateway_name}")
    return client_class()
