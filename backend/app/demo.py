"""CLI для демо-прогона end-to-end."""

from __future__ import annotations

import argparse
import json
import logging
import sys

from app.config import settings
from app.demo_scenarios import CLI_SCENARIOS
from app.hypotheses.generator import HypothesisGenerator
from app.ingest.pipeline import IngestPipeline

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def run_scenario(scenario_id: str, skip_ingest: bool = False) -> dict:
    scenario = CLI_SCENARIOS[scenario_id]
    logger.info("Сценарий %s: %s", scenario_id, scenario.data_path)

    if not skip_ingest:
        pipeline = IngestPipeline()
        target = settings.data_dir_path / scenario.data_path
        if target.exists():
            results = pipeline.ingest_directory(target)
            logger.info("Проиндексировано файлов: %d", len(results))
        else:
            logger.warning("Папка не найдена: %s", target)

    generator = HypothesisGenerator()
    result = generator.generate(
        problem=scenario.problem,
        constraints=scenario.constraints,
    )
    logger.info(
        "Сгенерировано гипотез: %d, generation_id=%s",
        len(result["hypotheses"]),
        result["generation_id"],
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Демо end-to-end прогон")
    parser.add_argument("--scenario", choices=["1", "2", "3"], default="1")
    parser.add_argument("--skip-ingest", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    try:
        result = run_scenario(args.scenario, skip_ingest=args.skip_ingest)
        if args.json:
            print(
                json.dumps(
                    {
                        "generation_id": result["generation_id"],
                        "hypotheses": [
                            h.model_dump(mode="json") for h in result["hypotheses"]
                        ],
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
    except Exception as exc:
        logger.error("Ошибка: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
