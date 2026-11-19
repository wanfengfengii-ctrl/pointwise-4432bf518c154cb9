"""Independent handoff inputs and hand-calculated expectations."""

import json


MODELS = ("A", "B", "C")


def partner_cases():
    cases = {}
    shifts = (
        ("high", (("2", "2"), ("0", None)), (1, 1, 1)),
        ("low", (("2", None), ("0", "2")), (0, 0, 1)),
    )
    for name, positives, expected_auc in shifts:
        contributions = []
        for ticket in ("P", "Q"):
            readings = [("positive", *scores) for scores in positives]
            readings.append(("negative", "1", "1"))
            for label, ab_score, c_score in readings:
                scores = {"A": [[ab_score, 1]], "B": [[ab_score, 1]]}
                if c_score is not None:
                    scores["C"] = [[c_score, 1]]
                contributions.append({"ticket": ticket, "label": label, "count": 1, "scores": scores})
        cases[name] = {
            "package": {
                "version": 2,
                "package_id": f"partner-{name}",
                "source": {"origin": "partner-lab", "station": "Partner", "revision": name},
                "contributions": contributions,
            },
            "expected": {
                "models": MODELS,
                "positive_count": 2,
                "negative_count": 2,
                "auc": expected_auc,
                "deletions": [("P", expected_auc), ("Q", expected_auc)],
                "covariance": [[0, 0, 0] for model in MODELS],
            },
        }
    return cases


if __name__ == "__main__":
    print(json.dumps(partner_cases(), indent=2))
