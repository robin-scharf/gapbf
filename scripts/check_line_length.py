from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

WARNING_LIMIT = 200
ERROR_LIMIT = 250
REPO_ROOT = Path(__file__).resolve().parents[1]

SKIP_FILE_NAMES = {
    "config.yaml.backup",
    "test.csv",
    "uv.lock",
}
SKIP_SUFFIXES = {
    ".css",
    ".pyc",
}
SKIP_DIR_NAMES = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
}


@dataclass(frozen=True, slots=True)
class Violation:
    path: Path
    line_number: int
    line_length: int
    threshold: str


def should_skip(path: Path) -> bool:
    if path.name in SKIP_FILE_NAMES:
        return True
    if path.suffix in SKIP_SUFFIXES:
        return True
    return any(part in SKIP_DIR_NAMES for part in path.parts)


def iter_candidate_files(root: Path) -> list[Path]:
    return sorted(
        path
        for path in root.rglob("*")
        if path.is_file() and not should_skip(path.relative_to(root))
    )


def collect_violations(paths: list[Path]) -> tuple[list[Violation], list[Violation]]:
    warnings: list[Violation] = []
    errors: list[Violation] = []

    for path in paths:
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError:
            continue

        relative_path = path.relative_to(REPO_ROOT)
        for line_number, line in enumerate(lines, start=1):
            line_length = len(line)
            if line_length > ERROR_LIMIT:
                errors.append(
                    Violation(relative_path, line_number, line_length, f"> {ERROR_LIMIT}")
                )
            elif line_length > WARNING_LIMIT:
                warnings.append(
                    Violation(relative_path, line_number, line_length, f"> {WARNING_LIMIT}")
                )

    return warnings, errors


def print_group(title: str, violations: list[Violation]) -> None:
    if not violations:
        return

    print(title)
    for violation in violations:
        print(
            f"  {violation.path}:{violation.line_number} "
            f"({violation.line_length} chars, {violation.threshold})"
        )


def main() -> int:
    warnings, errors = collect_violations(iter_candidate_files(REPO_ROOT))

    print_group(
        f"Line-length warnings ({WARNING_LIMIT + 1}-{ERROR_LIMIT} characters):",
        warnings,
    )
    print_group(
        f"Line-length failures ({ERROR_LIMIT + 1}+ characters):",
        errors,
    )

    if errors:
        print(
            "\nCommit blocked: wrap lines to 250 characters or fewer. "
            "Lines over 200 characters are warnings only."
        )
        return 1

    if warnings:
        print("\nWarnings only: commit allowed.")
    else:
        print("No line-length issues detected.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())