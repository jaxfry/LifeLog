from dataclasses import dataclass, field

CORE_ONTOLOGY_VERSION = "1"


@dataclass(frozen=True)
class PredicateDefinition:
    name: str
    subject_types: frozenset[str] = field(default_factory=lambda: frozenset({"entity"}))
    object_types: frozenset[str] = field(default_factory=lambda: frozenset({"entity"}))
    aliases: frozenset[str] = field(default_factory=frozenset)


class OntologyRegistry:
    """Small, versioned vocabulary gate for canonical memory projections."""

    def __init__(self) -> None:
        self.version = CORE_ONTOLOGY_VERSION
        self.entity_types = {
            "activity",
            "application",
            "assignment",
            "commitment",
            "concept",
            "course",
            "document",
            "domain",
            "event",
            "media",
            "organization",
            "person",
            "place",
            "project",
            "topic",
        }
        definitions = [
            PredicateDefinition("assigned_by"),
            PredicateDefinition("belongs_to"),
            PredicateDefinition("browsed", subject_types=frozenset({"event"})),
            PredicateDefinition("completed"),
            PredicateDefinition("depends_on"),
            PredicateDefinition("derived_from"),
            PredicateDefinition("discussed"),
            PredicateDefinition("concerns", subject_types=frozenset({"event"})),
            PredicateDefinition(
                "for_course",
                subject_types=frozenset({"entity", "event"}),
            ),
            PredicateDefinition("has_topic"),
            PredicateDefinition("inferred_from"),
            PredicateDefinition("is_assignment", subject_types=frozenset({"event"})),
            PredicateDefinition("located_at"),
            PredicateDefinition("mentioned_in"),
            PredicateDefinition("relates_to", aliases=frozenset({"related_to"})),
            PredicateDefinition("scheduled_for"),
            PredicateDefinition("used_app", subject_types=frozenset({"event"})),
        ]
        self.predicates = {definition.name: definition for definition in definitions}
        self.predicate_aliases = {
            alias: definition.name
            for definition in definitions
            for alias in definition.aliases
        }

    def with_manifest(self, manifest: object) -> "OntologyRegistry":
        """Return a bounded registry with manifest-declared compatible additions."""
        registry = OntologyRegistry()
        for definition in getattr(manifest, "ontology_entity_types", []):
            registry.entity_types.add(definition.name)
        for definition in getattr(manifest, "ontology_predicates", []):
            existing = registry.predicates.get(definition.name)
            candidate = PredicateDefinition(
                definition.name,
                subject_types=frozenset(definition.subject_types),
                object_types=frozenset(definition.object_types),
                aliases=frozenset(definition.aliases),
            )
            if existing is not None and existing != candidate:
                raise ValueError(
                    f"ontology predicate {definition.name!r} conflicts with the core definition"
                )
            registry.predicates[definition.name] = candidate
            for alias in definition.aliases:
                prior = registry.predicate_aliases.get(alias)
                if prior is not None and prior != definition.name:
                    raise ValueError(f"ontology alias {alias!r} is already assigned")
                registry.predicate_aliases[alias] = definition.name
        return registry

    def normalize_entity_type(self, value: str) -> tuple[str, bool]:
        normalized = _snake_case(value)
        if normalized in self.entity_types:
            return normalized, True
        return "concept", False

    def normalize_predicate(self, value: str) -> tuple[str, bool]:
        normalized = _snake_case(value)
        canonical = self.predicate_aliases.get(normalized, normalized)
        if canonical in self.predicates:
            return canonical, True
        return "relates_to", False

    def validate_relation(
        self,
        predicate: str,
        *,
        subject_kind: str = "entity",
        object_kind: str = "entity",
    ) -> bool:
        definition = self.predicates.get(predicate)
        return bool(
            definition
            and subject_kind in definition.subject_types
            and object_kind in definition.object_types
        )


def _snake_case(value: str) -> str:
    result = []
    previous_separator = True
    for character in value.casefold().strip():
        if character.isalnum():
            result.append(character)
            previous_separator = False
        elif not previous_separator:
            result.append("_")
            previous_separator = True
    return "".join(result).strip("_")


ontology_registry = OntologyRegistry()
