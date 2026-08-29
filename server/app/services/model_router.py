from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from app.core.config import settings


class ModelRole(StrEnum):
    ASSISTANT = "assistant"
    EMBEDDING = "embedding"
    EXTRACTION = "extraction"
    GENERAL = "general"
    RERANKING = "reranking"
    RESOLUTION = "resolution"
    SUMMARIZATION = "summarization"
    TRANSCRIPTION = "transcription"
    VISION = "vision"


@dataclass(frozen=True)
class ModelDeployment:
    role: ModelRole
    provider: str
    model: str
    api_key: str
    api_base: str | None = None
    modalities: frozenset[str] = frozenset({"text"})
    supports_structured_output: bool = False
    embedding_dimensions: int | None = None
    timeout_seconds: float = 90.0
    privacy: str = "remote"

    def as_litellm_provider(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "api_key": self.api_key,
            "api_base": self.api_base,
            "provider_name": self.provider,
            "role": self.role.value,
            "timeout_seconds": self.timeout_seconds,
        }


class ModelConfigurationError(RuntimeError):
    pass


class ModelRouter:
    """Capability-first deployment selection over configured AI providers."""

    def deployments_for(self, role: ModelRole) -> list[ModelDeployment]:
        deployments: list[ModelDeployment] = []
        requested_model = self._model_for_role(role)

        if settings.OPENROUTER_API_KEY and requested_model:
            deployments.append(
                ModelDeployment(
                    role=role,
                    provider="openrouter",
                    model=f"openrouter/{requested_model.removeprefix('openrouter/')}",
                    api_key=settings.OPENROUTER_API_KEY,
                    api_base=settings.OPENROUTER_BASE_URL,
                    modalities=self._modalities(role),
                    supports_structured_output=role
                    in {ModelRole.EXTRACTION, ModelRole.RESOLUTION},
                    embedding_dimensions=(
                        settings.EMBEDDING_DIMENSIONS if role == ModelRole.EMBEDDING else None
                    ),
                    timeout_seconds=settings.AI_REQUEST_TIMEOUT_SECONDS,
                )
            )

        if (
            settings.OPENCODE_ZEN_API_KEY
            and role
            in {
                ModelRole.ASSISTANT,
                ModelRole.EXTRACTION,
                ModelRole.GENERAL,
                ModelRole.RESOLUTION,
                ModelRole.SUMMARIZATION,
            }
        ):
            deployments.append(
                ModelDeployment(
                    role=role,
                    provider="opencode_zen",
                    model=f"openai/{settings.OPENCODE_ZEN_MODEL}",
                    api_key=settings.OPENCODE_ZEN_API_KEY,
                    api_base=settings.OPENCODE_ZEN_BASE_URL,
                    supports_structured_output=role
                    in {ModelRole.EXTRACTION, ModelRole.RESOLUTION},
                    timeout_seconds=settings.AI_REQUEST_TIMEOUT_SECONDS,
                )
            )

        if settings.HACK_CLUB_AI_API_KEY:
            hackclub_model = self._hackclub_model(role)
            if hackclub_model:
                deployments.append(
                    ModelDeployment(
                        role=role,
                        provider="hackclub",
                        model=hackclub_model,
                        api_key=settings.HACK_CLUB_AI_API_KEY,
                        api_base=settings.HACK_CLUB_AI_BASE_URL,
                        modalities=self._modalities(role),
                        supports_structured_output=role
                        in {ModelRole.EXTRACTION, ModelRole.RESOLUTION},
                        embedding_dimensions=(
                            settings.EMBEDDING_DIMENSIONS
                            if role == ModelRole.EMBEDDING
                            else None
                        ),
                        timeout_seconds=settings.AI_REQUEST_TIMEOUT_SECONDS,
                    )
                )

        if settings.GEMINI_API_KEY and role != ModelRole.TRANSCRIPTION:
            deployments.append(
                ModelDeployment(
                    role=role,
                    provider="gemini",
                    model=settings.LITELLM_MODEL,
                    api_key=settings.GEMINI_API_KEY,
                    modalities=self._modalities(role),
                    supports_structured_output=role
                    in {ModelRole.EXTRACTION, ModelRole.RESOLUTION},
                    timeout_seconds=settings.AI_REQUEST_TIMEOUT_SECONDS,
                )
            )

        return self._deduplicate(deployments)

    def require(self, role: ModelRole) -> list[ModelDeployment]:
        deployments = self.deployments_for(role)
        if not deployments:
            raise ModelConfigurationError(
                f"No deployment is configured for the {role.value} model role"
            )
        required = self._modalities(role)
        compatible = [item for item in deployments if required <= item.modalities]
        if not compatible:
            raise ModelConfigurationError(
                f"Configured {role.value} deployments do not support "
                f"{', '.join(sorted(required))}"
            )
        return compatible

    def readiness(self) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        for role in ModelRole:
            deployments = self.deployments_for(role)
            result[role.value] = {
                "configured": bool(deployments),
                "providers": [deployment.provider for deployment in deployments],
                "models": [deployment.model for deployment in deployments],
                "required_modalities": sorted(self._modalities(role)),
                "structured_output": [
                    deployment.supports_structured_output for deployment in deployments
                ],
            }
        return result

    @staticmethod
    def _model_for_role(role: ModelRole) -> str | None:
        models = {
            ModelRole.ASSISTANT: settings.ASSISTANT_MODEL,
            ModelRole.EMBEDDING: settings.EMBEDDING_MODEL,
            ModelRole.EXTRACTION: settings.EXTRACTION_MODEL or settings.ASSISTANT_MODEL,
            ModelRole.GENERAL: settings.GENERAL_MODEL or settings.ASSISTANT_MODEL,
            ModelRole.RERANKING: settings.RERANK_MODEL,
            ModelRole.RESOLUTION: (
                settings.RESOLUTION_MODEL
                or settings.EXTRACTION_MODEL
                or settings.ASSISTANT_MODEL
            ),
            ModelRole.SUMMARIZATION: settings.SUMMARY_MODEL or settings.ASSISTANT_MODEL,
            ModelRole.TRANSCRIPTION: settings.TRANSCRIPTION_MODEL,
            ModelRole.VISION: settings.VISION_MODEL,
        }
        return models[role]

    @staticmethod
    def _hackclub_model(role: ModelRole) -> str | None:
        if role == ModelRole.EMBEDDING:
            return settings.EMBEDDING_MODEL
        if role == ModelRole.TRANSCRIPTION:
            return settings.TRANSCRIPTION_MODEL
        if role == ModelRole.VISION and settings.VISION_MODEL is None:
            return None
        return settings.LITELLM_MODEL

    @staticmethod
    def _modalities(role: ModelRole) -> frozenset[str]:
        if role == ModelRole.VISION:
            return frozenset({"text", "image"})
        if role == ModelRole.TRANSCRIPTION:
            return frozenset({"audio"})
        return frozenset({"text"})

    @staticmethod
    def _deduplicate(deployments: list[ModelDeployment]) -> list[ModelDeployment]:
        seen: set[tuple[str, str]] = set()
        unique: list[ModelDeployment] = []
        for deployment in deployments:
            key = (deployment.provider, deployment.model)
            if key in seen:
                continue
            seen.add(key)
            unique.append(deployment)
        return unique


model_router = ModelRouter()
