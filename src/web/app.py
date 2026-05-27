"""Gradio web interface for The Muser.

Provides a browser-based UI wrapping the same agent loop as the CLI,
with chat, audio playback, composition status, and file management.
"""

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def create_app():
    """Create and return the Gradio Blocks application."""
    try:
        import gradio as gr
    except ImportError:
        raise ImportError(
            "Gradio is required for the web UI. "
            "Install with: pip install 'the-muser[web]'"
        )

    from src.orchestrator.agent import run_agent_turn
    from src.orchestrator.composition_state import CompositionState
    from src.orchestrator.config import COMPOSITIONS_DIR

    def handle_message(
        user_msg: str,
        chat_history: list,
        model: str,
        state_json: dict,
        conv_history: list,
    ) -> tuple:
        if not user_msg.strip():
            return chat_history, "", state_json, conv_history, None, None

        state = CompositionState()
        if state_json:
            state.project = state_json.get("project", state.project)
            state.form_plan = state_json.get("form_plan", state.form_plan)
            state.completed_sections = state_json.get("completed_sections", {})

        response = run_agent_turn(
            user_message=user_msg,
            conversation_history=conv_history,
            composition_state=state,
            model=model if model else None,
        )

        chat_history = chat_history + [[user_msg, response]]

        updated_state = {
            "project": state.project,
            "form_plan": state.form_plan,
            "completed_sections": state.completed_sections,
        }

        status_md = state.to_context_string() or "No composition loaded."

        audio_file = _find_latest_audio(state)
        output_files = _list_output_files(state)

        return chat_history, "", updated_state, conv_history, audio_file, status_md

    def _find_latest_audio(state: CompositionState) -> str | None:
        if not state.project_dir:
            return None
        renders = Path(state.project_dir) / "renders"
        if not renders.exists():
            return None
        wavs = sorted(renders.glob("*.wav"), key=lambda p: p.stat().st_mtime, reverse=True)
        return str(wavs[0]) if wavs else None

    def _list_output_files(state: CompositionState) -> list[str]:
        if not state.project_dir:
            return []
        output = Path(state.project_dir) / "output"
        if not output.exists():
            return []
        return [str(f) for f in sorted(output.iterdir()) if f.is_file()]

    with gr.Blocks(
        title="The Muser",
        theme=gr.themes.Soft(),
    ) as app:
        gr.Markdown("# The Muser — AI Music Composition\n*Run locally. Own everything.*")

        state_store = gr.State({})
        conv_store = gr.State([])

        with gr.Row():
            with gr.Column(scale=2):
                chatbot = gr.Chatbot(label="Composition Chat", height=500)
                user_input = gr.Textbox(
                    label="Instructions",
                    placeholder="Compose a jazz piano piece in Bb major...",
                    lines=2,
                )
                with gr.Row():
                    submit_btn = gr.Button("Send", variant="primary")
                    clear_btn = gr.ClearButton(
                        [chatbot, user_input, state_store, conv_store],
                        value="New Session",
                    )

            with gr.Column(scale=1):
                status_display = gr.Markdown("## Status\nNo composition loaded.")
                audio_player = gr.Audio(label="Latest Audio", type="filepath")

                model_dropdown = gr.Dropdown(
                    choices=[
                        "ollama_chat/qwen3:30b-a3b",
                        "groq/llama-3.3-70b-versatile",
                        "cerebras/llama-3.3-70b",
                        "gemini/gemini-2.0-flash",
                    ],
                    value="ollama_chat/qwen3:30b-a3b",
                    label="LLM Provider",
                )

        submit_btn.click(
            fn=handle_message,
            inputs=[user_input, chatbot, model_dropdown, state_store, conv_store],
            outputs=[chatbot, user_input, state_store, conv_store, audio_player, status_display],
        )
        user_input.submit(
            fn=handle_message,
            inputs=[user_input, chatbot, model_dropdown, state_store, conv_store],
            outputs=[chatbot, user_input, state_store, conv_store, audio_player, status_display],
        )

    return app


def main():
    """Launch the web UI."""
    logging.basicConfig(level=logging.INFO)
    app = create_app()
    app.launch(server_name="0.0.0.0", server_port=7860, share=False)


if __name__ == "__main__":
    main()
