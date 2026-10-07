"""Initialize the policy collection without loading or downloading ML models."""

import argparse
import logging

from app.config import Settings, settings
from app.rag.vector_store import create_qdrant_client, ensure_policy_collection
from app.agents.tools.similarity_search import ensure_claim_collection


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qdrant-url", help="Override QDRANT_URL (use localhost for host execution)")
    parser.add_argument("--collection", help="Override QDRANT_POLICY_COLLECTION")
    parser.add_argument("--include-claims", action="store_true", help="Also initialize Phase 3 claim similarity storage")
    args = parser.parse_args()
    values = settings.model_dump()
    if args.qdrant_url:
        values["qdrant_url"] = args.qdrant_url
    if args.collection:
        values["qdrant_policy_collection"] = args.collection
    config = Settings.model_validate(values)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    client = create_qdrant_client(config)
    try:
        name = ensure_policy_collection(client, config)
        logging.info("Policy collection ready: %s (1024 dimensions, cosine)", name)
        if args.include_claims:
            claims = ensure_claim_collection(client, config)
            logging.info("Claim collection ready: %s (1024 dimensions, cosine)", claims)
        return 0
    except Exception:
        logging.exception("Unable to initialize the policy collection")
        return 1
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
