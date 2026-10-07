"""Score a whole run: every query against the criteria, then the overall verdict."""

from dataclasses import dataclass

from eval.harness.criteria import CriteriaConfig, QueryEvaluation, evaluate_query
from eval.harness.labels import LabelSet
from eval.harness.runstore import LoadedRun
from eval.harness.verdict import Verdict, overall_verdict


@dataclass(frozen=True)
class ScoredRun:
    loaded: LoadedRun
    evaluations: tuple[QueryEvaluation, ...]
    verdict: Verdict
    config: CriteriaConfig
    labelled: bool
    """True when a labelling sheet was imported, so good@10 is a person's judgement."""


def score_run(
    loaded: LoadedRun,
    *,
    config: CriteriaConfig | None = None,
    labels: LabelSet | None = None,
) -> ScoredRun:
    """Judge each query of ``loaded`` and apply the "most queries" rule."""
    config = config or CriteriaConfig()
    evaluations = tuple(
        evaluate_query(
            run,
            config=config,
            link_checks=loaded.links.get(run.query.id),
            labels=labels,
        )
        for run in loaded.runs
    )
    verdict = overall_verdict(evaluations, config.required_queries)
    return ScoredRun(loaded, evaluations, verdict, config, labels is not None)
