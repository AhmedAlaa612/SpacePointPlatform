# Interns domain models. Importing here registers them on Base.metadata.
from app.models.interns.project import Project, project_teams  # noqa: F401
from app.models.interns.team import Team, team_members  # noqa: F401
from app.models.interns.epic import Epic  # noqa: F401
from app.models.interns.module import Module  # noqa: F401
from app.models.interns.task import Task, task_assignees  # noqa: F401
from app.models.interns.submission import TaskSubmission  # noqa: F401
from app.models.interns.proposal import Proposal  # noqa: F401
from app.models.interns.mind_map import MindMapLayout, TaskMindMapNote  # noqa: F401
