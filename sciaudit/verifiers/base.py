"""Base verifier interface."""

from __future__ import annotations

from abc import ABC, abstractmethod

from sciaudit.models import Claim, VerificationResult


class BaseVerifier(ABC):
    """Abstract base class for claim verifiers."""

    name: str = "base"

    @abstractmethod
    async def verify(self, claim: Claim) -> VerificationResult:
        """Verify a single claim.

        Args:
            claim: The claim to verify.

        Returns:
            VerificationResult with status, evidence, and explanation.
        """
        ...

    @abstractmethod
    def can_verify(self, claim: Claim) -> bool:
        """Check if this verifier can handle the given claim type.

        Args:
            claim: The claim to check.

        Returns:
            True if this verifier can attempt to verify the claim.
        """
        ...
