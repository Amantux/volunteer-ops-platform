"""Import every model module so Base.metadata and Alembic autogenerate see them all."""

from __future__ import annotations

from app.core.audit import AuditEvent  # noqa: F401
from app.core.outbox import OutboxEvent  # noqa: F401
from app.modules.agents.models import AgentProposal  # noqa: F401
from app.modules.communications.models import (  # noqa: F401
    EmailDeliveryEvent,
    EmailMessage,
    EmailTemplate,
    InboxMessage,
)
from app.modules.identity.models import (  # noqa: F401
    Person,
    Role,
    RolePermission,
    User,
    UserRoleAssignment,
    VerificationToken,
)
from app.modules.org.models import (  # noqa: F401
    Organization,
    OrganizationSetting,
    Program,
)
from app.modules.people.models import (  # noqa: F401
    QualificationType,
    VolunteerProfile,
    VolunteerQualification,
)
from app.modules.scheduling.models import (  # noqa: F401
    Event,
    Shift,
    ShiftRole,
    ShiftSignup,
    VolunteerHourEntry,
)
from app.modules.training.models import (  # noqa: F401
    Course,
    TrainingRegistration,
    TrainingSession,
)
