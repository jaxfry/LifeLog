from __future__ import annotations
import argparse
import asyncio
import json
from typing import Any

from .config import AgentConfig
from .runner import run_agent
from .http import DeviceClient


def main():
    ap = argparse.ArgumentParser(prog="lifelog-agent", description="LifeLog Device Agent")
    sub = ap.add_subparsers(dest="cmd", required=True)

    ap_init = sub.add_parser("init", help="Initialize local agent config")
    ap_init.add_argument("--server", required=True)
    ap_init.add_argument("--device-key", required=True)
    ap_init.add_argument("--platform", default="macos")

    ap_run = sub.add_parser("run", help="Run the agent loop")

    ap_cfg = sub.add_parser("config", help="Manage collector config")
    ap_cfg_sub = ap_cfg.add_subparsers(dest="cfg_cmd", required=True)
    ap_cfg_show = ap_cfg_sub.add_parser("show", help="Display current configuration")
    ap_cfg_set = ap_cfg_sub.add_parser("set", help="Set collector key/value")
    ap_cfg_set.add_argument("extension_slug")
    ap_cfg_set.add_argument("collector_slug")
    ap_cfg_set.add_argument("key")
    ap_cfg_set.add_argument("value")
    ap_cfg_reset = ap_cfg_sub.add_parser("reset", help="Reset configuration to defaults")
    ap_cfg_reset.add_argument("--confirm", action="store_true", help="Skip confirmation prompt")

    args = ap.parse_args()

    if args.cmd == "init":
        cfg = AgentConfig(server_url=args.server, device_key=args.device_key, platform=args.platform)
        cfg.save()
        print("Initialized config at ~/.lifelog/agent/config.json")
        return

    if args.cmd == "config":
        cfg = AgentConfig.load()
        if args.cfg_cmd == "show":
            print("Current Configuration:")
            print("=" * 50)
            print(f"Server URL:    {cfg.server_url}")
            print(f"Platform:      {cfg.platform}")
            print(f"Device Key:    {cfg.device_key[:8]}...{cfg.device_key[-4:]}")
            print(f"Poll Interval: {cfg.poll_interval_sec}s")
            print(f"Max Queue:     {cfg.max_queue_mb}MB")
            print("")
            if cfg.collectors:
                print("Collector Configurations:")
                print("-" * 50)
                for ext_slug, ext_config in cfg.collectors.items():
                    print(f"\n[{ext_slug}]")
                    for col_slug, col_config in ext_config.items():
                        print(f"  {col_slug}:")
                        for key, value in col_config.items():
                            print(f"    {key}: {value}")
            else:
                print("No collector configurations set.")
            return
        if args.cfg_cmd == "set":
            ext = cfg.collectors.get(args.extension_slug, {})
            col = ext.get(args.collector_slug, {})
            col[args.key] = args.value
            ext[args.collector_slug] = col
            cfg.collectors[args.extension_slug] = ext
            cfg.save()
            print("Updated local config.")
            return
        if args.cfg_cmd == "reset":
            if not args.confirm:
                response = input("⚠️  This will reset all configuration to defaults. Continue? [y/N] ")
                if response.lower() not in ["y", "yes"]:
                    print("Reset cancelled.")
                    return
            server_url = cfg.server_url
            device_key = cfg.device_key
            platform = cfg.platform
            new_cfg = AgentConfig(
                server_url=server_url,
                device_key=device_key,
                platform=platform
            )
            new_cfg.save()
            print("✅ Configuration reset to defaults.")
            print("   Collector configurations have been cleared.")
            print("   Run 'python -m lifelog_agent run' to sync from server.")
        return

    if args.cmd == "run":
        cfg = AgentConfig.load()
        asyncio.run(run_agent(cfg))


if __name__ == "__main__":
    main()
