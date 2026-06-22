"""Provider registry. To swap data sources, change PROVIDER in config.py
to any key here. Adding Tradier later = write tradier_provider.py and add
one line to this dict.
"""
from .base import DataProvider, OptionContract
from .yfinance_provider import YFinanceProvider

PROVIDERS = {
    "yfinance": YFinanceProvider,
    # "tradier": TradierProvider,   # drop in later
}


def get_provider(name: str) -> DataProvider:
    if name not in PROVIDERS:
        raise ValueError(f"Unknown provider '{name}'. Options: {list(PROVIDERS)}")
    return PROVIDERS[name]()


__all__ = ["DataProvider", "OptionContract", "get_provider", "PROVIDERS"]
