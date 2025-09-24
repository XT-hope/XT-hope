from __future__ import annotations

from .base import CANoeController
from .com_impl import CANoeCOMController


def create_controller() -> CANoeController:
    """Create the default CANoe controller (COM-based).

    Note: CANoe application lifecycle is managed externally (e.g., Simulink).
    This factory only attaches to the running CANoe via COM.
    """

    return CANoeCOMController()

