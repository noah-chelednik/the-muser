"""Run the Studio API:  python -m studio.server [--host 127.0.0.1] [--port 8765] [--demo]"""

from __future__ import annotations

import argparse
import os


def main() -> None:
    parser = argparse.ArgumentParser(description="The Muser Studio API + web UI")
    parser.add_argument("--host", default=os.environ.get("MUSER_STUDIO_HOST", "127.0.0.1"))
    parser.add_argument(
        "--port", type=int, default=int(os.environ.get("MUSER_STUDIO_PORT", "8765"))
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Force demo mode (synthesized audio, no models/LLM required)",
    )
    parser.add_argument("--reload", action="store_true", help="Dev auto-reload")
    args = parser.parse_args()

    if args.demo:
        os.environ["MUSER_STUDIO_DEMO"] = "1"

    import uvicorn

    print(f"\n  NoDAW Labs // THE MUSER STUDIO  ->  http://{args.host}:{args.port}\n")
    uvicorn.run(
        "studio.server.app:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info",
    )


if __name__ == "__main__":
    main()
