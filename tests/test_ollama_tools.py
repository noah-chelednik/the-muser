"""Verify Ollama tool calling works with our model."""

from ollama import chat

# Define a simple test tool
tools = [
    {
        "type": "function",
        "function": {
            "name": "get_composition_status",
            "description": "Get the current status of a composition project",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_name": {
                        "type": "string",
                        "description": "Name of the composition project",
                    }
                },
                "required": ["project_name"],
            },
        },
    }
]

messages = [
    {
        "role": "system",
        "content": "You are The Muser, a music composition assistant. Use tools when appropriate.",
    },
    {"role": "user", "content": "What's the status of my nocturne project?"},
]

response = chat(
    model="qwen3:30b-a3b",
    messages=messages,
    tools=tools,
    options={
        "num_gpu": 0,
        "num_thread": 16,
        "num_ctx": 8192,
        "temperature": 0.7,
        "top_p": 0.8,
    },
)

print("Response:", response.message.content)
print("Tool calls:", response.message.tool_calls)

# Verify at least one tool call was made
assert response.message.tool_calls is not None and len(response.message.tool_calls) > 0, (
    "Model failed to make a tool call"
)
tc = response.message.tool_calls[0]
assert tc.function.name == "get_composition_status", (
    f"Expected get_composition_status, got {tc.function.name}"
)
print("Tool calling works correctly")
