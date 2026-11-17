"""Backward-compatible import path for the Azure blob client.

New code should use problems.storage.get_storage().
"""

from problems.storage.azure import AzureBlobManager

__all__ = ["AzureBlobManager"]
