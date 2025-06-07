import argparse
import asyncio
import sys

from flags import (delete_flag, disable_flag, enable_flag, get_flag_details,
                   is_enabled, list_flags)


async def enable_command(flag_name: str, description: str = ""):
    if await enable_flag(flag_name, description):
        print(f"✓ Enabled flag: {flag_name}")
        if description:
            print(f"  Description: {description}")
    else:
        print(f"✗ Failed to enable flag: {flag_name}")


async def disable_command(flag_name: str, description: str = ""):
    if await disable_flag(flag_name, description):
        print(f"✓ Disabled flag: {flag_name}")
        if description:
            print(f"  Description: {description}")
    else:
        print(f"✗ Failed to disable flag: {flag_name}")


async def list_command():
    flags = await list_flags()
    if not flags:
        print("No feature flags found.")
        return
    print("Feature Flags:")
    print("-" * 50)
    for flag_name, enabled in flags.items():
        details = await get_flag_details(flag_name)
        description = (
            details.get("description", "No description")
            if details
            else "No description"
        )
        updated_at = details.get("updated_at", "Unknown") if details else "Unknown"

        status_icon = "✓" if enabled else "✗"
        status_text = "ENABLED" if enabled else "DISABLED"

        print(f"{status_icon} {flag_name}: {status_text}")
        print(f"  Description: {description}")
        print(f"  Updated: {updated_at}")
        print()


async def status_commadn(flag_name: str):
    details = await get_flag_details(flag_name)
    if not details:
        print(f"✗ Flag '{flag_name}' not found.")
        return
    enabled = await is_enabled(flag_name)
    status_icon = "✓" if enabled else "✗"
    status_text = "ENABLED" if enabled else "DISABLED"
    print(f"Flag: {flag_name}")
    print(f"Status: {status_icon} {status_text}")
    print(f"Description: {details.get('description', 'No description')}")
    print(f"Updated: {details.get('updated_at', 'Unknown')}")


async def delete_command(flag_name: str):
    """Delete a feature flag"""
    if not await get_flag_details(flag_name):
        print(f"✗ Flag '{flag_name}' not found.")
        return

    confirm = input(f"Are you sure you want to delete flag '{flag_name}'? (y/N): ")
    if confirm.lower() in ["y", "yes"]:
        if await delete_flag(flag_name):
            print(f"✓ Deleted flag: {flag_name}")
        else:
            print(f"✗ Failed to delete flag: {flag_name}")
    else:
        print("Cancelled.")


async def toggle_command(flag_name: str, description: str = ""):
    """Toggle a feature flag"""
    current_status = await is_enabled(flag_name)

    if current_status:
        await disable_command(flag_name, description)
    else:
        await enable_command(flag_name, description)
