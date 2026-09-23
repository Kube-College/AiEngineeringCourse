from dataclasses import dataclass, fields


@dataclass(frozen=True)
class Config:
    poll_seconds: int = 20
    timeout_seconds: int = 1200
    max_iterations: int = 50
    max_active: int = 1
    issue_budget_microusd: int = 5_000_000
    max_fix_cycles: int = 1
    completed_retention_hours: int = 24

    @classmethod
    def from_mapping(cls, values: dict[str, object]) -> "Config":
        unknown = set(values) - {field.name for field in fields(cls)}
        if unknown:
            raise ValueError(f"unknown configuration keys: {', '.join(sorted(unknown))}")
        result = cls(**values)
        for field in fields(cls):
            value = getattr(result, field.name)
            if type(value) is not int or value <= 0:
                raise ValueError(f"{field.name} must be a positive integer")
        if result.max_active != 1:
            raise ValueError("the local controller supports one active execution")
        return result
