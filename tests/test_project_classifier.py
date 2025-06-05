from datetime import datetime, timezone, timedelta
from LifeLog.config import Settings
from LifeLog.enrichment.project_classifier import ProjectResolver


def test_similarity_and_continuity(tmp_path):
    settings = Settings()
    settings.project_aliases = {}
    settings.project_memory_path = tmp_path / "memory.json"
    settings.project_similarity_threshold = 0.2
    resolver = ProjectResolver(settings)

    t1 = datetime.now(timezone.utc)
    name1 = resolver.resolve(None, "Work on cool app", "initial commit", t1)
    assert name1.startswith("Inferred-")

    t2 = t1 + timedelta(minutes=5)
    name2 = resolver.resolve(None, "continue working on cool application", None, t2)
    assert name2 == name1

    t3 = t2 + timedelta(minutes=40)
    name3 = resolver.resolve(None, "random unrelated task", None, t3)
    assert name3 != name1
