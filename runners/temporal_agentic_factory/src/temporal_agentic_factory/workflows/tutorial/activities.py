"""The tutorial activity: the folder checked and made. It fails at once on a
bad name or a folder in use, no retry: another try meets the same folder."""

from pathlib import Path

from temporalio import activity
from temporalio.exceptions import ApplicationError
from tutorial.run import located_dir


@activity.defn
async def locate_tutorial(folder: str) -> str:
    """The tutorial's folder made with its specs/, refused when its name is
    not a plain folder name or it holds files already: its absolute path."""
    try:
        return str(located_dir(Path(folder)))
    except ValueError as error:
        raise ApplicationError(str(error), type="BadFolder", non_retryable=True) from error
