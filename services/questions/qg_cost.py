"""Token prices, with the basis they came from. Costs shown in reports are always labelled with this basis."""
from __future__ import annotations

from dataclasses import dataclass

_BASIS = "AWS Bedrock on-demand, Asia Pacific (Sydney), per aws.amazon.com/bedrock/pricing on 2026-11-03; no US West (Oregon) price was found"

_OREGON = (
    "AWS Price List API (pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonBedrock and AmazonBedrockFoundationModels), "
    "US West (Oregon) us-west-2, on-demand standard tier, regional (not global) inference, per million tokens, retrieved 2026-11-03"
)

@dataclass(frozen=True)
class Price:
    model: str
    input_per_million: float  # USD per million input tokens
    output_per_million: float  # USD per million output tokens
    basis: str


PRICES: dict[str, Price] = {
    "gpt-oss-20b": Price("gpt-oss-20b", 0.0721, 0.3090, _BASIS),
    "gpt-oss-120b": Price("gpt-oss-120b", 0.1545, 0.6180, _BASIS),
    "qwen3-32b": Price("qwen3-32b", 0.1545, 0.6180, _BASIS),
    "nova-micro": Price("nova-micro", 0.035, 0.14, _OREGON),
    "nova-lite": Price("nova-lite", 0.06, 0.24, _OREGON),
    "nova-pro": Price("nova-pro", 0.80, 3.20, _OREGON),
    "llama4-maverick": Price("llama4-maverick", 0.24, 0.97, _OREGON),
    "sonnet-4-5": Price("sonnet-4-5", 3.30, 16.50, _OREGON),
    "opus-4-5": Price("opus-4-5", 5.50, 27.50, _OREGON),
}


def price_for(spec: str) -> Price | None:
    """Find the price for a model spec such as `ollama:gpt-oss:20b` or `bedrock:openai.gpt-oss-20b-1:0`."""
    flat = spec.lower().replace(":", "-").replace(".", "-")
    return next((price for key, price in PRICES.items() if key in flat), None)


def estimate_usd(input_tokens: int, output_tokens: int, price: Price | None) -> float | None:
    if price is None:
        return None
    return input_tokens * price.input_per_million / 1_000_000 + output_tokens * price.output_per_million / 1_000_000
