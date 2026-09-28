"""Stable bridge exceptions shared by clients and adapters."""

from __future__ import annotations


class BridgeError(RuntimeError):
    """Base exception for an actionable bridge failure."""

    code = "bridge_error"
    retriable = False

    def __init__(self, message: str, *, details: dict | None = None) -> None:
        super().__init__(message)
        self.details = details or {}


class ContractError(BridgeError):
    code = "contract_error"


class ConfigurationError(BridgeError):
    code = "configuration_error"


class VKongNotInstalledError(BridgeError):
    code = "vkong_not_installed"


class VKongCLIError(BridgeError):
    code = "vkong_cli_error"

    def __init__(
        self,
        message: str,
        *,
        exit_code: int,
        stderr: str = "",
        cli_code: str | None = None,
        retriable: bool = False,
        details: dict | None = None,
    ) -> None:
        super().__init__(message, details=details)
        self.exit_code = exit_code
        self.stderr = stderr
        self.cli_code = cli_code
        self.retriable = retriable


class OutputPublicationError(BridgeError):
    code = "output_publication_failed"
    retriable = True


class CapabilityUnavailableError(BridgeError):
    """The installed VKong CLI lacks a capability this operation requires."""

    code = "vkong_capability_unavailable"
