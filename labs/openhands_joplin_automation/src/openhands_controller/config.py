from dataclasses import dataclass, fields


@dataclass(frozen=True)
class Config:
    poll_seconds: int = 20
    timeout_seconds: int = 1200
    max_iterations: int = 50
    max_active: int = 1
    issue_budget_microusd: int = 5_000_000
    dispatch_estimate_microusd: int = 1_000_000
    max_fix_cycles: int = 1
    completed_retention_hours: int = 24

    def __post_init__(self):
        for field in fields(type(self)):
            value = getattr(self, field.name)
            if type(value) is not int or value <= 0:
                raise ValueError(f"{field.name} must be a positive integer")
        if self.max_active != 1:
            raise ValueError("the local controller supports one active execution")

    @classmethod
    def from_mapping(cls, values: dict[str, object]) -> "Config":
        unknown = set(values) - {field.name for field in fields(cls)}
        if unknown:
            raise ValueError(f"unknown configuration keys: {', '.join(sorted(unknown))}")
        return cls(**values)
