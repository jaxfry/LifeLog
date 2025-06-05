import json
from LifeLog.models import TimelineEntry


def test_parse_contract_example():
    sample = json.loads(
        """
        [
          {
            "start": "2025-05-12T17:00:00Z",
            "end":   "2025-05-12T18:30:00Z",
            "activity": "3D modelling",
            "project": "Renewable Energy Dam",
            "location": null,
            "notes": "Worked in Blender refining the turbine house geometry."
          }
        ]
        """
    )
    TimelineEntry(**sample[0])   # should not raise
