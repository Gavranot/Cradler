#!/usr/bin/env python
"""
Database migration helper script

Usage:
    python migrate.py upgrade    # Apply all pending migrations
    python migrate.py downgrade  # Rollback one migration
    python migrate.py current    # Show current revision
    python migrate.py history    # Show migration history
    python migrate.py revision "description"  # Create new migration
"""
import sys
import subprocess
from pathlib import Path

# Change to backend directory
backend_dir = Path(__file__).parent
sys.path.insert(0, str(backend_dir))


def run_alembic_command(args: list[str]):
    """Run alembic command with proper environment"""
    cmd = ["alembic"] + args
    result = subprocess.run(cmd, cwd=backend_dir)
    return result.returncode


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    command = sys.argv[1]

    if command == "upgrade":
        # Apply migrations
        target = sys.argv[2] if len(sys.argv) > 2 else "head"
        return run_alembic_command(["upgrade", target])

    elif command == "downgrade":
        # Rollback migrations
        target = sys.argv[2] if len(sys.argv) > 2 else "-1"
        return run_alembic_command(["downgrade", target])

    elif command == "current":
        # Show current revision
        return run_alembic_command(["current"])

    elif command == "history":
        # Show migration history
        return run_alembic_command(["history", "--verbose"])

    elif command == "revision":
        # Create new migration
        if len(sys.argv) < 3:
            print("Error: Please provide a migration description")
            print("Usage: python migrate.py revision 'description'")
            sys.exit(1)
        description = sys.argv[2]
        return run_alembic_command(["revision", "--autogenerate", "-m", description])

    elif command == "heads":
        # Show head revisions
        return run_alembic_command(["heads"])

    elif command == "branches":
        # Show branch points
        return run_alembic_command(["branches"])

    elif command == "stamp":
        # Stamp the database with a specific revision
        if len(sys.argv) < 3:
            print("Error: Please provide a revision")
            print("Usage: python migrate.py stamp <revision>")
            sys.exit(1)
        revision = sys.argv[2]
        return run_alembic_command(["stamp", revision])

    else:
        print(f"Unknown command: {command}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    sys.exit(main())
