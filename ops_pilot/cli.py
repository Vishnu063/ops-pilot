import argparse
import json
from pathlib import Path
from .config import DEFAULT_CONFIG, DEFAULT_STATE, load, save


def main():
    parser = argparse.ArgumentParser(description="Ops Pilot: one Docker app, reviewed repairs, verified health")
    parser.add_argument("command", choices=("setup", "serve", "check", "freelance"), nargs="?", default="serve")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--state-dir", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--port", type=int, default=8767)
    parser.add_argument("--ai-model", help="Optional installed local Ollama model. Advisory only; no auto download.")
    parser.add_argument("--ecosystem-service",help="Opt in to the event inbox for this exact service ID; source/read tokens come from private environment variables")
    args = parser.parse_args()
    try:
        if args.command == "setup":
            if args.config.expanduser().exists():
                if input("Replace this application's configuration? Type replace: ").strip() != "replace":
                    return 1
            print("Connect one application you own. No repair runs during setup.")
            value = {"name": input("Application name: ").strip(),
                "docker_context": input("Docker context [default]: ").strip() or "default",
                "container": input("Exact container name or ID: ").strip(),
                "health_url": input("Health URL (HTTPS, or local HTTP): ").strip(), "interval_seconds": 30}
            save(args.config, value)
            print("Saved privately. Start with: bash start.sh")
            return 0
        if not 1024 <= args.port <= 65535:
            raise ValueError("Choose a port between 1024 and 65535")
        from .freelance import Workspace
        from .web import run
        if args.command == 'freelance':
            run(None, args.port, Workspace(args.state_dir))
            return 0
        from .service import Pilot
        config, _ = load(args.config)
        pilot = Pilot(config, args.state_dir, ai_model=args.ai_model)
        if args.command == "check":
            pilot.action("investigate")
            report = pilot.report
            print(json.dumps(report, indent=2))
            return 2 if report["snapshot"].get("errors") else 1 if report["findings"] else 0
        hub=None
        if args.ecosystem_service:
            from .ecosystem import EventHub
            hub=EventHub(pilot,args.state_dir,args.ecosystem_service)
        run(pilot, args.port, Workspace(args.state_dir), hub)
        return 0
    except (ValueError, RuntimeError, OSError, EOFError) as exc:
        print("Ops Pilot could not continue:", str(exc))
        print("Run bash start.sh setup; check Docker access and the configured health endpoint.")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

