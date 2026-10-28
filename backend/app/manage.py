import argparse
import asyncio
import sys

from app.database import async_session_maker, engine
from app.services.system.credentials import CredentialError, migrate_credentials
from app.services.system.migrations import adopt_baseline, check_schema_current


async def run(action: str):
    try:
        if action == "adopt-baseline":
            async with engine.begin() as connection:
                await connection.run_sync(adopt_baseline)
            print("Verified baseline adopted and upgraded")
        else:
            async with engine.connect() as connection:
                await connection.run_sync(check_schema_current)
            async with async_session_maker() as db:
                count = await migrate_credentials(db)
            print(f"Credential migration committed: {count} values converted")
    finally:
        await engine.dispose()


def main():
    parser = argparse.ArgumentParser(description="Explicit administration. Before either operation, create and verify a restricted database backup using your deployment backup process. This command never creates a backup or plaintext export.")
    parser.add_argument("action", choices=["adopt-baseline", "encrypt-credentials"])
    parser.add_argument("--backup-confirmed", action="store_true", help="Confirm a verified, access-restricted backup exists")
    args = parser.parse_args()
    if not args.backup_confirmed:
        parser.error("A verified backup is required; pass --backup-confirmed only after completing it")
    try:
        asyncio.run(run(args.action))
    except CredentialError:
        print("Credential migration failed: encryption key unavailable, incorrect, or ciphertext invalid; transaction rolled back", file=sys.stderr)
        return 1
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except Exception:
        print("Administration failed; no partial transaction committed. Check database availability and schema.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
