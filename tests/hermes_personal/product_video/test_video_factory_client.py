import json
from hermes_personal.integrations.video_factory.client import VideoFactoryClient
from hermes_personal.integrations.video_factory import contracts


def test_video_factory_client_methods():
    client = VideoFactoryClient()
    # shared artifact reference
    expected_artifact_ref = client._artifact.digest()
    for method_name, request_cls in [
        ("create_creative_brief", contracts.CreativeBriefRequest),
        ("create_scene_plan", contracts.ScenePlanRequest),
        ("create_storyboard", contracts.StoryboardRequest),
        ("render_video", contracts.RenderRequest),
        ("export_video", contracts.ExportRequest),
    ]:
        method = getattr(client, method_name)
        result = method()
        # keys exist
        assert set(result.keys()) == {"artifact_ref", "payload", "digest"}
        # artifact ref deterministic
        assert result["artifact_ref"] == expected_artifact_ref
        # payload matches request JSON
        request = request_cls()
        assert json.loads(result["payload"]) == {
            "owner": request.owner,
            "version": request.version,
        }
        # digest matches request digest
        assert result["digest"] == request.digest()
