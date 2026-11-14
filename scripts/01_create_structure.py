"""Create the FireScope project folders. Run from the extracted project directory."""
from pathlib import Path
import argparse

FOLDERS = [
    "data/raw/modis",
    "data/raw/viirs",
    "data/processed",
    "data/harmonized",
    "data/exports",
    "reports/audit",
    "reports/analytics",
    "scripts",
    "notebooks",
    "docs",
]


def main():
    parser = argparse.ArgumentParser(description="Create the FireScope folder structure.")
    parser.add_argument("--root", default=".", help="Project root folder (default: current folder)")
    args = parser.parse_args()
    root = Path(args.root).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    for folder in FOLDERS:
        path = root / folder
        path.mkdir(parents=True, exist_ok=True)
        print(f"Created/checked: {path}")
    print(f"\nFireScope folder structure is ready at: {root}")
    print("Copy the original MODIS CSV into data/raw/modis and the VIIRS CSV into data/raw/viirs.")


if __name__ == "__main__":
    main()
