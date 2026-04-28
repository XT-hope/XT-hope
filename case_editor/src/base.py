from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

import pythoncom


class CANoeError(Exception):
    """Raised for CANoe controller related errors."""


class CANoeController(ABC):
    """Abstract base class for controlling CANoe measurement and variables.

    Notes:
        - Implementations MUST NOT start or quit the CANoe application; they
          should only attach to an already running instance.
        - Implementations SHOULD provide sensible timeouts and clear errors.
    """

    @abstractmethod
    def start_measurement(self, timeout_s: float = 10.0) -> None:
        """Start measurement and wait until running or timeout."""

    @abstractmethod
    def stop_measurement(self, timeout_s: float = 10.0) -> None:
        """Stop measurement and wait until stopped or timeout."""

    @abstractmethod
    def is_measurement_running(self) -> bool:
        """Return True if measurement is running."""

    @abstractmethod
    def read_system_variable(self, path: str) -> Any:
        """Read a system variable by hierarchical path (e.g. 'Ns1.Ns2.Var')."""

    @abstractmethod
    def write_system_variable(self, path: str, value: Any) -> None:
        """Write a system variable by hierarchical path (e.g. 'Ns1.Ns2.Var')."""

    @abstractmethod
    def add_system_variable(
        self,
        path: str,
        initialValue,
        minValue=pythoncom.Empty,
        maxValue=pythoncom.Empty,
        isAddNewNamespace: bool = True,
    ) -> None:
        """Add a system variable by hierarchical path (e.g. 'Ns1.Ns2.Var')."""

    @abstractmethod
    def read_environment_variable(self, name: str) -> Any:
        """Read an environment variable by name."""

    @abstractmethod
    def write_environment_variable(self, name: str, value: Any) -> None:
        """Write an environment variable by name."""

    # @abstractmethod
    # def write_environment_variables(self, items) -> None:
    #     """Write more environment variable by items."""

    @abstractmethod
    def read_signal(self, path: str):
        """read signal"""

    @abstractmethod
    def start_logging(self, savePath: str) -> None:
        """Start logging a signal."""

    @abstractmethod
    def stop_logging(self) -> None:
        """Stop logging a signal."""
