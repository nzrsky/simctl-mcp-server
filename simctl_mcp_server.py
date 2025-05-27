#!/usr/bin/env python3
"""
SimCtl MCP Server

A Model Context Protocol server that provides structured access to iOS Simulator 
management via xcrun simctl commands.
"""

import asyncio
import json
import subprocess
import sys
import re
from typing import Any, Dict, List, Optional, Union
from dataclasses import dataclass

import mcp.server.stdio
import mcp.types as types
from mcp.server import NotificationOptions, Server


@dataclass
class SimulatorDevice:
    """Represents a simulator device"""
    name: str
    udid: str
    state: str
    runtime: str
    device_type: str


class SimCtlMCPServer:
    """MCP Server for iOS Simulator management via simctl"""
    
    def __init__(self):
        self.server = Server("simctl-mcp")
        self._setup_handlers()
    
    def _setup_handlers(self):
        """Setup MCP server handlers"""
        
        @self.server.list_tools()
        async def handle_list_tools() -> list[types.Tool]:
            """List available simctl tools"""
            return [
                types.Tool(
                    name="simctl_list_devices",
                    description="List available iOS simulators and their states",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "format": {
                                "type": "string",
                                "enum": ["json", "text"],
                                "default": "json",
                                "description": "Output format"
                            },
                            "filter": {
                                "type": "string",
                                "description": "Optional filter term (e.g., 'available', 'iPhone', 'iOS 17')"
                            }
                        }
                    }
                ),
                
                types.Tool(
                    name="simctl_boot_device",
                    description="Boot a simulator device",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "device": {
                                "type": "string",
                                "description": "Device UDID, name, or 'booted' for current device"
                            },
                            "arch": {
                                "type": "string",
                                "enum": ["arm64", "x86_64"],
                                "description": "Architecture to use when booting"
                            }
                        },
                        "required": ["device"]
                    }
                ),
                
                types.Tool(
                    name="simctl_shutdown_device",
                    description="Shutdown a simulator device",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "device": {
                                "type": "string",
                                "description": "Device UDID, name, or 'all' to shutdown all devices"
                            }
                        },
                        "required": ["device"]
                    }
                ),
                
                types.Tool(
                    name="simctl_create_device",
                    description="Create a new simulator device",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "name": {
                                "type": "string",
                                "description": "Name for the new device"
                            },
                            "device_type": {
                                "type": "string",
                                "description": "Device type ID (e.g., 'iPhone 15', 'com.apple.CoreSimulator.SimDeviceType.iPhone-15')"
                            },
                            "runtime": {
                                "type": "string",
                                "description": "Runtime ID (optional, defaults to newest compatible)"
                            }
                        },
                        "required": ["name", "device_type"]
                    }
                ),
                
                types.Tool(
                    name="simctl_delete_device",
                    description="Delete simulator devices",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "devices": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "List of device UDIDs/names, or ['unavailable'] or ['all']"
                            }
                        },
                        "required": ["devices"]
                    }
                ),
                
                types.Tool(
                    name="simctl_install_app",
                    description="Install an app on a simulator device",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "device": {
                                "type": "string",
                                "description": "Device UDID, name, or 'booted'"
                            },
                            "app_path": {
                                "type": "string",
                                "description": "Path to the .app bundle or .ipa file"
                            }
                        },
                        "required": ["device", "app_path"]
                    }
                ),
                
                types.Tool(
                    name="simctl_launch_app",
                    description="Launch an app on a simulator device",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "device": {
                                "type": "string",
                                "description": "Device UDID, name, or 'booted'"
                            },
                            "bundle_id": {
                                "type": "string",
                                "description": "App bundle identifier"
                            },
                            "wait_for_debugger": {
                                "type": "boolean",
                                "default": False,
                                "description": "Wait for debugger to attach"
                            },
                            "console_mode": {
                                "type": "string",
                                "enum": ["none", "console", "console-pty"],
                                "default": "none",
                                "description": "Console output mode"
                            },
                            "args": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Command line arguments to pass to the app"
                            }
                        },
                        "required": ["device", "bundle_id"]
                    }
                ),
                
                types.Tool(
                    name="simctl_terminate_app",
                    description="Terminate an app on a simulator device",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "device": {
                                "type": "string",
                                "description": "Device UDID, name, or 'booted'"
                            },
                            "bundle_id": {
                                "type": "string",
                                "description": "App bundle identifier"
                            }
                        },
                        "required": ["device", "bundle_id"]
                    }
                ),
                
                types.Tool(
                    name="simctl_screenshot",
                    description="Take a screenshot of a simulator device",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "device": {
                                "type": "string",
                                "description": "Device UDID, name, or 'booted'"
                            },
                            "output_path": {
                                "type": "string",
                                "description": "Output file path (use '-' for stdout)"
                            },
                            "format": {
                                "type": "string",
                                "enum": ["png", "tiff", "bmp", "gif", "jpeg"],
                                "default": "png",
                                "description": "Image format"
                            },
                            "display": {
                                "type": "string",
                                "enum": ["internal", "external"],
                                "default": "internal",
                                "description": "Display to capture"
                            }
                        },
                        "required": ["device", "output_path"]
                    }
                ),
                
                types.Tool(
                    name="simctl_record_video",
                    description="Record video of a simulator device",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "device": {
                                "type": "string",
                                "description": "Device UDID, name, or 'booted'"
                            },
                            "output_path": {
                                "type": "string",
                                "description": "Output file path"
                            },
                            "codec": {
                                "type": "string",
                                "enum": ["h264", "hevc"],
                                "default": "hevc",
                                "description": "Video codec"
                            },
                            "display": {
                                "type": "string",
                                "enum": ["internal", "external"],
                                "default": "internal",
                                "description": "Display to record"
                            }
                        },
                        "required": ["device", "output_path"]
                    }
                ),
                
                types.Tool(
                    name="simctl_push_notification",
                    description="Send a push notification to an app",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "device": {
                                "type": "string",
                                "description": "Device UDID, name, or 'booted'"
                            },
                            "bundle_id": {
                                "type": "string",
                                "description": "App bundle identifier (optional if payload contains target)"
                            },
                            "payload": {
                                "type": "object",
                                "description": "Push notification payload (must contain 'aps' key)"
                            }
                        },
                        "required": ["device", "payload"]
                    }
                ),
                
                types.Tool(
                    name="simctl_privacy_control",
                    description="Grant, revoke, or reset app privacy permissions",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "device": {
                                "type": "string",
                                "description": "Device UDID, name, or 'booted'"
                            },
                            "action": {
                                "type": "string",
                                "enum": ["grant", "revoke", "reset"],
                                "description": "Action to take"
                            },
                            "service": {
                                "type": "string",
                                "enum": [
                                    "all", "calendar", "contacts-limited", "contacts",
                                    "location", "location-always", "photos-add", "photos",
                                    "media-library", "microphone", "motion", "reminders", "siri"
                                ],
                                "description": "Privacy service"
                            },
                            "bundle_id": {
                                "type": "string",
                                "description": "App bundle identifier (required for grant/revoke)"
                            }
                        },
                        "required": ["device", "action", "service"]
                    }
                ),
                
                types.Tool(
                    name="simctl_set_location",
                    description="Set device location or run location scenario",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "device": {
                                "type": "string",
                                "description": "Device UDID, name, or 'booted'"
                            },
                            "action": {
                                "type": "string",
                                "enum": ["set", "clear", "list", "run"],
                                "description": "Location action"
                            },
                            "latitude": {
                                "type": "number",
                                "description": "Latitude (for 'set' action)"
                            },
                            "longitude": {
                                "type": "number",
                                "description": "Longitude (for 'set' action)"
                            },
                            "scenario": {
                                "type": "string",
                                "description": "Scenario name (for 'run' action)"
                            }
                        },
                        "required": ["device", "action"]
                    }
                ),
                
                types.Tool(
                    name="simctl_status_bar_override",
                    description="Override status bar appearance",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "device": {
                                "type": "string",
                                "description": "Device UDID, name, or 'booted'"
                            },
                            "action": {
                                "type": "string",
                                "enum": ["list", "clear", "override"],
                                "description": "Status bar action"
                            },
                            "time": {
                                "type": "string",
                                "description": "Override time display"
                            },
                            "data_network": {
                                "type": "string",
                                "enum": ["hide", "wifi", "3g", "4g", "lte", "lte-a", "lte+", "5g", "5g+", "5g-uwb", "5g-uc"],
                                "description": "Data network type"
                            },
                            "wifi_bars": {
                                "type": "integer",
                                "minimum": 0,
                                "maximum": 3,
                                "description": "WiFi signal strength (0-3)"
                            },
                            "cellular_bars": {
                                "type": "integer",
                                "minimum": 0,
                                "maximum": 4,
                                "description": "Cellular signal strength (0-4)"
                            },
                            "battery_level": {
                                "type": "integer",
                                "minimum": 0,
                                "maximum": 100,
                                "description": "Battery level percentage"
                            },
                            "battery_state": {
                                "type": "string",
                                "enum": ["charging", "charged", "discharging"],
                                "description": "Battery state"
                            }
                        },
                        "required": ["device", "action"]
                    }
                ),
                
                types.Tool(
                    name="simctl_ui_appearance",
                    description="Get or set UI appearance (light/dark mode)",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "device": {
                                "type": "string",
                                "description": "Device UDID, name, or 'booted'"
                            },
                            "appearance": {
                                "type": "string",
                                "enum": ["light", "dark"],
                                "description": "Appearance to set (omit to get current)"
                            }
                        },
                        "required": ["device"]
                    }
                )
            ]
        
        @self.server.call_tool()
        async def handle_call_tool(name: str, arguments: dict) -> list[types.TextContent]:
            """Handle tool calls"""
            try:
                if name == "simctl_list_devices":
                    result = await self._list_devices(arguments)
                elif name == "simctl_boot_device":
                    result = await self._boot_device(arguments)
                elif name == "simctl_shutdown_device":
                    result = await self._shutdown_device(arguments)
                elif name == "simctl_create_device":
                    result = await self._create_device(arguments)
                elif name == "simctl_delete_device":
                    result = await self._delete_device(arguments)
                elif name == "simctl_install_app":
                    result = await self._install_app(arguments)
                elif name == "simctl_launch_app":
                    result = await self._launch_app(arguments)
                elif name == "simctl_terminate_app":
                    result = await self._terminate_app(arguments)
                elif name == "simctl_screenshot":
                    result = await self._screenshot(arguments)
                elif name == "simctl_record_video":
                    result = await self._record_video(arguments)
                elif name == "simctl_push_notification":
                    result = await self._push_notification(arguments)
                elif name == "simctl_privacy_control":
                    result = await self._privacy_control(arguments)
                elif name == "simctl_set_location":
                    result = await self._set_location(arguments)
                elif name == "simctl_status_bar_override":
                    result = await self._status_bar_override(arguments)
                elif name == "simctl_ui_appearance":
                    result = await self._ui_appearance(arguments)
                else:
                    raise ValueError(f"Unknown tool: {name}")
                
                return [types.TextContent(type="text", text=result)]
            
            except Exception as e:
                return [types.TextContent(type="text", text=f"Error: {str(e)}")]
    
    async def _run_simctl_command(self, args: List[str]) -> str:
        """Run a simctl command and return the output"""
        cmd = ["xcrun", "simctl"] + args
        
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                error_msg = stderr.decode().strip() if stderr else "Command failed"
                raise RuntimeError(f"simctl command failed: {error_msg}")
            
            return stdout.decode().strip()
        
        except FileNotFoundError:
            raise RuntimeError("xcrun simctl not found. Make sure Xcode is installed.")
    
    async def _list_devices(self, args: dict) -> str:
        """List available devices"""
        cmd_args = ["list"]
        
        if args.get("format") == "json":
            cmd_args.extend(["-j"])
        
        cmd_args.append("devices")
        
        if args.get("filter"):
            cmd_args.append(args["filter"])
        
        result = await self._run_simctl_command(cmd_args)
        
        if args.get("format") == "json":
            # Parse and format JSON for better readability
            try:
                data = json.loads(result)
                return json.dumps(data, indent=2)
            except json.JSONDecodeError:
                return result
        
        return result
    
    async def _boot_device(self, args: dict) -> str:
        """Boot a device"""
        cmd_args = ["boot", args["device"]]
        
        if args.get("arch"):
            cmd_args.append(f"--arch={args['arch']}")
        
        await self._run_simctl_command(cmd_args)
        return f"Successfully booted device: {args['device']}"
    
    async def _shutdown_device(self, args: dict) -> str:
        """Shutdown a device"""
        cmd_args = ["shutdown", args["device"]]
        await self._run_simctl_command(cmd_args)
        return f"Successfully shutdown device: {args['device']}"
    
    async def _create_device(self, args: dict) -> str:
        """Create a new device"""
        cmd_args = ["create", args["name"], args["device_type"]]
        
        if args.get("runtime"):
            cmd_args.append(args["runtime"])
        
        result = await self._run_simctl_command(cmd_args)
        return f"Created device '{args['name']}': {result}"
    
    async def _delete_device(self, args: dict) -> str:
        """Delete devices"""
        cmd_args = ["delete"] + args["devices"]
        await self._run_simctl_command(cmd_args)
        return f"Successfully deleted devices: {', '.join(args['devices'])}"
    
    async def _install_app(self, args: dict) -> str:
        """Install an app"""
        cmd_args = ["install", args["device"], args["app_path"]]
        await self._run_simctl_command(cmd_args)
        return f"Successfully installed app from {args['app_path']} to {args['device']}"
    
    async def _launch_app(self, args: dict) -> str:
        """Launch an app"""
        cmd_args = ["launch"]
        
        if args.get("wait_for_debugger"):
            cmd_args.append("--wait-for-debugger")
        
        console_mode = args.get("console_mode", "none")
        if console_mode == "console":
            cmd_args.append("--console")
        elif console_mode == "console-pty":
            cmd_args.append("--console-pty")
        
        cmd_args.extend([args["device"], args["bundle_id"]])
        
        if args.get("args"):
            cmd_args.extend(args["args"])
        
        result = await self._run_simctl_command(cmd_args)
        return f"Launched {args['bundle_id']} on {args['device']}: {result}"
    
    async def _terminate_app(self, args: dict) -> str:
        """Terminate an app"""
        cmd_args = ["terminate", args["device"], args["bundle_id"]]
        await self._run_simctl_command(cmd_args)
        return f"Terminated {args['bundle_id']} on {args['device']}"
    
    async def _screenshot(self, args: dict) -> str:
        """Take a screenshot"""
        cmd_args = ["io", args["device"], "screenshot"]
        
        if args.get("format", "png") != "png":
            cmd_args.append(f"--type={args['format']}")
        
        if args.get("display", "internal") != "internal":
            cmd_args.append(f"--display={args['display']}")
        
        cmd_args.append(args["output_path"])
        
        await self._run_simctl_command(cmd_args)
        return f"Screenshot saved to {args['output_path']}"
    
    async def _record_video(self, args: dict) -> str:
        """Record video (note: this starts recording, user needs to stop with Ctrl+C)"""
        cmd_args = ["io", args["device"], "recordVideo"]
        
        if args.get("codec", "hevc") != "hevc":
            cmd_args.append(f"--codec={args['codec']}")
        
        if args.get("display", "internal") != "internal":
            cmd_args.append(f"--display={args['display']}")
        
        cmd_args.append(args["output_path"])
        
        # Note: This will start recording but won't wait for completion
        # The user needs to send SIGINT to stop recording
        await self._run_simctl_command(cmd_args)
        return f"Started video recording to {args['output_path']}. Send SIGINT (Ctrl+C) to stop."
    
    async def _push_notification(self, args: dict) -> str:
        """Send push notification"""
        import tempfile
        import os
        
        # Create temporary file for payload
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(args["payload"], f)
            payload_file = f.name
        
        try:
            cmd_args = ["push", args["device"]]
            
            if args.get("bundle_id"):
                cmd_args.append(args["bundle_id"])
            
            cmd_args.append(payload_file)
            
            await self._run_simctl_command(cmd_args)
            return f"Push notification sent to {args.get('bundle_id', 'app specified in payload')}"
        
        finally:
            os.unlink(payload_file)
    
    async def _privacy_control(self, args: dict) -> str:
        """Control app privacy permissions"""
        cmd_args = ["privacy", args["device"], args["action"], args["service"]]
        
        if args.get("bundle_id"):
            cmd_args.append(args["bundle_id"])
        
        await self._run_simctl_command(cmd_args)
        
        action_desc = f"{args['action']}ed" if args["action"] != "reset" else "reset"
        return f"Privacy permission {action_desc} for {args['service']} service"
    
    async def _set_location(self, args: dict) -> str:
        """Set device location"""
        cmd_args = ["location", args["device"], args["action"]]
        
        if args["action"] == "set":
            if not args.get("latitude") or not args.get("longitude"):
                raise ValueError("Latitude and longitude required for 'set' action")
            cmd_args.append(f"{args['latitude']},{args['longitude']}")
        elif args["action"] == "run":
            if not args.get("scenario"):
                raise ValueError("Scenario required for 'run' action")
            cmd_args.append(args["scenario"])
        
        result = await self._run_simctl_command(cmd_args)
        return result if result else f"Location {args['action']} completed"
    
    async def _status_bar_override(self, args: dict) -> str:
        """Override status bar appearance"""
        cmd_args = ["status_bar", args["device"], args["action"]]
        
        if args["action"] == "override":
            if args.get("time"):
                cmd_args.extend(["--time", args["time"]])
            if args.get("data_network"):
                cmd_args.extend(["--dataNetwork", args["data_network"]])
            if args.get("wifi_bars") is not None:
                cmd_args.extend(["--wifiBars", str(args["wifi_bars"])])
            if args.get("cellular_bars") is not None:
                cmd_args.extend(["--cellularBars", str(args["cellular_bars"])])
            if args.get("battery_level") is not None:
                cmd_args.extend(["--batteryLevel", str(args["battery_level"])])
            if args.get("battery_state"):
                cmd_args.extend(["--batteryState", args["battery_state"]])
        
        result = await self._run_simctl_command(cmd_args)
        return result if result else f"Status bar {args['action']} completed"
    
    async def _ui_appearance(self, args: dict) -> str:
        """Get or set UI appearance"""
        cmd_args = ["ui", args["device"], "appearance"]
        
        if args.get("appearance"):
            cmd_args.append(args["appearance"])
        
        result = await self._run_simctl_command(cmd_args)
        return result
    
    async def run(self):
        """Run the MCP server"""
        async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
            await self.server.run(
                read_stream,
                write_stream,
                NotificationOptions(
                    prompts_changed=True,
                    resources_changed=True,
                    tools_changed=True,
                ),
            )


async def main():
    """Main entry point"""
    server = SimCtlMCPServer()
    await server.run()


def cli():
    """CLI entry point for package installation"""
    asyncio.run(main())


if __name__ == "__main__":
    asyncio.run(main())