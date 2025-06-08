import os
import json
import re
from uuid import uuid4
from typing import Optional, Any

from agent.tools.message_tool import MessageTool
from agent.tools.sb_deploy_tool import SandboxDeployTool
from agent.tools.sb_expose_tool import SandboxExposeTool
from agent.tools.web_search_tool import SandboxWebSearchTool
from dotenv import load_dotenv
from utils.config import config

from agent.agent_builder_prompt import get_agent_builder_prompt
from agentpress.thread_manager import ThreadManager
from agentpress.response_processor import ProcessorConfig
from agent.tools.sb_shell_tool import SandboxShellTool
from agent.tools.sb_files_tool import SandboxFilesTool
from agent.tools.sb_browser_tool import SandboxBrowserTool
from agent.tools.data_providers_tool import DataProvidersTool
from agent.tools.expand_msg_tool import ExpandMessageTool
from agent.prompt import get_system_prompt
from utils.logger import logger
from utils.auth_utils import get_account_id_from_thread
from agent.tools.sb_vision_tool import SandboxVisionTool
from services.langfuse import langfuse
from services.langfuse import langfuse
from agent.gemini_prompt import get_gemini_system_prompt
from agent.tools.mcp_tool_wrapper import MCPToolWrapper
from agentpress.tool import SchemaType


async def run_agent(
    thread_id: str,
    project_id: str,
    stream: bool,
    thread_manager: Optional[ThreadManager] = None,
    native_max_auto_continues: int = 25,
    max_iterations: int = 100,
    model_name: str = "anthropic/claude-3-7-sonnet-latest",
    enable_thinking: Optional[bool] = False,
    reasoning_effort: Optional[str] = 'low',
    enable_context_manager: bool = True,
    agent_config: Optional[dict] = None,
    trace: Optional[Any] = None,
    is_agent_builder: Optional[bool] = False,
    target_agent_id: Optional[str] = None
):
    logger.info(f"🚀 Starting agent with model: {model_name}")
    if agent_config:
        logger.info(
            f"Using custom agent: {agent_config.get('name', 'Unknown')}")
    if not trace:
        trace = langfuse.trace(name="run_agent", session_id=thread_id, metadata={
                               "project_id": project_id})
    thread_manager = ThreadManager(
        trace=trace, is_agent_builder=is_agent_builder, target_agent_id=target_agent_id)

    client = await thread_manager.db.client
    account_id = await get_account_id_from_thread(client, thread_id)
    if not account_id:
        raise ValueError("Could not determine account ID for thread")
    project = await client.table('projects').select('*').eq('project_id', project_id).execute()
    if not project.data or len(project.data) == 0:
        raise ValueError(f"Project {project_id} not found")

    project_data = project.data[0]
    sandbox_info = project_data.get('sandbox', {})
    if not sandbox_info.get('id'):
        raise ValueError(f"No sandbox found for project {project_id}")
    enabled_tools = None
    if agent_config and 'agentpress_tools' in agent_config:
        enabled_tools = agent_config['agentpress_tools']
        logger.info(f"Using custom tool configuration from agent")
    if is_agent_builder:
        logger.info("Agent builder mode - registering only update agent tool")
        from agent.tools.update_agent_tool import UpdateAgentTool
        from services.supabase import DBConnection
        db = DBConnection()
        thread_manager.add_tool(
            UpdateAgentTool, thread_manager=thread_manager, db_connection=db, agent_id=target_agent_id)
    if enabled_tools is None:
        # No agent specified - register ALL tools for full Suna experience
        logger.info(
            "No agent specified - registering all tools for full Suna capabilities")
        thread_manager.add_tool(
            SandboxShellTool, project_id=project_id, thread_manager=thread_manager)
        thread_manager.add_tool(
            SandboxFilesTool, project_id=project_id, thread_manager=thread_manager)
        thread_manager.add_tool(SandboxBrowserTool, project_id=project_id,
                                thread_id=thread_id, thread_manager=thread_manager)
        thread_manager.add_tool(
            SandboxDeployTool, project_id=project_id, thread_manager=thread_manager)
        thread_manager.add_tool(
            SandboxExposeTool, project_id=project_id, thread_manager=thread_manager)
        thread_manager.add_tool(
            ExpandMessageTool, thread_id=thread_id, thread_manager=thread_manager)
        thread_manager.add_tool(MessageTool)
        thread_manager.add_tool(
            SandboxWebSearchTool, project_id=project_id, thread_manager=thread_manager)
        thread_manager.add_tool(SandboxVisionTool, project_id=project_id,
                                thread_id=thread_id, thread_manager=thread_manager)
        if config.RAPID_API_KEY:
            thread_manager.add_tool(DataProvidersTool)
    else:
        logger.info("Custom agent specified - registering only enabled tools")
        thread_manager.add_tool(
            ExpandMessageTool, thread_id=thread_id, thread_manager=thread_manager)
        thread_manager.add_tool(MessageTool)
        if enabled_tools.get('sb_shell_tool', {}).get('enabled', False):
            thread_manager.add_tool(
                SandboxShellTool, project_id=project_id, thread_manager=thread_manager)
        if enabled_tools.get('sb_files_tool', {}).get('enabled', False):
            thread_manager.add_tool(
                SandboxFilesTool, project_id=project_id, thread_manager=thread_manager)
        if enabled_tools.get('sb_browser_tool', {}).get('enabled', False):
            thread_manager.add_tool(SandboxBrowserTool, project_id=project_id,
                                    thread_id=thread_id, thread_manager=thread_manager)
        if enabled_tools.get('sb_deploy_tool', {}).get('enabled', False):
            thread_manager.add_tool(
                SandboxDeployTool, project_id=project_id, thread_manager=thread_manager)
        if enabled_tools.get('sb_expose_tool', {}).get('enabled', False):
            thread_manager.add_tool(
                SandboxExposeTool, project_id=project_id, thread_manager=thread_manager)
        if enabled_tools.get('web_search_tool', {}).get('enabled', False):
            thread_manager.add_tool(
                SandboxWebSearchTool, project_id=project_id, thread_manager=thread_manager)
        if enabled_tools.get('sb_vision_tool', {}).get('enabled', False):
            thread_manager.add_tool(SandboxVisionTool, project_id=project_id,
                                    thread_id=thread_id, thread_manager=thread_manager)
        if config.RAPID_API_KEY and enabled_tools.get('data_providers_tool', {}).get('enabled', False):
            thread_manager.add_tool(DataProvidersTool)
    mcp_wrapper_instance = None
    if agent_config:
        # Merge configured_mcps and custom_mcps
        all_mcps = []

        # Add standard configured MCPs
        if agent_config.get('configured_mcps'):
            all_mcps.extend(agent_config['configured_mcps'])

        # Add custom MCPs
        if agent_config.get('custom_mcps'):
            for custom_mcp in agent_config['custom_mcps']:
                # Transform custom MCP to standard format
                mcp_config = {
                    'name': custom_mcp['name'],
                    'qualifiedName': f"custom_{custom_mcp['type']}_{custom_mcp['name'].replace(' ', '_').lower()}",
                    'config': custom_mcp['config'],
                    'enabledTools': custom_mcp.get('enabledTools', []),
                    'isCustom': True,
                    'customType': custom_mcp['type']
                }
                all_mcps.append(mcp_config)
        if all_mcps:
            logger.info(
                f"Registering MCP tool wrapper for {len(all_mcps)} MCP servers (including {len(agent_config.get('custom_mcps', []))} custom)")
            # Register the tool with all MCPs
            thread_manager.add_tool(MCPToolWrapper, mcp_configs=all_mcps)

            # Get the tool instance from the registry
            # The tool is registered with method names as keys
            for tool_name, tool_info in thread_manager.tool_registry.tools.items():
                if isinstance(tool_info['instance'], MCPToolWrapper):
                    mcp_wrapper_instance = tool_info['instance']
                    break
            if mcp_wrapper_instance:
                try:
                    await mcp_wrapper_instance.initialize_and_register_tools()
                    logger.info("MCP tools initialized successfully")

                    # Re-register the updated schemas with the tool registry
                    # This ensures the dynamically created tools are available for function calling
                    updated_schemas = mcp_wrapper_instance.get_schemas()
                    for method_name, schema_list in updated_schemas.items():
                        if method_name != 'call_mcp_tool':  # Skip the fallback method
                            # Register each dynamic tool in the registry
                            for schema in schema_list:
                                if schema.schema_type == SchemaType.OPENAPI:
                                    thread_manager.tool_registry.tools[method_name] = {
                                        "instance": mcp_wrapper_instance,
                                        "schema": schema
                                    }
                                    logger.debug(
                                        f"Registered dynamic MCP tool: {method_name}")

                except Exception as e:
                    logger.error(f"Failed to initialize MCP tools: {e}")
                    # Continue without MCP tools if initialization fails
