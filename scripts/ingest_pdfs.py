"""Ingest one PDF or a policy directory into Qdrant and PostgreSQL."""

import argparse
import asyncio
import json
import logging
from pathlib import Path

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import Settings, settings
from app.rag.ingest import PolicyIngestor
from app.services.policy_service import PolicyService

logger = logging.getLogger(__name__)


def policy_targets(args: argparse.Namespace) -> list[tuple[Path, str]]:
    source = args.source.expanduser().resolve(strict=True)
    if source.is_file():
        if source.suffix.lower() != ".pdf":
            raise ValueError("Source file must be a PDF")
        if args.manifest:
            raise ValueError("--manifest is only supported for a directory")
        number = args.policy_number if args.policy_number is not None else source.stem
        if not number.strip():
            raise ValueError("Policy number must not be empty")
        return [(source, number)]
    if not source.is_dir():
        raise ValueError("Source must be a PDF file or a directory")
    if args.policy_number is not None:
        raise ValueError("--policy-number is only supported for a single PDF")
    files = sorted(path for path in source.rglob("*") if path.is_file() and path.suffix.lower() == ".pdf")
    if not files:
        raise ValueError("No PDF files found in source directory")
    if args.manifest:
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        if not isinstance(manifest, dict) or any(
            not isinstance(key, str) or not isinstance(value, str) or not value.strip()
            for key, value in manifest.items()
        ):
            raise ValueError("Manifest must map relative PDF paths to nonempty policy numbers")
        available = {path.relative_to(source).as_posix(): path for path in files}
        unknown = set(manifest) - set(available)
        if unknown:
            raise ValueError(f"Manifest references missing PDF files: {', '.join(sorted(unknown))}")
        if not manifest:
            raise ValueError("Manifest must contain at least one PDF mapping")
        targets = [(available[name], number) for name, number in sorted(manifest.items())]
    else:
        targets = [(path, path.stem) for path in files]
    numbers = [number for _, number in targets]
    if len(set(numbers)) != len(numbers):
        raise ValueError("Each policy must map to exactly one PDF; combine multi-file policies first")
    return targets


async def ingest_targets(
    targets: list[tuple[Path, str]], config: Settings, *, fail_fast: bool
) -> int:
    engine = create_async_engine(config.database_url, pool_pre_ping=True)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    ingestor = None
    successful = 0
    failed = 0
    try:
        ingestor = PolicyIngestor(config)
        for path, number in targets:
            try:
                async with sessions() as session:
                    result = await PolicyService(session, ingestor).ingest_pdf(number, path)
                successful += 1
                logger.info(
                    "Indexed %s for %s: %d pages, %d chunks",
                    path.name, number, result.page_count, result.chunk_count,
                )
            except Exception:
                failed += 1
                logger.exception("Ingestion failed for %s (policy %s)", path.name, number)
                if fail_fast:
                    break
    finally:
        if ingestor is not None:
            ingestor.close()
        await engine.dispose()
    logger.info(
        "Ingestion finished: %d succeeded, %d failed, %d skipped",
        successful, failed, len(targets) - successful - failed,
    )
    return 1 if failed else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="PDF file or directory (searched recursively)")
    parser.add_argument("--policy-number", help="Existing policy number for a single PDF; default: filename stem")
    parser.add_argument("--manifest", type=Path, help="JSON mapping relative PDF paths to existing policy numbers")
    parser.add_argument("--qdrant-url", help="Override QDRANT_URL")
    parser.add_argument("--database-url", help="Override DATABASE_URL using postgresql+asyncpg://")
    parser.add_argument("--fail-fast", action="store_true", help="Stop after the first failed document")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    try:
        targets = policy_targets(args)
        values = settings.model_dump()
        if args.qdrant_url:
            values["qdrant_url"] = args.qdrant_url
        if args.database_url:
            values["database_url"] = args.database_url
        config = Settings.model_validate(values)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    try:
        return asyncio.run(ingest_targets(targets, config, fail_fast=args.fail_fast))
    except KeyboardInterrupt:
        logger.error("Ingestion interrupted")
        return 130
    except Exception:
        logger.exception("Unable to start policy ingestion")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
