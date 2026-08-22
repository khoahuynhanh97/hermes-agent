from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from typing import Any, Mapping

from hermes_personal.contracts import AgentEvent, AgentTurnRequest
from hermes_personal.identity import IdentityRepository, UnknownIdentity
from hermes_personal.sessions import SessionRepository, UnknownSession

from .ports import (
    AgentOutput,
    AuthorizationError,
    TranscriptFactory,
    UpstreamAgentPort,
)


class HermesTurnService:
    def __init__(
        self,
        identity_repository: IdentityRepository,
        session_repository: SessionRepository,
        transcript_factory: TranscriptFactory,
        agent: UpstreamAgentPort,
    ) -> None:
        self._identity_repository = identity_repository
        self._session_repository = session_repository
        self._transcript_factory = transcript_factory
        self._agent = agent

    async def handle(self, request: AgentTurnRequest) -> AsyncIterator[AgentEvent]:
        self._validate_request(request)
        transcript = self._transcript_factory.for_session(request.session_id)
        transcript.append_user_turn(request.message)
        outputs = self._start_agent(request, transcript.history)
        sequence = 0

        while True:
            try:
                output = next(outputs)
            except StopIteration:
                return
            except AuthorizationError:
                raise
            except Exception as error:
                failed = self._failed_event(request, sequence, error)
                transcript.append_event(failed)
                yield failed
                return

            event = self._event_from_output(request, sequence, output)
            transcript.append_event(event)
            yield event
            sequence += 1

    def _validate_request(self, request: AgentTurnRequest) -> None:
        try:
            authenticated_owner = self._identity_repository.resolve(
                request.channel, request.principal.actor_id
            )
            session = self._session_repository.get(request.session_id)
        except (UnknownIdentity, UnknownSession) as error:
            raise AuthorizationError("principal is not authorized for this session") from error

        if authenticated_owner.owner_user_id != request.principal.owner_user_id:
            raise AuthorizationError("principal owner does not match authenticated identity")
        if session.owner_user_id != request.principal.owner_user_id:
            raise AuthorizationError("principal owner does not match session owner")
        if session.channel != request.channel:
            raise AuthorizationError("principal channel does not match session channel")
        if request.workflow_id is not None:
            self._validate_workflow(request, session.owner_user_id, session.active_workflow_id)

    def _validate_workflow(
        self,
        request: AgentTurnRequest,
        owner_user_id: str,
        active_workflow_id: str | None,
    ) -> None:
        if request.workflow_id == active_workflow_id:
            return

        handoff = self._session_repository.resolve_handoff(
            request.session_id, request.workflow_id
        )
        if handoff is None or handoff.owner_user_id != owner_user_id:
            raise AuthorizationError("workflow is not authorized for this session")

    def _start_agent(
        self,
        request: AgentTurnRequest,
        history: tuple[Mapping[str, Any], ...],
    ) -> Iterator[AgentOutput]:
        try:
            return iter(self._agent.run(request, history))
        except AuthorizationError:
            raise
        except Exception as error:
            return _FailedAgentIterator(error)

    @staticmethod
    def _event_from_output(
        request: AgentTurnRequest, sequence: int, output: AgentOutput
    ) -> AgentEvent:
        return AgentEvent(
            event_type=output.event_type,
            principal_id=request.principal.owner_user_id,
            session_id=request.session_id,
            turn_id=request.turn_id,
            sequence=sequence,
            data=output.data,
            workflow_id=output.workflow_id or request.workflow_id,
            job_id=output.job_id,
            approval_id=output.approval_id,
            tool_call_id=output.tool_call_id,
        )

    @staticmethod
    def _failed_event(
        request: AgentTurnRequest, sequence: int, error: Exception
    ) -> AgentEvent:
        return AgentEvent(
            event_type="failed",
            principal_id=request.principal.owner_user_id,
            session_id=request.session_id,
            turn_id=request.turn_id,
            sequence=sequence,
            data={"error": str(error)},
            workflow_id=request.workflow_id,
        )


class _FailedAgentIterator:
    def __init__(self, error: Exception) -> None:
        self._error = error
        self._raised = False

    def __iter__(self) -> _FailedAgentIterator:
        return self

    def __next__(self) -> AgentOutput:
        if self._raised:
            raise StopIteration
        self._raised = True
        raise self._error
