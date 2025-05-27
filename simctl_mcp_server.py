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
import os
import tempfile
import re
from typing import Any, Dict, List, Optional, Union
from dataclasses import dataclass

from mcp.server.fastmcp import FastMCP


@dataclass
class SimulatorDevice:
    """Represents a simulator device"""
    name: str
    udid: str
    state: str
    runtime: str
    device_type: str


# Initialize the MCP server
mcp = FastMCP("SimCtl MCP Server")


class SimCtlMCPError(Exception):
    """Base exception for SimCtl MCP operations"""
    def __init__(self, message: str, code: Optional[str] = None):
        self.message = message
        self.code = code
        super().__init__(self.message)


async def run_simctl_command(args: List[str]) -> str:
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
            raise SimCtlMCPError(f"simctl command failed: {error_msg}")
        
        return stdout.decode().strip()
    
    except FileNotFoundError:
        raise SimCtlMCPError("xcrun simctl not found. Make sure Xcode is installed.")


# MCP Tools for iOS Simulator management

@mcp.tool()
async def simctl_list_devices(format: str = "json", filter: Optional[str] = None) -> str:
    """
    List available iOS simulators and their states.
    
    Args:
        format: Output format (json or text). Defaults to json.
        filter: Optional filter term (e.g., 'available', 'iPhone', 'iOS 17')
        
    Returns:
        List of available simulators
    """
    cmd_args = ["list"]
    
    if format == "json":
        cmd_args.extend(["-j"])
    
    cmd_args.append("devices")
    
    if filter:
        cmd_args.append(filter)
    
    result = await run_simctl_command(cmd_args)
    
    if format == "json":
        # Parse and format JSON for better readability
        try:
            data = json.loads(result)
            return json.dumps(data, indent=2)
        except json.JSONDecodeError:
            return result
    
    return result


@mcp.tool()
async def simctl_boot_device(device: str, arch: Optional[str] = None) -> str:
    """
    Boot a simulator device.
    
    Args:
        device: Device UDID, name, or 'booted' for current device
        arch: Architecture to use when booting (arm64 or x86_64)
        
    Returns:
        Success message
    """
    cmd_args = ["boot", device]
    
    if arch:
        cmd_args.append(f"--arch={arch}")
    
    await run_simctl_command(cmd_args)
    return f"Successfully booted device: {device}"


@mcp.tool()
async def simctl_shutdown_device(device: str) -> str:
    """
    Shutdown a simulator device.
    
    Args:
        device: Device UDID, name, or 'booted' for current device
        
    Returns:
        Success message
    """
    cmd_args = ["shutdown", device]
    await run_simctl_command(cmd_args)
    return f"Successfully shutdown device: {device}"


@mcp.tool()
async def simctl_create_device(name: str, device_type: str, runtime: Optional[str] = None) -> str:
    """
    Create a new simulator device.
    
    Args:
        name: Name for the new device
        device_type: Device type identifier (e.g., 'iPhone 15 Pro')
        runtime: Runtime identifier (e.g., 'iOS 17.0')
        
    Returns:
        Created device information
    """
    cmd_args = ["create", name, device_type]
    
    if runtime:
        cmd_args.append(runtime)
    
    result = await run_simctl_command(cmd_args)
    return f"Created device '{name}': {result}"


@mcp.tool()
async def simctl_delete_device(devices: List[str]) -> str:
    """
    Delete simulator devices.
    
    Args:
        devices: List of device UDIDs, names, or 'unavailable' to delete all unavailable devices
        
    Returns:
        Success message
    """
    cmd_args = ["delete"] + devices
    await run_simctl_command(cmd_args)
    return f"Successfully deleted devices: {', '.join(devices)}"


@mcp.tool()
async def simctl_install_app(device: str, app_path: str) -> str:
    """
    Install an app on a simulator device.
    
    Args:
        device: Device UDID, name, or 'booted' for current device
        app_path: Path to .app bundle or .ipa file
        
    Returns:
        Success message
    """
    cmd_args = ["install", device, app_path]
    await run_simctl_command(cmd_args)
    return f"Successfully installed app from {app_path} to {device}"


@mcp.tool()
async def simctl_launch_app(device: str, bundle_id: str, wait_for_debugger: bool = False, 
                           console_mode: str = "none", args: Optional[List[str]] = None) -> str:
    """
    Launch an app on a simulator device.
    
    Args:
        device: Device UDID, name, or 'booted' for current device
        bundle_id: App bundle identifier
        wait_for_debugger: Wait for debugger to attach before launching
        console_mode: Console output mode (none, console, console-pty)
        args: Additional launch arguments
        
    Returns:
        Launch result
    """
    cmd_args = ["launch"]
    
    if wait_for_debugger:
        cmd_args.append("--wait-for-debugger")
    
    if console_mode == "console":
        cmd_args.append("--console")
    elif console_mode == "console-pty":
        cmd_args.append("--console-pty")
    
    cmd_args.extend([device, bundle_id])
    
    if args:
        cmd_args.extend(args)
    
    result = await run_simctl_command(cmd_args)
    return f"Launched {bundle_id} on {device}: {result}"


@mcp.tool()
async def simctl_terminate_app(device: str, bundle_id: str) -> str:
    """
    Terminate an app on a simulator device.
    
    Args:
        device: Device UDID, name, or 'booted' for current device
        bundle_id: App bundle identifier
        
    Returns:
        Success message
    """
    cmd_args = ["terminate", device, bundle_id]
    await run_simctl_command(cmd_args)
    return f"Terminated {bundle_id} on {device}"


@mcp.tool()
async def simctl_screenshot(device: str, output_path: str, format: str = "png", 
                           display: str = "internal") -> str:
    """
    Take a screenshot of a simulator device.
    
    Args:
        device: Device UDID, name, or 'booted' for current device
        output_path: Path where to save the screenshot
        format: Image format (png, jpeg)
        display: Display to capture (internal, external)
        
    Returns:
        Success message
    """
    cmd_args = ["io", device, "screenshot"]
    
    if format != "png":
        cmd_args.append(f"--type={format}")
    
    if display != "internal":
        cmd_args.append(f"--display={display}")
    
    cmd_args.append(output_path)
    
    await run_simctl_command(cmd_args)
    return f"Screenshot saved to {output_path}"


@mcp.tool()
async def simctl_record_video(device: str, output_path: str, codec: str = "hevc", 
                             display: str = "internal") -> str:
    """
    Start recording video of a simulator device.
    
    Args:
        device: Device UDID, name, or 'booted' for current device
        output_path: Path where to save the video
        codec: Video codec (hevc, h264)
        display: Display to record (internal, external)
        
    Returns:
        Recording start message
    """
    cmd_args = ["io", device, "recordVideo"]
    
    if codec != "hevc":
        cmd_args.append(f"--codec={codec}")
    
    if display != "internal":
        cmd_args.append(f"--display={display}")
    
    cmd_args.append(output_path)
    
    # Note: This will start recording but won't wait for completion
    # The user needs to send SIGINT to stop recording
    await run_simctl_command(cmd_args)
    return f"Started video recording to {output_path}. Send SIGINT (Ctrl+C) to stop."


@mcp.tool()
async def simctl_push_notification(device: str, payload: Dict[str, Any], 
                                  bundle_id: Optional[str] = None) -> str:
    """
    Send a push notification to a simulator device.
    
    Args:
        device: Device UDID, name, or 'booted' for current device
        payload: Push notification payload as JSON object
        bundle_id: Target app bundle identifier (optional if specified in payload)
        
    Returns:
        Success message
    """
    # Create temporary file for payload
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(payload, f)
        payload_file = f.name
    
    try:
        cmd_args = ["push", device]
        
        if bundle_id:
            cmd_args.append(bundle_id)
        
        cmd_args.append(payload_file)
        
        await run_simctl_command(cmd_args)
        return f"Push notification sent to {bundle_id or 'app specified in payload'}"
    
    finally:
        os.unlink(payload_file)


@mcp.tool()
async def simctl_privacy_control(device: str, action: str, service: str, 
                                bundle_id: Optional[str] = None) -> str:
    """
    Control app privacy permissions on a simulator device.
    
    Args:
        device: Device UDID, name, or 'booted' for current device
        action: Privacy action (grant, revoke, reset)
        service: Privacy service (photos, camera, microphone, location, etc.)
        bundle_id: App bundle identifier (optional)
        
    Returns:
        Success message
    """
    cmd_args = ["privacy", device, action, service]
    
    if bundle_id:
        cmd_args.append(bundle_id)
    
    await run_simctl_command(cmd_args)
    
    action_desc = f"{action}ed" if action != "reset" else "reset"
    return f"Privacy permission {action_desc} for {service} service"


@mcp.tool()
async def simctl_set_location(device: str, action: str, latitude: Optional[float] = None, 
                             longitude: Optional[float] = None, scenario: Optional[str] = None) -> str:
    """
    Set or clear device location on a simulator.
    
    Args:
        device: Device UDID, name, or 'booted' for current device
        action: Location action (set, clear, run)
        latitude: Latitude coordinate (required for 'set' action)
        longitude: Longitude coordinate (required for 'set' action)
        scenario: Location scenario (required for 'run' action)
        
    Returns:
        Success message
    """
    cmd_args = ["location", device, action]
    
    if action == "set":
        if latitude is None or longitude is None:
            raise SimCtlMCPError("Latitude and longitude required for 'set' action")
        cmd_args.append(f"{latitude},{longitude}")
    elif action == "run":
        if not scenario:
            raise SimCtlMCPError("Scenario required for 'run' action")
        cmd_args.append(scenario)
    
    result = await run_simctl_command(cmd_args)
    return result if result else f"Location {action} completed"


@mcp.tool()
async def simctl_status_bar_override(device: str, action: str, time: Optional[str] = None,
                                    data_network: Optional[str] = None, wifi_bars: Optional[int] = None,
                                    cellular_bars: Optional[int] = None, battery_level: Optional[int] = None,
                                    battery_state: Optional[str] = None) -> str:
    """
    Override status bar appearance on a simulator device.
    
    Args:
        device: Device UDID, name, or 'booted' for current device
        action: Status bar action (override, clear)
        time: Time to display (e.g., "9:41")
        data_network: Data network type (wifi, 3g, 4g, lte, lte-a, lte+, 5g, 5g+, 5g-uw)
        wifi_bars: WiFi signal strength (0-3)
        cellular_bars: Cellular signal strength (0-4)
        battery_level: Battery level percentage (0-100)
        battery_state: Battery state (charging, charged, discharging)
        
    Returns:
        Success message
    """
    cmd_args = ["status_bar", device, action]
    
    if action == "override":
        if time:
            cmd_args.extend(["--time", time])
        if data_network:
            cmd_args.extend(["--dataNetwork", data_network])
        if wifi_bars is not None:
            cmd_args.extend(["--wifiBars", str(wifi_bars)])
        if cellular_bars is not None:
            cmd_args.extend(["--cellularBars", str(cellular_bars)])
        if battery_level is not None:
            cmd_args.extend(["--batteryLevel", str(battery_level)])
        if battery_state:
            cmd_args.extend(["--batteryState", battery_state])
    
    result = await run_simctl_command(cmd_args)
    return result if result else f"Status bar {action} completed"


@mcp.tool()
async def simctl_ui_appearance(device: str, appearance: Optional[str] = None) -> str:
    """
    Get or set UI appearance (light/dark mode) on a simulator device.
    
    Args:
        device: Device UDID, name, or 'booted' for current device
        appearance: UI appearance (light, dark). If not provided, returns current appearance.
        
    Returns:
        Current or updated appearance
    """
    cmd_args = ["ui", device, "appearance"]
    
    if appearance:
        cmd_args.append(appearance)
    
    result = await run_simctl_command(cmd_args)
    return result


def cli():
    """CLI entry point for package installation"""
    mcp.run()


if __name__ == "__main__":
    mcp.run()
