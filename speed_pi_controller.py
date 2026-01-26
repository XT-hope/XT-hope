from dataclasses import dataclass


def clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(value, upper))


def balance_accel_pedal(vehicle_speed_kmh: float) -> float:
    """
    Base accelerator pedal (0-100) to balance drag and rolling resistance.
    The formula assumes vehicle_speed_kmh is in km/h.
    """
    return (
        (0.015 * 9.8 + 1.1016 * vehicle_speed_kmh * vehicle_speed_kmh / 1825 / 3.6 / 3.6)
        / 6
        * 100
    )


@dataclass
class PIParams:
    kp: float
    ki: float
    integral_min: float = -100.0
    integral_max: float = 100.0
    accel_min: float = 0.0
    accel_max: float = 100.0
    brake_min: float = 0.0
    brake_max: float = 100.0


@dataclass
class PedalCommand:
    accel_pedal: float
    brake_pedal: float
    base_accel_pedal: float
    error: float
    control_output: float


class SpeedPIController:
    def __init__(self, params: PIParams) -> None:
        self.params = params
        self.integral = 0.0

    def reset(self, integral_value: float = 0.0) -> None:
        self.integral = integral_value

    def update(self, driverspeed: float, vehicle_speed: float, dt: float) -> PedalCommand:
        if dt <= 0:
            raise ValueError("dt must be positive")

        error = driverspeed - vehicle_speed
        self.integral += error * dt
        self.integral = clamp(
            self.integral, self.params.integral_min, self.params.integral_max
        )

        control = self.params.kp * error + self.params.ki * self.integral
        base = balance_accel_pedal(vehicle_speed)
        net = base + control

        if net >= 0.0:
            accel = clamp(net, self.params.accel_min, self.params.accel_max)
            brake = 0.0
        else:
            accel = 0.0
            brake = clamp(-net, self.params.brake_min, self.params.brake_max)

        return PedalCommand(
            accel_pedal=accel,
            brake_pedal=brake,
            base_accel_pedal=base,
            error=error,
            control_output=control,
        )


def _build_arg_parser():
    import argparse

    parser = argparse.ArgumentParser(
        description="PI speed controller producing accel/brake pedal outputs."
    )
    parser.add_argument("--driverspeed", type=float, required=True)
    parser.add_argument("--vehicle-speed", type=float, required=True)
    parser.add_argument("--dt", type=float, default=0.1)
    parser.add_argument("--kp", type=float, default=1.0)
    parser.add_argument("--ki", type=float, default=0.1)
    parser.add_argument("--integral", type=float, default=0.0)
    return parser


def main() -> None:
    args = _build_arg_parser().parse_args()
    params = PIParams(kp=args.kp, ki=args.ki)
    controller = SpeedPIController(params)
    controller.reset(args.integral)

    command = controller.update(args.driverspeed, args.vehicle_speed, args.dt)
    print("accelpedal:", command.accel_pedal)
    print("brakepedal:", command.brake_pedal)
    print("base_accel:", command.base_accel_pedal)
    print("error:", command.error)
    print("control_output:", command.control_output)


if __name__ == "__main__":
    main()
