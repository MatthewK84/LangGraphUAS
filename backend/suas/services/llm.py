"""Report generation service.

Turns a deterministic mission assessment into a short natural-language safety
brief. If no API key is configured, or the model call fails, a deterministic
text summary is returned instead so the endpoint always responds.
"""

import logging
from typing import Final

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from suas.config import Settings
from suas.errors import ReportGenerationError
from suas.schemas.responses import Calculations, WeatherReading

logger: Final[logging.Logger] = logging.getLogger(__name__)

_SYSTEM_PROMPT: Final[str] = (
    "You are an aviation safety officer. Produce a concise go/no-go brief. "
    "Lead with the decision, then the limiting factors. Use active voice."
)


def _fallback_report(is_viable: bool) -> str:
    """Return a deterministic brief when the model is unavailable."""
    decision: str = "GO" if is_viable else "NO-GO"
    return f"Mission status: {decision}. Deterministic assessment only; model narrative unavailable."


def _build_prompt(
    *,
    is_viable: bool,
    aircraft_name: str,
    weather: WeatherReading,
    calculations: Calculations,
) -> str:
    """Return the user prompt describing the mission assessment."""
    decision: str = "GO" if is_viable else "NO-GO"
    flags: str = calculations.safety_flags.model_dump_json()
    return (
        f"Decision: {decision}. Aircraft: {aircraft_name}. "
        f"Temp: {weather.temperature_c} C. Wind: {weather.wind_speed_mps} m/s. "
        f"Density altitude: {calculations.density_altitude_m} m. "
        f"Energy required: {calculations.energy_required_wh} Wh. "
        f"Payload margin: {calculations.payload_margin_kg} kg. Safety flags: {flags}."
    )


class ReportService:
    """Generates safety-officer reports via a chat model."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def _build_model(self) -> ChatOpenAI | None:
        """Return a configured chat model, or None when no key is set."""
        if not self._settings.openai_api_key:
            return None
        return ChatOpenAI(
            model=self._settings.openai_model,
            api_key=SecretStr(self._settings.openai_api_key),
            temperature=0.0,
            timeout=self._settings.llm_timeout_s,
            max_retries=self._settings.llm_max_retries,
        )

    async def generate(
        self,
        *,
        is_viable: bool,
        aircraft_name: str,
        weather: WeatherReading,
        calculations: Calculations,
    ) -> str:
        """Return a natural-language safety brief for the mission."""
        model = self._build_model()
        if model is None:
            return _fallback_report(is_viable)
        prompt: str = _build_prompt(
            is_viable=is_viable,
            aircraft_name=aircraft_name,
            weather=weather,
            calculations=calculations,
        )
        messages = [SystemMessage(content=_SYSTEM_PROMPT), HumanMessage(content=prompt)]
        try:
            response = await model.ainvoke(messages)
        except Exception as exc:
            logger.error("Report generation failed: %s", exc)
            raise ReportGenerationError("Language model call failed") from exc
        return str(response.content)
