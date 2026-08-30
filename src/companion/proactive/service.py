from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from companion.availability import AvailabilityService
from companion.clock import Clock, system_clock
from companion.learning import LearningService
from companion.persistence.models import ProactiveInvitation
from companion.persistence.repositories import decode_dt
from companion.preferences import LearnerPreferencesSchema, PreferencesService, ProactiveCadence
from companion.proactive.errors import InvitationConflictError, InvitationNotFoundError
from companion.proactive.repository import ProactiveRepository
from companion.proactive.schemas import (
    InvitationDecision,
    InvitationKind,
    InvitationSchema,
    InvitationStatus,
    PracticeOutcome,
    ProactiveCheckRequest,
    ProactiveReason,
    ProactiveRespondResponse,
    ProactiveStatus,
)
from companion.schemas.availability import AvailabilityState
from companion.settings import Settings

STARTERS = (
    ("week-highlight", "What was one highlight of your week, and why did it matter to you?"),
    ("recent-learning", "Tell me about something interesting you learned recently."),
    ("ideal-weekend", "What would your ideal weekend look like?"),
    ("small-goal", "What is one small goal you would like to achieve this week?"),
)


class ProactiveService:
    def __init__(
        self,
        *,
        repository: ProactiveRepository,
        availability: AvailabilityService,
        learning: LearningService,
        settings: Settings,
        clock: Clock = system_clock,
        preferences: PreferencesService | None = None,
    ) -> None:
        self._repository = repository
        self._availability = availability
        self._learning = learning
        self._settings = settings
        self._clock = clock
        self._preferences = preferences

    def check(self, request: ProactiveCheckRequest) -> InvitationSchema | None:
        status = self.status(request)
        if status.reason == ProactiveReason.PENDING_INVITATION:
            pending = self._repository.pending(self._settings.user_id)
            return self._schema(pending) if pending is not None else None
        if not status.eligible:
            return None
        now = self._now()
        today = now.date()
        kind = status.next_kind
        key = prompt = None
        if kind == InvitationKind.CONVERSATION:
            count = self._repository.delivery_count(self._settings.user_id, today, kind)
            index = count % len(STARTERS)
            key, prompt = STARTERS[index]
        return self._schema(
            self._repository.create(
                user_id=self._settings.user_id,
                kind=kind,
                now=now,
                local_date=today,
                starter_key=key,
                starter_prompt=prompt,
            )
        )

    def status(self, request: ProactiveCheckRequest) -> ProactiveStatus:
        """Explain the same eligibility path as ``check`` without delivering an invite."""
        now = self._now()
        profile = self._preference_profile()
        review_idle, conversation_idle, daily_limit, _ = self._policy(profile)
        completed = self._preferences is not None and self._preferences.has_completed_preferences()
        availability = self._availability.snapshot()
        due_count = self._learning.due_count()
        next_kind = InvitationKind.REVIEW if due_count else InvitationKind.CONVERSATION
        threshold = review_idle if due_count else conversation_idle
        deliveries = self._repository.delivery_count(self._settings.user_id, now.date())
        reason = ProactiveReason.ELIGIBLE
        not_before = None
        if not request.can_present:
            reason = ProactiveReason.UI_CANNOT_PRESENT
        elif availability.state == AvailabilityState.BUSY:
            reason, not_before = ProactiveReason.BUSY, availability.expires_at
        elif availability.state == AvailabilityState.DND:
            reason = ProactiveReason.DND
        else:
            hours_reason = self._preferred_hours_reason(now, profile)
            if hours_reason is not None:
                reason = hours_reason
            elif self._repository.accepted_conversation(self._settings.user_id) is not None:
                reason = ProactiveReason.ACCEPTED_PRACTICE
            elif self._repository.pending(self._settings.user_id) is not None:
                reason = ProactiveReason.PENDING_INVITATION
            else:
                latest = self._repository.latest(self._settings.user_id)
                if latest and latest.suppress_until and decode_dt(latest.suppress_until) > now:
                    not_before = decode_dt(latest.suppress_until)
                    reason = {
                        InvitationStatus.SNOOZED.value: ProactiveReason.SNOOZED,
                        InvitationStatus.DISMISSED.value: ProactiveReason.DISMISSED_TODAY,
                    }.get(latest.status, ProactiveReason.ACCEPTED_COOLDOWN)
                elif deliveries >= daily_limit:
                    reason = ProactiveReason.DAILY_LIMIT
                elif request.idle_seconds < threshold:
                    reason = ProactiveReason.INSUFFICIENT_IDLE
        return ProactiveStatus(
            cadence=profile.proactive_cadence.value,
            uses_legacy_policy=not completed,
            availability=availability.state,
            availability_expires_at=availability.expires_at,
            eligible=reason == ProactiveReason.ELIGIBLE,
            reason=reason,
            due_review_count=due_count,
            next_kind=next_kind,
            idle_threshold_seconds=threshold,
            idle_remaining_seconds=max(0.0, threshold - request.idle_seconds),
            not_before=not_before,
            daily_delivery_count=deliveries,
            daily_delivery_limit=daily_limit,
            active_hours_start=str(profile.active_hours_start)
            if profile.active_hours_start
            else None,
            active_hours_end=str(profile.active_hours_end) if profile.active_hours_end else None,
            quiet_hours_start=str(profile.quiet_hours_start) if profile.quiet_hours_start else None,
            quiet_hours_end=str(profile.quiet_hours_end) if profile.quiet_hours_end else None,
        )

    def respond(
        self,
        invitation_id: str,
        decision: InvitationDecision,
        conversation_id: str | None = None,
    ) -> ProactiveRespondResponse:
        row = self._repository.get(invitation_id, self._settings.user_id)
        if row is None:
            raise InvitationNotFoundError(invitation_id)
        if row.status != InvitationStatus.PENDING.value:
            raise InvitationConflictError(invitation_id)
        now = self._now()
        if (
            decision == InvitationDecision.START
            and row.kind == InvitationKind.CONVERSATION.value
            and conversation_id is None
        ):
            raise ValueError("conversation_id is required to start conversation practice")
        status = InvitationStatus.ACCEPTED
        boundary = now + timedelta(minutes=self._policy(self._preference_profile())[3])
        if decision == InvitationDecision.SNOOZE:
            status = InvitationStatus.SNOOZED
            boundary = now + timedelta(minutes=self._settings.proactive_snooze_minutes)
        elif decision == InvitationDecision.DISMISS_TODAY:
            status = InvitationStatus.DISMISSED
            boundary = datetime.combine(now.date() + timedelta(days=1), time(), tzinfo=now.tzinfo)
        if not self._repository.resolve(
            row,
            status=status,
            now=now,
            suppress_until=boundary,
            conversation_id=(
                conversation_id
                if decision == InvitationDecision.START
                and row.kind == InvitationKind.CONVERSATION.value
                else None
            ),
        ):
            raise InvitationConflictError(invitation_id)
        schema = self._schema(row)
        if decision != InvitationDecision.START:
            return ProactiveRespondResponse(invitation=schema)
        if row.kind == InvitationKind.REVIEW.value:
            question = self._learning.first_due()
            return ProactiveRespondResponse(
                invitation=schema, review_question=question, review_complete=question is None
            )
        return ProactiveRespondResponse(invitation=schema, conversation_starter=row.starter_prompt)

    def finalize_practice(
        self,
        invitation_id: str,
        *,
        conversation_id: str,
        user_message_id: str,
        assistant_message_id: str,
    ) -> InvitationSchema:
        row = self._practice_invitation(invitation_id)
        if row.status in {InvitationStatus.COMPLETED.value, InvitationStatus.ABANDONED.value}:
            if (
                row.status == InvitationStatus.COMPLETED.value
                and row.conversation_id == conversation_id
                and row.user_message_id == user_message_id
                and row.assistant_message_id == assistant_message_id
            ):
                return self._schema(row)
            raise InvitationConflictError(invitation_id)
        if row.conversation_id != conversation_id:
            raise ValueError("Practice evidence does not belong to the bound conversation")
        occurrence = self._repository.validated_practice_evidence(
            user_id=self._settings.user_id,
            conversation_id=conversation_id,
            user_message_id=user_message_id,
            assistant_message_id=assistant_message_id,
        )
        outcome = (
            PracticeOutcome.LEARNING_SIGNAL_CAPTURED
            if occurrence
            else PracticeOutcome.COMPLETED_NOT_EVALUATED
        )
        if not self._repository.finish_practice(
            row,
            status=InvitationStatus.COMPLETED,
            outcome=outcome.value,
            now=self._now(),
            conversation_id=conversation_id,
            user_message_id=user_message_id,
            assistant_message_id=assistant_message_id,
            occurrence=occurrence,
        ):
            raise InvitationConflictError(invitation_id)
        return self._schema(row)

    def abandon_practice(self, invitation_id: str) -> InvitationSchema:
        row = self._practice_invitation(invitation_id)
        if row.status == InvitationStatus.ABANDONED.value:
            return self._schema(row)
        if row.status != InvitationStatus.ACCEPTED.value or not self._repository.finish_practice(
            row,
            status=InvitationStatus.ABANDONED,
            outcome=PracticeOutcome.ABANDONED.value,
            now=self._now(),
            conversation_id=row.conversation_id,
        ):
            raise InvitationConflictError(invitation_id)
        return self._schema(row)

    def reconcile_accepted_practices(self) -> list[InvitationSchema]:
        """Resolve stale accepted practice using only one exact post-acceptance turn."""
        resolved: list[InvitationSchema] = []
        for row in self._repository.practices_awaiting_evaluation(self._settings.user_id):
            if row.user_message_id is None or row.assistant_message_id is None:
                continue
            processing = self._repository.processing_state(row.user_message_id)
            if processing is None or processing.status not in {
                "completed",
                "no_candidate",
                "failed",
            }:
                continue
            occurrence = self._repository.validated_practice_evidence(
                user_id=self._settings.user_id,
                conversation_id=row.conversation_id or "",
                user_message_id=row.user_message_id,
                assistant_message_id=row.assistant_message_id,
            )
            if occurrence is not None:
                self._repository.attach_practice_occurrence(row, occurrence)
                resolved.append(self._schema(row))
        for row in self._repository.accepted_conversations(self._settings.user_id):
            messages = []
            if (
                row.conversation_id is not None
                and row.responded_at is not None
                and self._repository.conversation_belongs_to(
                    row.conversation_id, self._settings.user_id
                )
            ):
                messages = self._repository.messages_at_or_after(
                    conversation_id=row.conversation_id,
                    boundary=decode_dt(row.responded_at),
                )
            if (
                len(messages) == 2
                and messages[0].role == "user"
                and messages[1].role == "assistant"
            ):
                resolved.append(
                    self.finalize_practice(
                        row.id,
                        conversation_id=row.conversation_id or "",
                        user_message_id=messages[0].id,
                        assistant_message_id=messages[1].id,
                    )
                )
            else:
                resolved.append(self.abandon_practice(row.id))
        return resolved

    def _practice_invitation(self, invitation_id: str) -> ProactiveInvitation:
        row = self._repository.get(invitation_id, self._settings.user_id)
        if row is None:
            raise InvitationNotFoundError(invitation_id)
        if row.kind != InvitationKind.CONVERSATION.value:
            raise InvitationConflictError(invitation_id)
        return row

    def _now(self) -> datetime:
        value = self._clock()
        return value.astimezone(ZoneInfo(self._settings.timezone))

    def _preference_profile(self) -> LearnerPreferencesSchema:
        return self._preferences.read() if self._preferences else LearnerPreferencesSchema()

    def _policy(self, profile: LearnerPreferencesSchema) -> tuple[int, int, int, int]:
        if self._preferences is None or not self._preferences.has_completed_preferences():
            return (
                self._settings.proactive_review_idle_seconds,
                self._settings.proactive_conversation_idle_seconds,
                self._settings.proactive_daily_limit,
                self._settings.proactive_accept_cooldown_minutes,
            )
        if profile.proactive_cadence == ProactiveCadence.RARE:
            return (1200, 3600, 1, 120)
        if profile.proactive_cadence == ProactiveCadence.FREQUENT:
            return (300, 900, 5, 30)
        return (600, 1800, 3, 60)

    @staticmethod
    def _within_preferred_hours(now: datetime, profile: LearnerPreferencesSchema) -> bool:
        return ProactiveService._preferred_hours_reason(now, profile) is None

    @staticmethod
    def _preferred_hours_reason(
        now: datetime, profile: LearnerPreferencesSchema
    ) -> ProactiveReason | None:
        def contains(current: time, start: time, end: time) -> bool:
            return start <= current < end if start < end else current >= start or current < end

        current = now.timetz().replace(tzinfo=None)
        if (
            profile.active_hours_start
            and profile.active_hours_end
            and not contains(current, profile.active_hours_start, profile.active_hours_end)
        ):
            return ProactiveReason.OUTSIDE_ACTIVE_HOURS
        if (
            profile.quiet_hours_start
            and profile.quiet_hours_end
            and contains(current, profile.quiet_hours_start, profile.quiet_hours_end)
        ):
            return ProactiveReason.QUIET_HOURS
        return None

    @staticmethod
    def _schema(row: ProactiveInvitation) -> InvitationSchema:
        return InvitationSchema(
            id=row.id,
            kind=InvitationKind(row.kind),
            status=InvitationStatus(row.status),
            created_at=decode_dt(row.created_at),
            suppress_until=decode_dt(row.suppress_until) if row.suppress_until else None,
            starter_key=row.starter_key,
            starter_prompt=row.starter_prompt,
            conversation_id=row.conversation_id,
            user_message_id=row.user_message_id,
            assistant_message_id=row.assistant_message_id,
            learning_occurrence_id=row.learning_occurrence_id,
            learning_item_id=row.learning_item_id,
            outcome=PracticeOutcome(row.outcome) if row.outcome else None,
        )
