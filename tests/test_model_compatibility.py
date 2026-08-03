"""Tests for multi-vendor model parameter compatibility.

Every case here corresponds to a real 400 observed against the live gateway while building the
model panel. The gateway exposes OpenAI, Anthropic, Google and Meta models behind one
OpenAI-compatible API, and they disagree about which sampling parameters are legal. Getting this
wrong does not degrade quality quietly — it fails the call outright, which silently drops whole
models from a comparison.
"""

import unittest

from llm_client import (
    LLMClient,
    _is_unsupported_parameter_error,
    _needs_large_token_budget,
    _rejects_temperature,
    _uses_completion_token_budget,
)


class TokenBudgetParameterTests(unittest.TestCase):
    """`max_completion_tokens` vs `max_tokens`."""

    def test_o_series_uses_completion_budget(self):
        for model in ("azure-o3", "azure-o4-mini", "o1", "o3-mini"):
            self.assertTrue(_uses_completion_token_budget(model), model)

    def test_o4_mini_regression(self):
        """The previous substring test listed only o1 and o3, so every o4-mini call 400ed."""
        self.assertTrue(_uses_completion_token_budget("azure-o4-mini"))

    def test_gpt5_and_azure5_families_use_completion_budget(self):
        for model in ("gpt-5.5", "gpt-5.4", "gpt-5.4-nano", "azure-5", "azure-5-mini", "azure-5.2"):
            self.assertTrue(_uses_completion_token_budget(model), model)

    def test_conventional_models_use_max_tokens(self):
        for model in ("azure-4.1", "azure-4.1-mini", "azure-4o", "claude-sonnet-4-6",
                      "gemini-2.5-flash", "llama-3.3-70b", "google/gemma-4-e4b"):
            self.assertFalse(_uses_completion_token_budget(model), model)

    def test_o_pattern_does_not_match_an_embedded_letter_o(self):
        """`llama-3.3-70b` and similar must not be mistaken for the o-series."""
        for model in ("llama-3.3-70b", "gemini-2.5-pro", "claude-opus-4-6"):
            self.assertFalse(_uses_completion_token_budget(model), model)


class TemperatureCompatibilityTests(unittest.TestCase):
    def test_o_series_rejects_temperature(self):
        self.assertTrue(_rejects_temperature("azure-o4-mini"))
        self.assertTrue(_rejects_temperature("azure-o3"))

    def test_gpt5_family_rejects_temperature(self):
        for model in ("gpt-5.5", "gpt-5.4-mini", "azure-5", "azure-5-mini"):
            self.assertTrue(_rejects_temperature(model), model)

    def test_newest_anthropic_models_reject_temperature(self):
        self.assertTrue(_rejects_temperature("claude-opus-4-7"))

    def test_established_anthropic_models_accept_temperature(self):
        for model in ("claude-opus-4-6", "claude-sonnet-4-6", "claude-haiku-4-5"):
            self.assertFalse(_rejects_temperature(model), model)

    def test_conventional_models_accept_temperature(self):
        for model in ("azure-4.1-mini", "azure-4o", "gemini-2.5-flash", "llama-3.3-70b"):
            self.assertFalse(_rejects_temperature(model), model)


class LargeTokenBudgetTests(unittest.TestCase):
    def test_gemini_pro_gets_headroom_for_its_thinking_trace(self):
        """At a 512-token budget it returned truncated JSON: {"verdict": "Not-in-"""
        self.assertTrue(_needs_large_token_budget("gemini-2.5-pro"))

    def test_whole_gemini_family_gets_headroom(self):
        """Flash was initially excluded and truncated 7 of 1,200 panel responses.

        Rare enough to survive a smoke test, frequent enough to put holes in a results table, so the
        rule covers the family rather than the one model observed failing first.
        """
        for model in ("gemini-2.5-pro", "gemini-2.5-flash", "gemini-2.5-flash-lite"):
            self.assertTrue(_needs_large_token_budget(model), model)

    def test_reasoning_families_get_headroom(self):
        for model in ("azure-o3", "gpt-5.5", "azure-5-mini"):
            self.assertTrue(_needs_large_token_budget(model), model)

    def test_ordinary_models_keep_the_requested_budget(self):
        for model in ("azure-4.1-mini", "claude-haiku-4-5", "azure-4o", "llama-3.3-70b"):
            self.assertFalse(_needs_large_token_budget(model), model)


class UnsupportedParameterDetectionTests(unittest.TestCase):
    """The defensive retry must recognise a parameter rejection, not a genuine bad request."""

    def test_recognises_openai_o_series_message(self):
        self.assertTrue(_is_unsupported_parameter_error(
            "litellm.UnsupportedParamsError: O-series models don't support temperature=0.0."
        ))

    def test_recognises_gpt5_message(self):
        self.assertTrue(_is_unsupported_parameter_error(
            "gpt-5 models (including gpt-5-codex) don't support temperature=0.0. "
            "Only temperature=1 is supported."
        ))

    def test_recognises_anthropic_deprecation_message(self):
        self.assertTrue(_is_unsupported_parameter_error(
            'Vertex_aiException BadRequestError - `temperature` is deprecated for this model.'
        ))

    def test_does_not_swallow_unrelated_errors(self):
        for message in ("rate limit exceeded", "context length exceeded",
                        "authentication failed", "model not found"):
            self.assertFalse(_is_unsupported_parameter_error(message), message)


class ResolvedSamplingProvenanceTests(unittest.TestCase):
    """Cross-model comparisons must disclose which models ignored the requested temperature."""

    def _client(self, model):
        client = LLMClient.__new__(LLMClient)
        client.model = model
        client.provider = "azure"
        client._temperature_unsupported = False
        return client

    def test_reports_honoured_temperature_for_a_conventional_model(self):
        resolved = self._client("azure-4.1-mini").resolved_sampling(requested_temperature=0.0)
        self.assertTrue(resolved["temperature_honoured"])
        self.assertEqual(resolved["effective_temperature"], 0.0)
        self.assertEqual(resolved["token_budget_parameter"], "max_tokens")

    def test_reports_provider_default_for_a_model_that_rejects_temperature(self):
        resolved = self._client("gpt-5.5").resolved_sampling(requested_temperature=0.0)
        self.assertFalse(resolved["temperature_honoured"])
        self.assertEqual(resolved["effective_temperature"], "provider_default")
        self.assertEqual(resolved["token_budget_parameter"], "max_completion_tokens")

    def test_runtime_rejection_is_recorded_even_for_an_unrecognised_model(self):
        client = self._client("some-future-model")
        self.assertTrue(client.resolved_sampling(0.0)["temperature_honoured"])
        client._temperature_unsupported = True
        self.assertFalse(client.resolved_sampling(0.0)["temperature_honoured"])


if __name__ == "__main__":
    unittest.main()
