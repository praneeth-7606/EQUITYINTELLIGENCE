import json
import logging
import re
from contextvars import ContextVar
from datetime import date
from typing import Any, Optional

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI

from app.config import settings

logger = logging.getLogger("stock_intelligence.llm")
_last_llm_call_info: ContextVar[dict[str, str] | None] = ContextVar("last_llm_call_info", default=None)


def sanitize_markdown_text(text: Any) -> str:
    """Clean common LLM formatting artifacts before data reaches the UI."""
    if text is None:
        return ""
    cleaned = str(text).strip()
    cleaned = re.sub(r"^\s*```(?:markdown|md|text)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```\s*$", "", cleaned)
    cleaned = cleaned.replace("{{current_date}}", date.today().isoformat())
    cleaned = cleaned.replace("{current_date}", date.today().isoformat())
    return cleaned.strip()


def sanitize_structured_response(response: Any) -> Any:
    """Sanitize common string fields on Pydantic structured responses."""
    if response is None:
        return response
    try:
        updates = {}
        if hasattr(response, "summary"):
            updates["summary"] = sanitize_markdown_text(response.summary)
        if hasattr(response, "overall_summary"):
            updates["overall_summary"] = sanitize_markdown_text(response.overall_summary)
        if hasattr(response, "observations"):
            updates["observations"] = [
                sanitize_markdown_text(obs).lstrip("-* ").strip()
                for obs in (response.observations or [])
            ]
        if updates and hasattr(response, "model_copy"):
            return response.model_copy(update=updates)
    except Exception as exc:
        logger.warning(f"Failed to sanitize structured LLM response: {exc}")
    return response


class LLMFactory:
    """
    LLM factory with explicit fallback ordering and call metadata capture.

    Default preference:
    1. Mistral
    2. Grok/Groq
    3. Gemini
    """

    _client_cache: dict[tuple[str, float], BaseChatModel] = {}
    _provider_order = ("mistral", "grok", "gemini")

    @classmethod
    def _set_last_call_info(cls, provider: str, model: str):
        _last_llm_call_info.set({"provider": provider, "model": model})

    @classmethod
    def consume_last_call_info(cls) -> dict[str, str] | None:
        info = _last_llm_call_info.get()
        _last_llm_call_info.set(None)
        return info

    @classmethod
    def _provider_sequence(cls, primary_provider: str = "mistral") -> list[str]:
        ordered: list[str] = []
        if primary_provider in cls._provider_order:
            ordered.append(primary_provider)
        for provider in cls._provider_order:
            if provider not in ordered:
                ordered.append(provider)
        return ordered

    @classmethod
    def _provider_meta(cls, provider: str) -> dict[str, str]:
        if provider == "mistral":
            return {"provider": "mistral", "model": settings.mistral_model or "mistral-large-latest"}
        if provider == "grok":
            if settings.xai_api_key and settings.xai_api_key.startswith("gsk_"):
                return {"provider": "groq", "model": "llama-3.3-70b-versatile"}
            return {"provider": "grok", "model": settings.xai_model or "grok-2-1212"}
        return {"provider": "gemini", "model": "gemini-3.1-flash-lite"}

    @classmethod
    def _init_gemini(cls, temperature: float) -> Optional[BaseChatModel]:
        if not settings.gemini_api_key or "your-gemini" in settings.gemini_api_key:
            logger.info("Gemini API key not set or using placeholder.")
            return None
        try:
            logger.info("Initializing Gemini fallback model.")
            return ChatGoogleGenerativeAI(
                model="gemini-3.1-flash-lite",
                google_api_key=settings.gemini_api_key,
                temperature=temperature,
                timeout=20.0,
                max_retries=0,
            )
        except Exception as exc:
            logger.error(f"Error creating Gemini client: {exc}")
            return None

    @classmethod
    def _init_grok(cls, temperature: float) -> Optional[BaseChatModel]:
        if not settings.xai_api_key or "your-xai" in settings.xai_api_key:
            logger.info("Grok API key not set or using placeholder.")
            return None
        try:
            api_key = settings.xai_api_key
            base_url = settings.xai_api_base
            model = settings.xai_model
            if api_key.startswith("gsk_"):
                logger.info("Groq API key detected. Routing Grok slot to Groq Llama-3.3-70b-versatile.")
                base_url = "https://api.groq.com/openai/v1"
                model = "llama-3.3-70b-versatile"
            logger.info(f"Initializing Grok/Groq fallback model '{model}' via '{base_url}'")
            return ChatOpenAI(
                model=model,
                api_key=api_key,
                base_url=base_url,
                temperature=temperature,
                timeout=15.0,
                max_retries=2,
            )
        except Exception as exc:
            logger.error(f"Error creating Grok/Groq client: {exc}")
            return None

    @classmethod
    def _init_mistral(cls, temperature: float) -> Optional[BaseChatModel]:
        if not settings.mistral_api_key or "your-mistral" in settings.mistral_api_key:
            logger.info("Mistral API key not set or using placeholder.")
            return None
        try:
            logger.info(f"Initializing Mistral primary model '{settings.mistral_model}'")
            return ChatOpenAI(
                model=settings.mistral_model,
                api_key=settings.mistral_api_key,
                base_url=settings.mistral_api_base,
                temperature=temperature,
                timeout=15.0,
                max_retries=2,
            )
        except Exception as exc:
            logger.error(f"Error creating Mistral client: {exc}")
            return None

    @classmethod
    def _get_client(cls, provider: str, temperature: float) -> Optional[BaseChatModel]:
        cache_key = (provider, temperature)
        if cache_key in cls._client_cache:
            return cls._client_cache[cache_key]

        if provider == "mistral":
            client = cls._init_mistral(temperature)
        elif provider == "grok":
            client = cls._init_grok(temperature)
        else:
            client = cls._init_gemini(temperature)

        if client:
            cls._client_cache[cache_key] = client
        return client

    @classmethod
    def get_llm(cls, temperature: float = 0.0, primary_provider: str = "mistral") -> BaseChatModel:
        """Compatibility helper that returns a fallback-wrapped model chain."""
        models: list[BaseChatModel] = []
        for provider in cls._provider_sequence(primary_provider):
            client = cls._get_client(provider, temperature)
            if client:
                models.append(client)
        if not models:
            raise ValueError(
                "API keys are missing. Please configure MISTRAL_API_KEY, XAI_API_KEY, or GEMINI_API_KEY."
            )
        return models[0].with_fallbacks(models[1:]) if len(models) > 1 else models[0]

    @classmethod
    def invoke_text_llm(
        cls,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.0,
        primary_provider: str = "mistral",
    ):
        from langchain_core.messages import HumanMessage, SystemMessage

        last_error: Optional[Exception] = None
        for provider in cls._provider_sequence(primary_provider):
            client = cls._get_client(provider, temperature)
            if not client:
                continue
            meta = cls._provider_meta(provider)
            try:
                response = client.invoke([
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=user_prompt),
                ])
                cls._set_last_call_info(meta["provider"], meta["model"])
                return response
            except Exception as exc:
                last_error = exc
                logger.warning(f"[LLMFactory] Text invoke failed on provider={provider}: {exc}")
        if last_error:
            raise last_error
        raise ValueError("No available LLM providers could be initialized.")

    @classmethod
    def call_structured_llm(
        cls,
        system_prompt: str,
        user_prompt: str,
        response_format_class,
        temperature: float = 0.0,
        primary_provider: str = "mistral",
    ) -> Any:
        """
        Invokes LLM to return a structured Pydantic object.
        Tries providers in explicit order and records the provider/model that succeeded.
        """
        from langchain_core.messages import HumanMessage, SystemMessage

        try:
            schema = response_format_class.model_json_schema()
            schema_str = json.dumps(schema, indent=2)
        except Exception:
            schema_str = "{\n  \"summary\": \"string\",\n  \"observations\": [\"string\"]\n}"

        json_instruction = (
            "\n\nIMPORTANT: You MUST respond with a valid JSON object matching this schema. "
            "Do NOT include any extra prose, markdown wrapper, prefix, or explanation. ONLY return the JSON block.\n"
            "Please escape all internal double quotes as '\\\"' in string fields.\n"
            f"JSON Schema:\n{schema_str}\n"
        )

        last_error: Optional[Exception] = None

        for provider in cls._provider_sequence(primary_provider):
            client = cls._get_client(provider, temperature)
            if not client:
                continue
            meta = cls._provider_meta(provider)

            try:
                logger.info(f"[LLMFactory] Attempting native structured output invoke with provider={provider}...")
                structured_llm = client.with_structured_output(response_format_class)
                result = structured_llm.invoke([
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=user_prompt),
                ])
                cls._set_last_call_info(meta["provider"], meta["model"])
                return sanitize_structured_response(result)
            except Exception as exc:
                last_error = exc
                logger.warning(f"[LLMFactory] Native structured output failed on provider={provider}: {exc}")

            try:
                response = client.invoke([
                    SystemMessage(content=system_prompt + json_instruction),
                    HumanMessage(content=user_prompt),
                ])
                text = response.content if hasattr(response, "content") else str(response)
                text_json = text[text.find("{"):text.rfind("}") + 1] if "{" in text else text
                parsed_json = json.loads(text_json, strict=False)

                if hasattr(response_format_class, "summary") and hasattr(response_format_class, "observations"):
                    summary = parsed_json.get("summary", "")
                    observations = parsed_json.get("observations", [])
                    if isinstance(observations, str):
                        observations = [observations]
                    cls._set_last_call_info(meta["provider"], meta["model"])
                    return sanitize_structured_response(response_format_class(
                        summary=sanitize_markdown_text(summary),
                        observations=[sanitize_markdown_text(obs).lstrip("-* ").strip() for obs in observations],
                    ))

                kwargs = {}
                for field_name, field_info in response_format_class.model_fields.items():
                    default_val = field_info.default
                    if default_val == ... or default_val is None:
                        ann = field_info.annotation
                        if ann == list or getattr(ann, "__origin__", None) == list:
                            default_val = []
                        elif ann == str:
                            default_val = ""
                        elif ann == int:
                            default_val = 0
                        elif ann == float:
                            default_val = 0.0
                        elif ann == dict:
                            default_val = {}
                    value = parsed_json.get(field_name, default_val)
                    if isinstance(value, str):
                        value = sanitize_markdown_text(value)
                    elif isinstance(value, list):
                        value = [sanitize_markdown_text(v).lstrip("-* ").strip() if isinstance(v, str) else v for v in value]
                    kwargs[field_name] = value

                cls._set_last_call_info(meta["provider"], meta["model"])
                return sanitize_structured_response(response_format_class(**kwargs))
            except Exception as exc:
                last_error = exc
                logger.error(f"[LLMFactory] Manual JSON parser failed on provider={provider}: {exc}")

        if last_error:
            raise last_error
        raise ValueError("No available LLM providers could be initialized.")
