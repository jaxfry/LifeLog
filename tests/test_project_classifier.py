from datetime import datetime, timezone, timedelta
from LifeLog.config import Settings
from LifeLog.enrichment.project_classifier import ProjectResolver


def test_similarity_and_continuity(tmp_path):
    settings = Settings()
    settings.project_aliases = {}
    settings.project_memory_path = tmp_path / "memory.json"
    settings.project_similarity_threshold = 0.2
    settings.enable_database_fallback = True
    # Disable database usage for this test to use file-based memory
    settings.project_memory_use_db = False
    settings.use_database = False
    resolver = ProjectResolver(settings)

    t1 = datetime.now(timezone.utc)
    # Provide an explicit project name to seed the resolver's memory
    name1 = resolver.resolve("CoolProject", "Work on cool app", "initial commit", t1)
    assert name1 == "CoolProject"

    t2 = t1 + timedelta(minutes=5)
    # Subsequent similar activity without an explicit project should
    # be resolved to the previously known project based on text similarity
    name2 = resolver.resolve(None, "continue working on cool application", None, t2)
    assert name2 == "CoolProject"

    t3 = t2 + timedelta(minutes=40)
    # Unrelated text after a long gap should not be associated with the project
    name3 = resolver.resolve(None, "random unrelated task", None, t3)
    assert name3 is None
