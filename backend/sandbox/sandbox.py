from daytona_api_client.models.workspace_state import WorkspaceState
from daytona_sdk import (CreateSandboxParams, Daytona, DaytonaConfig, Sandbox,
                         SessionExecuteRequest)
from dotenv import load_dotenv

from utils.config import Configuration, config
from utils.logger import logger

load_dotenv()

logger.debug("Initializing Daytona sandbox configuration")
daytona_config = DaytonaConfig(
    api_key=config.DAYTONA_API_KEY,
    server_url=config.DAYTONA_SERVER_URL,
    target=config.DAYTONA_TARGET,
)

if daytona_config.api_key:
    logger.debug("Daytona API key configured successfully")
else:
    logger.warning("No Daytona API key found in environment variables")


if daytona_config.server_url:
    logger.debug(f"Daytona server URL set to: {daytona_config.server_url}")
else:
    logger.warning("No Daytona server URL found in environment variables")

if daytona_config.target:
    logger.debug(f"Daytona target set to: {daytona_config.target}")
else:
    logger.warning("No Daytona target found in environment variables")
daytona = Daytona(daytona_config)
logger.debug("Daytona client initialized")


async def get_or_start_sandbox(sandbox_id: str):
    logger.info(f"Getting or starting sandbox with ID: {sandbox_id}")
    try:
        sandbox = daytona.get_current_sandbox(sandbox_id)
        if (
            sandbox.instance.state == WorkspaceState.ARCHIVED
            or sandbox.instance.state == WorkspaceState.STOPPED
        ):
            logger.info(
                f"Sandbox is in {sandbox.instance.state} state. Starting...")
            try:
                daytona.start(sandbox)

                sandbox = daytona.get_current_sandbox(sandbox_id)

                start_supervisord_session(sandbox)
            except:
                logger.error(f"Error starting sandbox: {e}")
                raise e
    except Exception as e:
        logger.error(f"Error retrieving or starting sandbox: {str(e)}")
        raise e


def start_supervisord_session(sandbox: Sandbox):
    session_id = "supervisord-session"
    try:
        logger.info(f"Creating session {session_id} for supervisord")
        sandbox.process.create_session(session_id)

        # Execute supervisord command
        sandbox.process.execute_session_command(
            session_id,
            SessionExecuteRequest(
                command="exec /usr/bin/supervisord -n -c /etc/supervisor/conf.d/supervisord.conf",
                var_async=True,
            ),
        )
        logger.info(f"Supervisord started in session {session_id}")
    except Exception as e:
        logger.error(f"Error starting supervisord session: {str(e)}")
        raise e


def create_sandbox(password: str, project_id: str = None):
    logger.debug("Creating new Daytona sandbox environment")
    logger.debug(
        "Configuring sandbox with browser-use image and environment variables")
    labels = None
    if project_id:
        logger.debug(f"Using sandbox_id as label: {project_id}")
        labels = {'id': project_id}
    params = CreateSandboxParams(
        image=Configuration.SANDBOX_IMAGE_NAME,
        public=True,
        labels=labels,
        env_vars={
            "CHROME_PERSISTENT_SESSION": "true",
            "RESOLUTION": "1024x768x24",
            "RESOLUTION_WIDTH": "1024",
            "RESOLUTION_HEIGHT": "768",
            "VNC_PASSWORD": password,
            "ANONYMIZED_TELEMETRY": "false",
            "CHROME_PATH": "",
            "CHROME_USER_DATA": "",
            "CHROME_DEBUGGING_PORT": "9222",
            "CHROME_DEBUGGING_HOST": "localhost",
            "CHROME_CDP": ""
        },
        resources={
            "cpu": 2,
            "memory": 4,
            "disk": 5,
        }
    )

    sandbox = daytona.create(params)
    logger.debug(f"Sandbox created with ID: {sandbox.id}")
    start_supervisord_session(sandbox)

    logger.debug(f"Sandbox environment successfully initialized")
    return sandbox


async def delete_sandbox(sandbox_id: str):
    logger.info(f"Deleting sandbox with ID: {sandbox_id}")

    try:
        sandbox = daytona.get_current_sandbox(sandbox_id)

        daytona.remove(sandbox)

        logger.info(f"Successfully deleted sandbox {sandbox_id}")
        return True
    except Exception as e:
        logger.error(f"Error deleting sandbox {sandbox_id}: {str(e)}")
        raise e
