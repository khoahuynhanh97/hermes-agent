from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Iterator
from typing import Any, Mapping

from hermes_personal.contracts import AgentEvent, AgentTurnRequest
from hermes_personal.identity import IdentityRepository, UnknownIdentity
from hermes_personal.sessions import SessionRepository, UnknownSession

from .event_repository import EventRepository
from .ports import (
    AgentOutput,
    AuthorizationError,
    TranscriptFactory,
    UpstreamAgentPort,
)

logger = logging.getLogger(__name__)


def _advance_iterator(iterator: Iterator[AgentOutput]) -> AgentOutput | None:
    try:
        return next(iterator)
    except StopIteration:
        return None


def _close_iterator(iterator: Iterator[AgentOutput]) -> None:
    close = getattr(iterator, "close", None)
    if callable(close):
        close()


async def _start_agent_in_worker(
    agent: UpstreamAgentPort,
    request: AgentTurnRequest,
    history: tuple[Mapping[str, Any], ...],
) -> Iterator[AgentOutput]:
    task = asyncio.create_task(asyncio.to_thread(agent.run, request, history))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        try:
            iterator = await asyncio.shield(task)
        except Exception:
            pass
        else:
            try:
                await asyncio.shield(asyncio.to_thread(_close_iterator, iterator))
            except Exception:
                pass
        raise


async def _advance_iterator_in_worker(
    iterator: Iterator[AgentOutput],
) -> AgentOutput | None:
    task = asyncio.create_task(asyncio.to_thread(_advance_iterator, iterator))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        try:
            await asyncio.shield(task)
        except Exception:
            pass
        raise


class HermesTurnService:
    def __init__(
        self,
        identity_repository: IdentityRepository,
        session_repository: SessionRepository,
        event_repository: EventRepository,
        transcript_factory: TranscriptFactory,
        agent: UpstreamAgentPort,
    ) -> None:
        self._identity_repository = identity_repository
        self._session_repository = session_repository
        self._event_repository = event_repository
        self._transcript_factory = transcript_factory
        self._agent = agent

    async def handle(self, request: AgentTurnRequest) -> AsyncIterator[AgentEvent]:
        self._validate_request(request)
        replay = self._event_repository.claim(request)
        if replay is not None:
            for event in replay:
                yield event
            return

        transcript = self._transcript_factory.for_session(request.session_id)
        history = self._assemble_history(transcript, request.session_id)
        transcript.append_user_turn(request.message)
        outputs: Iterator[AgentOutput] | None = None
        terminal_emitted = False
        next_sequence = 0
        try:
            try:
                outputs = await _start_agent_in_worker(
                    self._agent, request, history
                )
            except AuthorizationError as error:
                failed = self._failed_event(request, 0, error)
                self._persist_event(transcript, failed)
                terminal_emitted = True
                raise
            except Exception as error:
                failed = self._failed_event(request, 0, error)
                self._persist_event(transcript, failed)
                terminal_emitted = True
                yield failed
                return

            while True:
                try:
                    output = await _advance_iterator_in_worker(outputs)
                except AuthorizationError as error:
                    failed = self._failed_event(request, next_sequence, error)
                    self._persist_event(transcript, failed)
                    terminal_emitted = True
                    raise
                except Exception as error:
                    failed = self._failed_event(request, next_sequence, error)
                    self._persist_event(transcript, failed)
                    terminal_emitted = True
                    yield failed
                    return

                if output is None:
                    return

                try:
                    self._validate_output_workflow(request, output)
                except AuthorizationError as error:
                    failed = self._failed_event(request, next_sequence, error)
                    self._persist_event(transcript, failed)
                    terminal_emitted = True
                    raise

                event = self._event_from_output(request, next_sequence, output)
                if event.event_type in {"completed", "failed"}:
                    terminal_emitted = True
                self._persist_event(transcript, event)
                next_sequence += 1
                yield event
                if terminal_emitted:
                    return
        except (asyncio.CancelledError, GeneratorExit):
            if not terminal_emitted:
                cancelled_event = AgentEvent(
                    event_type="failed",
                    principal_id=request.principal.owner_user_id,
                    session_id=request.session_id,
                    turn_id=request.turn_id,
                    sequence=next_sequence,
                    data={"error": "turn cancelled", "cancelled": True},
                    workflow_id=request.workflow_id,
                )
                self._persist_event(transcript, cancelled_event)
                terminal_emitted = True
            raise
        finally:
            if outputs is not None:
                await asyncio.shield(asyncio.to_thread(_close_iterator, outputs))

    def _persist_event(self, transcript: Any, event: AgentEvent) -> None:
        self._event_repository.append_event(event)
        try:
            transcript.append_event(event)
        except Exception as error:
            logger.warning(
                "Failed to append event %s (turn %s) to transcript projection for session %s: %s",
                event.event_id,
                event.turn_id,
                event.session_id,
                error,
            )

    def _assemble_history(
        self, transcript: Any, session_id: str
    ) -> tuple[Mapping[str, Any], ...]:
        canonical_history = self._event_repository.load_session_history(session_id)
        if canonical_history:
            return canonical_history
        return tuple(transcript.history)

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

    @staticmethod
    def _validate_output_workflow(
        request: AgentTurnRequest, output: AgentOutput
    ) -> None:
        if output.workflow_id is not None and output.workflow_id != request.workflow_id:
            raise AuthorizationError("agent output workflow is not authorized")

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
            workflow_id=request.workflow_id,
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
