"""Provider adapter: extend existing openai/anthropic SDK providers with tool-calling.

Verified SDK contract (from tests/test_provider_adapter_smoke.py):
- openai: AsyncOpenAI(api_key=, base_url=).chat.completions.create(
      messages=, model=,
      tools=[{type:"function", function:{name, description, parameters}}],
      tool_choice=
  ) -> response.choices[0].message.tool_calls[i].function.{name, arguments(JSON str)}
- anthropic: AsyncAnthropic(api_key=).messages.create(
      model=, messages=,
      tools=[{name, description, input_schema}],
      tool_choice=
  ) -> response.content blocks of type="tool_use" with .name and .input(dict)
- No pydantic-ai (conflicts with pinned pydantic 2.9.2).

Implemented in Task 9; loop driven in Task 11.
"""
