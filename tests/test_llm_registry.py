from komora.agent.llm.anthropic_messages import AnthropicMessagesLLM
from komora.agent.llm.openai_chat import OpenAIChatLLM
from komora.agent.llm.registry import build_llm, is_anthropic, openai_base_url
from komora.agent.llm.validation import Validated

MANTLE = "https://bedrock-mantle.us-east-1.api.aws/anthropic"


def test_anthropic_models_are_recognised_by_prefix():
    assert is_anthropic("anthropic.claude-opus-4-8") is True
    assert is_anthropic("anthropic.claude-haiku-4-5") is True


def test_everything_else_is_not_anthropic():
    for model in ("openai.gpt-oss-120b", "mistral.mistral-large-3-675b-instruct", "qwen.qwen3-32b"):
        assert is_anthropic(model) is False


def test_bare_claude_id_also_routes_to_the_messages_adapter():
    assert is_anthropic("claude-opus-4-8") is True
    assert isinstance(
        build_llm(
            model="claude-opus-4-8", base_url="https://api.anthropic.com", api_key="k"
        ).inner,
        AnthropicMessagesLLM,
    )


def test_openai_base_url_drops_the_anthropic_suffix():
    assert openai_base_url(MANTLE) == "https://bedrock-mantle.us-east-1.api.aws"


def test_openai_base_url_tolerates_trailing_slash():
    assert openai_base_url(MANTLE + "/") == "https://bedrock-mantle.us-east-1.api.aws"


def test_openai_base_url_leaves_a_plain_host_alone():
    host = "https://bedrock-mantle.us-east-1.api.aws"
    assert openai_base_url(host) == host


def test_claude_gets_the_messages_adapter():
    llm = build_llm(model="anthropic.claude-opus-4-8", base_url=MANTLE, api_key="k")
    assert isinstance(llm.inner, AnthropicMessagesLLM)


def test_other_models_get_the_openai_adapter():
    llm = build_llm(model="mistral.mistral-large-3-675b-instruct", base_url=MANTLE, api_key="k")
    assert isinstance(llm.inner, OpenAIChatLLM)


def test_every_adapter_comes_wrapped_in_the_schema_check():
    for model in ("anthropic.claude-opus-4-8", "mistral.mistral-large-3-675b-instruct"):
        assert isinstance(build_llm(model=model, base_url=MANTLE, api_key="k"), Validated)


def test_adapters_keep_the_model_id_they_were_built_with():
    for model in ("anthropic.claude-opus-4-8", "openai.gpt-oss-120b"):
        assert build_llm(model=model, base_url=MANTLE, api_key="k").model == model
