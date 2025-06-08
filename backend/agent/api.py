import asyncio
import json
import os
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from fastapi import (APIRouter, Body, Depends, File, Form, HTTPException,
                     Query, Request, UploadFile)
from pydantic import BaseModel

from sandbox.sandbox import create_sandbox, delete_sandbox
from services import redis
from services.supabase import DBConnection
from utils.auth_utils import get_current_user_id_from_jwt
from utils.config import config
from utils.constants import MODEL_NAME_ALIASES
from utils.logger import logger

router = APIRouter()
db = None
instance_id = None


class AgentStartRequest(BaseModel):
    # Will be set from config.MODEL_TO_USE in the endpoint
    model_name: Optional[str] = None
    enable_thinking: Optional[bool] = False
    reasoning_effort: Optional[str] = "low"
    stream: Optional[bool] = True
    enable_context_manager: Optional[bool] = False
    agent_id: Optional[str] = None


class InitiateAgentResponse(BaseModel):
    thread_id: str
    agent_run_id: Optional[str] = None


def initialize(_db: DBConnection, _instance_id: str = None):
    global db, instance_id
    db = _db

    if _instance_id:
        instance_id = _instance_id
    else:
        instance_id = str(uuid.uuid4())[:8]

    logger.info(f"Initialized agent API with instance ID: {instance_id}")


async def cleanup():
    logger.info("Starting cleanup of agent API resources")
    try:
        if instance_id:  # Ensure instance_id is set
            running_keys = await redis.keys(f"active_run:{instance_id}:*")
            logger.info(
                f"Found {len(running_keys)} running agent runs for instance {instance_id} to clean up"
            )

            for key in running_keys:
                # Key format: active_run:{instance_id}:{agent_run_id}
                parts = key.split(":")
                if len(parts) == 3:
                    agent_run_id = parts[2]
                    await stop_agent_run(
                        agent_run_id,
                        error_message=f"Instance {instance_id} shutting down",
                    )
                else:
                    logger.warning(f"Unexpected key format found: {key}")
        else:
            logger.warning(
                "Instance ID not set, cannot clean up instance-specific agent runs."
            )
    except Exception as e:
        logger.error(f"Failed to clean up running agent runs: {str(e)}")


async def stop_agent_run(agent_run_id: str, error_message: Optional[str] = None):
    logger.info(f"Stopping agent run: {agent_run_id}")
    client = await db.client
    final_status = "failed" if error_message else "stopped"

    response_list_key = f"agent_run:{agent_run_id}:responses"
    all_responses = []
    try:
        all_responses_json = await redis.lrange(response_list_key, 0, -1)
        all_responses = [json.loads(r) for r in all_responses_json]
        logger.info(
            f"Fetched {len(all_responses)} responses from Redis for DB update on stop/fail: {agent_run_id}"
        )
    except Exception as e:
        logger.error(
            f"Failed to fetch responses from Redis for {agent_run_id} during stop/fail: {e}"
        )


async def verify_thread_access(client, thread_id: str, user_id: str):
    thread_result = (
        await client.table("threads")
        .select("*,project_id")
        .eq("thread_id", thread_id)
        .execute()
    )
    if not thread_result.data or len(thread_result.data) == 0:
        raise HTTPException(status_code=404, detail="Thread not found")
    thread_data = thread_result.data[0]
    # Check if project is public
    project_id = thread_data.get("project_id")
    if project_id:
        project_result = (
            await client.table("projects")
            .select("is_public")
            .eq("project_id", project_id)
            .execute()
        )
        if project_result.data and len(project_result.data) > 0:
            if project_result.data[0].get("is_public"):
                return True
    account_id = thread_data.get("account_id")
    if account_id:
        account_user_result = (
            await client.schema("basejump")
            .from_("account_user")
            .select("account_role")
            .eq("user_id", user_id)
            .eq("account_id", account_id)
            .execute()
        )
        if account_user_result.data and len(account_user_result.data) > 0:
            return True
    raise HTTPException(status_code=403, detail="Not authorized to access this thread")


# async def generate_and_update_project_name(project_id: str, prompt: str):
#     logger.info(
#         f"Starting background task to generate name for project: {project_id}")
#     try:
#         db_conn = DBConnection()
#         client = await db_conn.client
#         model_name = "openai/gpt-4o-mini"
#         system_prompt = "You are a helpful assistant that generates extremely concise titles (2-4 words maximum) for chat threads based on the user's message. Respond with only the title, no other text or punctuation."
#         user_message = f"Generate an extremely brief title (2-4 words only) for a chat thread that starts with this message: \"{prompt}\""
#         messages = [{"role": "system", "content": system_prompt},
#                     {"role": "user", "content": user_message}]
#         logger.debug(
#             f"Calling LLM ({model_name}) for project {project_id} naming.")
#         response = await make_llm_api_call(messages=messages, model_name=model_name, max_tokens=20, temperature=0.7)
#         generated_name = None
#         if response and response.get('choices') and response['choices'][0].get('message'):
#             raw_name = response['choices'][0]['message'].get(
#                 'content', '').strip()
#             cleaned_name = raw_name.strip('\'" \n\t')
#             if cleaned_name:
#                 generated_name = cleaned_name
#                 logger.info(
#                     f"LLM generated name for project {project_id}: '{generated_name}'")
#             else:
#                 logger.warning(
#                     f"LLM returned an empty name for project {project_id}.")
#         else:
#             logger.warning(
#                 f"Failed to get valid response from LLM for project {project_id} naming. Response: {response}")
#         if generated_name:
#             update_result = await client.table('projects').update({"name": generated_name}).eq("project_id", project_id).execute()
#             if hasattr(update_result, 'data') and update_result.data:
#                 logger.info(
#                     f"Successfully updated project {project_id} name to '{generated_name}'")
#             else:
#                 logger.error(
#                     f"Failed to update project {project_id} name in database. Update result: {update_result}")
#         else:
#             logger.warning(
#                 f"No generated name, skipping database update for project {project_id}.")

#     except Exception as e:
#         logger.error(
#             f"Error in background naming task for project {project_id}: {str(e)}\n{traceback.format_exc()}")
#     finally:
#         logger.info(
#             f"Finished background naming task for project: {project_id}")


@router.post("/agent/initiate", response_model=InitiateAgentResponse)
async def initiate_agent_with_files(
    prompt: str = Form(...),
    # Default to None to use config.MODEL_TO_USE
    model_name: Optional[str] = Form(None),
    enable_thinking: Optional[bool] = Form(False),
    reasoning_effort: Optional[str] = Form("low"),
    stream: Optional[bool] = Form(True),
    enable_context_manager: Optional[bool] = Form(False),
    agent_id: Optional[str] = Form(None),  # Add agent_id parameter
    files: List[UploadFile] = File(default=[]),
    is_agent_builder: Optional[bool] = Form(False),
    target_agent_id: Optional[str] = Form(None),
    # user_id: str = Depends(get_current_user_id_from_jwt),
    user_id: str = "cc907d80-ee45-4332-8bf3-e8cbe350300f",
):
    global instance_id
    if not instance_id:
        raise HTTPException(
            status_code=500, detail="Agent API not initialized with instance ID"
        )
    logger.info(f"Original model_name from request: {model_name}")
    if model_name is None:
        model_name = config.MODEL_TO_USE
        logger.info(f"Using model from config: {model_name}")
    resolved_model = MODEL_NAME_ALIASES.get(model_name, model_name)
    model_name = resolved_model

    logger.info(
        f"Starting new agent in agent builder mode: {is_agent_builder}, target_agent_id: {target_agent_id}"
    )
    logger.info(
        f"[\033[91mDEBUG\033[0m] Initiating new agent with prompt and {len(files)} files (Instance: {instance_id}), model: {model_name}, enable_thinking: {enable_thinking}"
    )
    client = await db.client
    account_id = user_id
    agent_config = None
    try:
        # 1. Create Project
        placeholder_name = f"{prompt[:30]}..." if len(prompt) > 30 else prompt
        project = (
            await client.table("projects")
            .insert(
                {
                    "project_id": str(uuid.uuid4()),
                    "account_id": account_id,
                    "name": placeholder_name,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
            )
            .execute()
        )
        project_id = project.data[0]["project_id"]
        logger.info(f"Created new project: {project_id}")
        # 2. Create Sandbox
        sandbox_id = None
        try:
            sandbox_pass = str(uuid.uuid4())
            sandbox = create_sandbox(sandbox_pass, project_id)
            sandbox_id = sandbox.id
            logger.info(f"Created new sandbox {sandbox_id} for project {project_id}")

            vnc_link = sandbox.get_preview_link(6080)
            website_link = sandbox.get_preview_link(8080)
            vnc_url = (
                vnc_link.url
                if hasattr(vnc_link, "url")
                else str(vnc_link).split("url='")[1].split("'")[0]
            )
            website_url = (
                website_link.url
                if hasattr(website_link, "url")
                else str(website_link).split("url='")[1].split("'")[0]
            )
            token = None
            if hasattr(vnc_link, "token"):
                token = vnc_link.token
            elif "token='" in str(vnc_link):
                token = str(vnc_link).split("token='")[1].split("'")[0]
        except Exception as e:
            logger.error(f"Error creating sandbox: {str(e)}")
            await client.table("projects").delete().eq(
                "project_id", project_id
            ).execute()
            if sandbox_id:
                try:
                    await delete_sandbox(sandbox_id)
                except Exception as e:
                    pass
            raise Exception("Failed to create sandbox")
        update_result = (
            await client.table("projects")
            .update(
                {
                    "sandbox": {
                        "id": sandbox_id,
                        "pass": sandbox_pass,
                        "vnc_preview": vnc_url,
                        "sandbox_url": website_url,
                        "token": token,
                    }
                }
            )
            .eq("project_id", project_id)
            .execute()
        )
        if not update_result.data:
            logger.error(
                f"Failed to update project {project_id} with new sandbox {sandbox_id}"
            )
            if sandbox_id:
                try:
                    await delete_sandbox(sandbox_id)
                except Exception as e:
                    logger.error(f"Error deleting sandbox: {str(e)}")
            raise Exception("Database update failed")
        # 3. Create Thread
        thread_data = {
            "thread_id": str(uuid.uuid4()),
            "project_id": project_id,
            "account_id": account_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        if agent_config:
            thread_data["agent_id"] = agent_config["agent_id"]
            logger.info(f"Storing agent_id {agent_config['agent_id']} in thread")
        if is_agent_builder:
            thread_data["metadata"] = {
                "is_agent_builder": True,
                "target_agent_id": target_agent_id,
            }
            logger.info(
                f"Storing agent builder metadata in thread: target_agent_id={target_agent_id}"
            )

        thread = await client.table("threads").insert(thread_data).execute()
        thread_id = thread.data[0]["thread_id"]
        logger.info(f"Created new thread: {thread_id}")
        # asyncio.create_task(generate_and_update_project_name(
        #     project_id=project_id, prompt=prompt))
        message_content = prompt
        # 4. Upload file to sandbox (if any)
        if files:
            successful_uploads = []
            failed_uploads = []
            for file in files:
                if file.filename:
                    try:
                        safe_filename = file.filename.replace("/", "_").replace(
                            "\\", "_"
                        )
                        target_path = f"/workspace/{safe_filename}"
                        logger.info(
                            f"Attempting to upload {safe_filename} to {target_path} in sandbox {sandbox_id}"
                        )
                        content = await file.read()
                        upload_successful = False
                        try:
                            if hasattr(sandbox, "fs") and hasattr(
                                sandbox.fs, "upload_file"
                            ):
                                import inspect

                                if inspect.iscoroutinefunction(sandbox.fs.upload_file):
                                    await sandbox.fs.upload_file(content, target_path)
                                else:
                                    sandbox.fs.upload_file(content, target_path)
                                logger.debug(
                                    f"Called sandbox.fs.upload_file for {target_path}"
                                )
                                upload_successful = True
                            else:
                                raise NotImplementedError(
                                    "Suitable upload method not found on sandbox object."
                                )
                        except Exception as upload_error:
                            logger.error(
                                f"Error during sandbox upload call for {safe_filename}: {str(upload_error)}",
                                exc_info=True,
                            )
                        if upload_successful:
                            try:
                                await asyncio.sleep(0.2)
                                parent_dir = os.path.dirname(target_path)
                                files_in_dir = sandbox.fs.list_files(parent_dir)
                                file_names_in_dir = [f.name for f in files_in_dir]
                                if safe_filename in file_names_in_dir:
                                    successful_uploads.append(target_path)
                                    logger.info(
                                        f"Successfully uploaded and verified file {safe_filename} to sandbox path {target_path}"
                                    )
                                else:
                                    logger.error(
                                        f"Verification failed for {safe_filename}: File not found in {parent_dir} after upload attempt."
                                    )
                                    failed_uploads.append(safe_filename)
                            except Exception as verify_error:
                                logger.error(
                                    f"Error verifying file {safe_filename} after upload: {str(verify_error)}",
                                    exc_info=True,
                                )
                                failed_uploads.append(safe_filename)
                        else:
                            failed_uploads.append(safe_filename)
                    except Exception as file_error:
                        logger.error(
                            f"Error processing file {file.filename}: {str(file_error)}",
                            exc_info=True,
                        )
                        failed_uploads.append(file.filename)
                    finally:
                        await file.close()
            if successful_uploads:
                message_content += "\n\n" if message_content else ""
                for file_path in successful_uploads:
                    message_content += f"[Uploaded File: {file_path}]\n"
            if failed_uploads:
                message_content += "\n\nThe following files failed to upload:\n"
                for failed_file in failed_uploads:
                    message_content += f"- {failed_file}\n"
        # 5. Add initial user message to thread
        message_id = str(uuid.uuid4())
        message_payload = {"role": "user", "content": message_content}
        await client.table("messages").insert(
            {
                "message_id": message_id,
                "thread_id": thread_id,
                "type": "user",
                "is_llm_message": True,
                "content": json.dumps(message_payload),
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        ).execute()
        # 6. Start the agent run
        agent_run = (
            await client.table("agent_runs")
            .insert(
                {
                    "thread_id": thread_id,
                    "status": "running",
                    "started_at": datetime.now(timezone.utc).isoformat(),
                }
            )
            .execute()
        )
        agent_run_id = agent_run.data[0]["id"]
        logger.info(f"Created new agent run: {agent_run_id}")
        # Register run in redis
        # Run agent in background
        return {"thread_id": thread_id, "agent_run_id": agent_run_id}

    except Exception as e:
        logger.error(f"Error in agent initiation: {str(e)}\n{traceback.format_exc()}")
        # TODO: Clean up created project/thread if initiation fails mid-way
        raise HTTPException(
            status_code=500, detail=f"Failed to initiate agent session: {str(e)}"
        )


@router.post("/thread/{thread_id}/agent/start")
async def start_agent(
    thread_id: str,
    body: AgentStartRequest = Body(...),
    user_id: str = Depends(get_current_user_id_from_jwt),
):
    global instance_id
    if not instance_id:
        raise HTTPException(
            status_code=500, detail="Agent API not initialized with instance ID"
        )
    model_name = body.model_name
    logger.info(f"Original model_name from request: {model_name}")
    if model_name is None:
        model_name = config.MODEL_TO_USE
        logger.info(f"Using model from config: {model_name}")
    resolved_model = MODEL_NAME_ALIASES.get(model_name, model_name)
    logger.info(f"Resolved model name: {resolved_model}")
    model_name = resolved_model
    logger.info(
        f"Starting new agent for thread: {thread_id} with config: model={model_name}, thinking={body.enable_thinking}, effort={body.reasoning_effort}, stream={body.stream}, context_manager={body.enable_context_manager} (Instance: {instance_id})"
    )
    client = await db.client
    await verify_thread_access(client, thread_id, user_id)
    thread_result = (
        await client.table("threads")
        .select("project_id", "account_id", "agent_id", "metadata")
        .eq("thread_id", thread_id)
        .execute()
    )
    if not thread_result.data:
        raise HTTPException(status_code=404, detail="Thread not found")
    thread_data = thread_result.data[0]
    project_id = thread_data.get("project_id")
    account_id = thread_data.get("account_id")
    thread_agent_id = thread_data.get("agent_id")
    thread_metadata = thread_data.get("metadata", {})

    is_agent_builder = thread_metadata.get("is_agent_builder", False)
    target_agent_id = thread_metadata.get("target_agent_id")
    if is_agent_builder:
        logger.info(
            f"Thread {thread_id} is in agent builder mode, target_agent_id: {target_agent_id}"
        )

    agent_config = None
    # Use provided agent_id or the one stored in thread
    effective_agent_id = body.agent_id or thread_agent_id


@router.post("/agent/{thread_id}/agent/start")
async def stop_agent(
    agent_run_id: str, user_id: str = Depends(get_current_user_id_from_jwt)
):
    logger.info(f"Received request to stop agent run: {agent_run_id}")
