from datetime import timedelta

from fastapi import APIRouter, Body, Depends, HTTPException, Request

from companion.api.schemas import (
    CommandRequest,
    CommandResponse,
    ConversationResponse,
    CreateConversationResponse,
    ReviewStateResponse,
    ReviewSubmissionResponse,
    SendMessageRequest,
    SendMessageResponse,
    TranscriptionResponse,
)
from companion.availability import AvailabilityService, OverrideRequest
from companion.commands.parser import AVAILABLE_COMMANDS, CommandParser
from companion.conversation import (
    AssistantRetryConflictError,
    ConversationEndedError,
    ConversationNotFoundError,
    ConversationService,
    MessageNotFoundError,
)
from companion.input_policy import ENGLISH_INPUT_REDIRECT
from companion.learning import (
    LearningItemNotDueError,
    LearningItemNotFoundError,
    LearningService,
    ReviewAnswerRequest,
    ReviewInputLanguageError,
)
from companion.memory import (
    AmbiguousMemoryIdError,
    MemoryNotFoundError,
    MemoryService,
    MemoryValidationError,
)
from companion.preferences import (
    LearnerPreferencesSchema,
    OnboardingOfferSchema,
    PreferencesService,
    PreferencesUpdate,
)
from companion.proactive import (
    InvitationConflictError,
    InvitationNotFoundError,
    InvitationSchema,
    PracticeFinalizeRequest,
    ProactiveCheckRequest,
    ProactiveCheckResponse,
    ProactiveRespondRequest,
    ProactiveRespondResponse,
    ProactiveService,
    ProactiveStatus,
)
from companion.providers.errors import LLMConfigurationError, LLMProviderError, LLMRateLimitError
from companion.providers.protocols import LLMProvider
from companion.providers.schemas import LanguageHelpMode, LanguageHelpRequest
from companion.schemas.availability import AvailabilityState, StateResponse
from companion.settings import get_settings
from companion.speech import SpeechTranscriber

from .dependencies import (
    get_availability_service,
    get_conversation_service,
    get_learning_service,
    get_llm_provider,
    get_llm_status,
    get_memory_service,
    get_preferences_service,
    get_proactive_service,
    get_speech_transcriber,
)

router = APIRouter()
AvailabilityDependency = Depends(get_availability_service)
ConversationDependency = Depends(get_conversation_service)
LLMDependency = Depends(get_llm_provider)
MemoryDependency = Depends(get_memory_service)
LearningDependency = Depends(get_learning_service)
ProactiveDependency = Depends(get_proactive_service)
PreferencesDependency = Depends(get_preferences_service)
SpeechDependency = Depends(get_speech_transcriber)


@router.post("/v1/speech/transcriptions")
async def transcribe_audio(
    request: Request,
    audio: bytes = Body(media_type="audio/wav"),
    transcriber: SpeechTranscriber = SpeechDependency,
) -> TranscriptionResponse:
    try:
        transcript = await transcriber.transcribe(
            audio, content_type=request.headers.get("content-type", "audio/wav")
        )
    except LLMProviderError as exc:
        status = 429 if isinstance(exc, LLMRateLimitError) else 503
        raise HTTPException(status_code=status, detail=str(exc)) from exc
    return TranscriptionResponse(transcript=transcript)


@router.get("/v1/preferences")
async def read_preferences(
    service: PreferencesService = PreferencesDependency,
) -> LearnerPreferencesSchema:
    return service.read()


@router.patch("/v1/preferences")
async def update_preferences(
    request: PreferencesUpdate,
    service: PreferencesService = PreferencesDependency,
) -> LearnerPreferencesSchema:
    return service.update(request)


@router.post("/v1/preferences/reset")
async def reset_preferences(
    service: PreferencesService = PreferencesDependency,
) -> LearnerPreferencesSchema:
    return service.reset()


@router.post("/v1/preferences/onboarding/offer")
async def offer_preferences_onboarding(
    service: PreferencesService = PreferencesDependency,
) -> OnboardingOfferSchema:
    return OnboardingOfferSchema(should_offer=service.offer_onboarding())


@router.post("/v1/preferences/onboarding/restart")
async def restart_preferences_onboarding(
    service: PreferencesService = PreferencesDependency,
) -> OnboardingOfferSchema:
    return OnboardingOfferSchema(should_offer=service.restart_onboarding())


@router.post("/v1/proactive/check")
async def check_proactive(
    request: ProactiveCheckRequest,
    service: ProactiveService = ProactiveDependency,
) -> ProactiveCheckResponse:
    return ProactiveCheckResponse(invitation=service.check(request))


@router.post("/v1/proactive/status")
async def proactive_status(
    request: ProactiveCheckRequest,
    service: ProactiveService = ProactiveDependency,
) -> ProactiveStatus:
    return service.status(request)


@router.post("/v1/proactive/invitations/{invitation_id}/respond")
async def respond_proactive(
    invitation_id: str,
    request: ProactiveRespondRequest,
    service: ProactiveService = ProactiveDependency,
) -> ProactiveRespondResponse:
    try:
        return service.respond(invitation_id, request.decision, request.conversation_id)
    except InvitationNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Invitation not found") from exc
    except InvitationConflictError as exc:
        raise HTTPException(status_code=409, detail="Invitation is no longer pending") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/v1/proactive/invitations/{invitation_id}/practice/complete")
async def complete_proactive_practice(
    invitation_id: str,
    request: PracticeFinalizeRequest,
    service: ProactiveService = ProactiveDependency,
) -> InvitationSchema:
    try:
        return service.finalize_practice(invitation_id, **request.model_dump())
    except InvitationNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Invitation not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except InvitationConflictError as exc:
        raise HTTPException(status_code=409, detail="Practice is already terminal") from exc


@router.post("/v1/proactive/invitations/{invitation_id}/practice/abandon")
async def abandon_proactive_practice(
    invitation_id: str,
    service: ProactiveService = ProactiveDependency,
) -> InvitationSchema:
    try:
        return service.abandon_practice(invitation_id)
    except InvitationNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Invitation not found") from exc
    except InvitationConflictError as exc:
        raise HTTPException(status_code=409, detail="Practice is already terminal") from exc


@router.get("/health")
async def health() -> dict[str, str | int]:
    settings = get_settings()
    return {
        "status": "ok",
        "service": "companion_core",
        "environment": settings.env,
        "schema_version": settings.schema_version,
    }


@router.get("/v1/state")
async def state(
    availability: AvailabilityService = AvailabilityDependency,
    learning_service: LearningService = LearningDependency,
) -> StateResponse:
    settings = get_settings()
    snapshot = availability.snapshot()
    return StateResponse(
        status="ok",
        user_id=settings.user_id,
        availability=snapshot.state,
        override_expires_at=snapshot.expires_at,
        timezone=settings.timezone,
        remaining_seconds=snapshot.remaining_seconds,
        llm=get_llm_status(),
        due_review_count=learning_service.due_count(),
    )


@router.post("/v1/commands/execute")
async def execute_command(
    request: CommandRequest,
    availability: AvailabilityService = AvailabilityDependency,
    conversation_service: ConversationService = ConversationDependency,
    llm_provider: LLMProvider = LLMDependency,
    memory_service: MemoryService = MemoryDependency,
    learning_service: LearningService = LearningDependency,
) -> CommandResponse:
    settings = get_settings()
    parsed = CommandParser(
        max_busy_duration=timedelta(hours=settings.busy_max_duration_hours)
    ).parse(request.raw)

    if parsed.name == "busy":
        duration = parsed.duration or timedelta(minutes=30)
        snapshot = availability.set_override(
            OverrideRequest(
                state=AvailabilityState.BUSY,
                duration=duration,
                source="terminal",
            )
        )
        return CommandResponse(
            command="busy",
            ok=True,
            message="Availability changed to busy.",
            availability=snapshot,
        )

    if parsed.name == "dnd":
        snapshot = availability.set_override(
            OverrideRequest(
                state=AvailabilityState.DND,
                duration=None,
                source="terminal",
            )
        )
        return CommandResponse(
            command="dnd",
            ok=True,
            message="Availability changed to dnd.",
            availability=snapshot,
        )

    if parsed.name == "available":
        snapshot = availability.set_override(
            OverrideRequest(
                state=AvailabilityState.AVAILABLE,
                duration=None,
                source="terminal",
            )
        )
        return CommandResponse(
            command="available",
            ok=True,
            message="Availability changed to available.",
            availability=snapshot,
        )

    snapshot = availability.snapshot()
    if parsed.name == "status":
        llm_status = get_llm_status()
        return CommandResponse(
            command="status",
            ok=True,
            message=(
                f"Core ok. Availability is {snapshot.state.value}. "
                f"LLM provider={llm_status.provider} "
                f"model={llm_status.model or '-'} "
                f"status={llm_status.status}."
            ),
            availability=snapshot,
        )

    if parsed.name in {"help", "hint", "say"}:
        if parsed.content is None:
            return CommandResponse(command="unknown", ok=False, message="Missing command content.")
        return await _execute_language_command(
            parsed_name=parsed.name,
            content=parsed.content,
            conversation_id=request.conversation_id,
            conversation_service=conversation_service,
            llm_provider=llm_provider,
            learning_service=learning_service,
        )

    if parsed.name == "review":
        question = learning_service.first_due()
        return CommandResponse(
            command="review",
            ok=True,
            message="Review complete." if question is None else "Review started.",
            review_question=question,
            review_complete=question is None,
        )

    if parsed.name == "review_quit":
        return CommandResponse(
            command="review_quit",
            ok=True,
            message="Review stopped.",
        )

    if parsed.name == "remember":
        try:
            memory = await memory_service.remember(parsed.content or "")
        except MemoryValidationError as exc:
            return CommandResponse(command="remember", ok=False, message=str(exc))
        return CommandResponse(
            command="remember",
            ok=True,
            message=f"Remembered as {memory.short_id}.",
            memory=memory,
        )

    if parsed.name == "memories":
        memories = memory_service.search(parsed.content)
        return CommandResponse(
            command="memories",
            ok=True,
            message=f"Found {len(memories)} memories.",
            memories=memories,
        )

    if parsed.name == "forget":
        try:
            if parsed.confirm:
                memory = memory_service.forget(parsed.content or "")
                return CommandResponse(
                    command="forget",
                    ok=True,
                    message=f"Forgot memory {memory.short_id}.",
                    memory=memory,
                )
            preview = memory_service.preview_forget(parsed.content or "")
            return CommandResponse(
                command="forget",
                ok=True,
                message=(f"Confirm deletion with /forget {preview.memory.short_id} confirm"),
                memory=preview.memory,
                confirmation_required=True,
            )
        except AmbiguousMemoryIdError:
            return CommandResponse(
                command="forget",
                ok=False,
                message="Memory ID is ambiguous; use a longer ID.",
            )
        except MemoryNotFoundError:
            return CommandResponse(
                command="forget",
                ok=False,
                message="Memory not found.",
            )

    return CommandResponse(
        command="unknown",
        ok=False,
        message=parsed.error or f"Available commands: {AVAILABLE_COMMANDS}",
        availability=snapshot,
    )


@router.post("/v1/conversations")
async def create_conversation(
    conversation_service: ConversationService = ConversationDependency,
    memory_service: MemoryService = MemoryDependency,
) -> CreateConversationResponse:
    for recoverable in conversation_service.recover_interrupted_conversations():
        await memory_service.extract_conversation(recoverable.id)
    conversation = conversation_service.create_conversation()
    return CreateConversationResponse(
        id=conversation.id,
        mode=conversation.mode,
        started_at=conversation.started_at.isoformat(),
    )


@router.get("/v1/conversations/{conversation_id}")
async def get_conversation(
    conversation_id: str,
    conversation_service: ConversationService = ConversationDependency,
) -> ConversationResponse:
    try:
        return ConversationResponse(
            conversation=conversation_service.get_conversation(conversation_id)
        )
    except ConversationNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Conversation not found") from exc


@router.post("/v1/conversations/{conversation_id}/messages")
async def send_message(
    conversation_id: str,
    request: SendMessageRequest,
    conversation_service: ConversationService = ConversationDependency,
) -> SendMessageResponse:
    if not request.content.strip():
        raise HTTPException(status_code=400, detail="Message content is required")
    try:
        result = await conversation_service.send_user_message(
            conversation_id=conversation_id,
            content=request.content,
        )
    except ConversationNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Conversation not found") from exc
    except ConversationEndedError as exc:
        raise HTTPException(status_code=409, detail="Conversation has ended") from exc
    return SendMessageResponse(
        ok=result.error is None,
        user_message=result.user_message,
        assistant_message=result.assistant_message,
        error=result.error,
        retryable=result.retryable,
    )


@router.post("/v1/conversations/{conversation_id}/messages/{user_message_id}/retry-assistant")
async def retry_assistant_reply(
    conversation_id: str,
    user_message_id: str,
    conversation_service: ConversationService = ConversationDependency,
) -> SendMessageResponse:
    try:
        result = await conversation_service.retry_assistant_reply(
            conversation_id=conversation_id, user_message_id=user_message_id
        )
    except (ConversationNotFoundError, MessageNotFoundError) as exc:
        raise HTTPException(status_code=404, detail="Retry target not found") from exc
    except (ConversationEndedError, AssistantRetryConflictError) as exc:
        raise HTTPException(status_code=409, detail=str(exc) or "Retry target is stale") from exc
    return SendMessageResponse(
        ok=result.error is None,
        user_message=result.user_message,
        assistant_message=result.assistant_message,
        error=result.error,
        retryable=result.retryable,
    )


@router.post("/v1/conversations/{conversation_id}/end")
async def end_conversation(
    conversation_id: str,
    conversation_service: ConversationService = ConversationDependency,
    memory_service: MemoryService = MemoryDependency,
) -> ConversationResponse:
    try:
        conversation = conversation_service.end_conversation(conversation_id)
        extraction = await memory_service.extract_conversation(conversation_id)
        return ConversationResponse(
            conversation=conversation_service.get_conversation(conversation.id),
            memory_extraction=extraction,
        )
    except ConversationNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Conversation not found") from exc


@router.get("/v1/review")
async def get_review(
    learning_service: LearningService = LearningDependency,
) -> ReviewStateResponse:
    question = learning_service.first_due()
    return ReviewStateResponse(question=question, complete=question is None)


@router.post("/v1/review/{item_id}/hint")
async def get_review_hint(
    item_id: str,
    learning_service: LearningService = LearningDependency,
    llm_provider: LLMProvider = LLMDependency,
) -> CommandResponse:
    """Generate a hint for an existing review item without capturing assistance."""
    try:
        prompt = learning_service.review_prompt(item_id)
    except LearningItemNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Learning item not found") from exc

    try:
        help_response = await llm_provider.provide_language_help(
            LanguageHelpRequest(mode=LanguageHelpMode.HINT, content=prompt)
        )
    except LLMConfigurationError as exc:
        return CommandResponse(command="hint", ok=False, message=str(exc))
    except LLMProviderError as exc:
        return CommandResponse(command="hint", ok=False, message=str(exc), retryable=exc.retryable)

    return CommandResponse(
        command="hint",
        ok=True,
        message="Review hint generated.",
        hints=help_response.hints,
    )


@router.post("/v1/review/{item_id}/answer")
async def submit_review_answer(
    item_id: str,
    request: ReviewAnswerRequest,
    learning_service: LearningService = LearningDependency,
) -> ReviewSubmissionResponse:
    try:
        result = learning_service.answer(
            item_id=item_id,
            answer=request.answer,
            position=request.position,
            total=request.total,
        )
    except LearningItemNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Learning item not found") from exc
    except LearningItemNotDueError as exc:
        raise HTTPException(status_code=409, detail="Learning item is no longer due") from exc
    except ReviewInputLanguageError as exc:
        raise HTTPException(status_code=422, detail=ENGLISH_INPUT_REDIRECT) from exc
    return ReviewSubmissionResponse(result=result)


async def _execute_language_command(
    *,
    parsed_name: str,
    content: str,
    conversation_id: str | None,
    conversation_service: ConversationService,
    llm_provider: LLMProvider,
    learning_service: LearningService,
) -> CommandResponse:
    mode = LanguageHelpMode(parsed_name)
    if mode == LanguageHelpMode.SAY and not conversation_id:
        return CommandResponse(
            command="say",
            ok=False,
            message="/say requires a valid conversation_id.",
        )

    try:
        help_response = await llm_provider.provide_language_help(
            LanguageHelpRequest(mode=mode, content=content)
        )
    except LLMConfigurationError as exc:
        return CommandResponse(command=parsed_name, ok=False, message=str(exc))
    except LLMProviderError as exc:
        return CommandResponse(
            command=parsed_name,
            ok=False,
            message=str(exc),
            retryable=exc.retryable,
        )

    if mode == LanguageHelpMode.SAY:
        if not help_response.natural_expression:
            return CommandResponse(
                command="say",
                ok=False,
                message="No English translation returned.",
            )
        try:
            result = await conversation_service.insert_translated_user_message(
                conversation_id=conversation_id or "",
                english_content=help_response.natural_expression,
            )
        except ConversationNotFoundError:
            return CommandResponse(
                command="say",
                ok=False,
                message="/say requires a valid conversation_id.",
            )
        except ConversationEndedError as exc:
            raise HTTPException(status_code=409, detail="Conversation has ended") from exc
        return CommandResponse(
            command="say",
            ok=result.error is None,
            message="Inserted translated English into the conversation.",
            natural_expression=help_response.natural_expression,
            inserted_into_conversation=True,
            inserted_text=help_response.natural_expression,
            inserted_user_message=result.user_message,
            assistant_message=result.assistant_message,
            assistant_error=result.error,
            retryable=result.retryable,
        )

    learning_item = learning_service.capture_assistance(
        mode=mode,
        prompt=content,
        response=help_response,
    )

    return CommandResponse(
        command=parsed_name,
        ok=True,
        message="Language help generated.",
        natural_expression=help_response.natural_expression,
        alternatives=help_response.alternatives,
        notes_zh=help_response.notes_zh,
        correction=help_response.correction,
        hints=help_response.hints,
        inserted_into_conversation=False,
        learning_item=learning_item,
    )
