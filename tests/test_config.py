import os
import pytest

from src.config import _expand_env_vars


class TestEnvVarExpansion:
    def test_expand_single_env_var(self):
        os.environ["TEST_VAR"] = "test_value"
        result = _expand_env_vars("url: ${TEST_VAR}")
        assert result == "url: test_value"

    def test_expand_multiple_env_vars(self):
        os.environ["VAR1"] = "value1"
        os.environ["VAR2"] = "value2"
        result = _expand_env_vars("${VAR1}/${VAR2}")
        assert result == "value1/value2"

    def test_expand_dict(self):
        os.environ["SLACK_URL"] = "https://slack.webhook"
        data = {"webhook_url": "${SLACK_URL}"}
        result = _expand_env_vars(data)
        assert result == {"webhook_url": "https://slack.webhook"}

    def test_expand_nested_dict(self):
        os.environ["WEBHOOK"] = "https://webhook.url"
        data = {"destinations": [{"webhook_url": "${WEBHOOK}"}]}
        result = _expand_env_vars(data)
        assert result == {"destinations": [{"webhook_url": "https://webhook.url"}]}

    def test_expand_list(self):
        os.environ["VAR1"] = "val1"
        os.environ["VAR2"] = "val2"
        data = ["${VAR1}", "${VAR2}"]
        result = _expand_env_vars(data)
        assert result == ["val1", "val2"]

    def test_no_expand_without_pattern(self):
        result = _expand_env_vars("plain_text")
        assert result == "plain_text"

    def test_fail_fast_missing_env_var(self):
        with pytest.raises(ValueError) as exc:
            _expand_env_vars("${MISSING_VAR}")
        assert "MISSING_VAR" in str(exc.value)
        assert "not found" in str(exc.value)

    def test_mixed_content(self):
        os.environ["VAR"] = "replaced"
        result = _expand_env_vars("prefix-${VAR}-suffix")
        assert result == "prefix-replaced-suffix"

    def test_expand_full_config(self):
        os.environ["SLACK_URL"] = "https://slack.webhook"
        os.environ["REDIS_URL"] = "redis://localhost:6379"

        data = {
            "settings": {"redis_url": "${REDIS_URL}"},
            "destinations": [{"webhook_url": "${SLACK_URL}"}],
        }
        result = _expand_env_vars(data)

        assert result["settings"]["redis_url"] == "redis://localhost:6379"
        assert result["destinations"][0]["webhook_url"] == "https://slack.webhook"
