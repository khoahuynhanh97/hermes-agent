import pytest
from hermes.adapters.telegram.ingestion_adapter import TelegramIngestionAdapter, FakeTelegramVideo
from hermes.application.ingestion_service import IngestionService
from hermes.domain.results import Result


@pytest.fixture
def fake_service():
    return IngestionService()


@pytest.fixture
def adapter(fake_service):
    return TelegramIngestionAdapter(fake_service)


def test_video_message_becomes_an_ingestion_request(adapter, fake_service):
    video = FakeTelegramVideo(file_id="abc", caption="/hoc_kien_thuc")
    result = adapter.handle_video(video)
    assert result.ok
    assert result.value is not None
    assert fake_service.requests[0].requested_action == "learn_knowledge"


def test_video_message_without_command_becomes_generic(adapter, fake_service):
    video = FakeTelegramVideo(file_id="xyz", caption="Just a video")
    result = adapter.handle_video(video)
    assert result.ok
    assert fake_service.requests[0].requested_action == "ingest_generic"


def test_document_becomes_ingestion_request(adapter, fake_service):
    from hermes.adapters.telegram.ingestion_adapter import FakeTelegramDocument
    doc = FakeTelegramDocument(file_id="doc1", file_name="report.pdf")
    result = adapter.handle_document(doc)
    assert result.ok
    assert fake_service.requests[0].requested_action == "ingest_document"
    assert fake_service.requests[0].source_type == "document"


def test_service_publishes_notification_on_submit(adapter, fake_service):
    notification_calls = []

    class TrackingNotification:
        def publish(self, event):
            notification_calls.append(event)

    service_with_tracking = IngestionService(notification_port=TrackingNotification())
    tracking_adapter = TelegramIngestionAdapter(service_with_tracking)
    video = FakeTelegramVideo(file_id="test123", caption="/hoc_kien_thuc")
    tracking_adapter.handle_video(video)
    assert len(notification_calls) == 1
    assert notification_calls[0]["event"] == "ingestion_submitted"
    assert notification_calls[0]["requested_action"] == "learn_knowledge"