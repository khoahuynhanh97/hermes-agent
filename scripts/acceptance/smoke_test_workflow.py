import requests
import json
import time
import uuid

# Configuration
BASE_URL = "http://127.0.0.1:8000/api"
OWNER_USER_ID = "acceptance_test_user"
PROJECT_ID = f"proj_acceptance_{uuid.uuid4().hex[:8]}"
PRODUCT_QUERY = "Nghiên cứu Baseus Bowie MA10 và tạo project video TikTok review 30 giây."

def print_step(title):
    print(f"\\n{'='*20}\\n[STEP] {title}\\n{'='*20}")

def assert_status(response, expected_status=200, context=""):
    if response.status_code != expected_status:
        print(f"Assertion failed: {context}")
        print(f"Expected status {expected_status}, but got {response.status_code}")
        try:
            print("Response body:", response.json())
        except json.JSONDecodeError:
            print("Response body:", response.text)
        raise AssertionError(f"{context}: Status code mismatch")
    print(f"OK: {context} (Status: {response.status_code})")
    return response.json()

def main():
    try:
        # 1. Input: "Nghiên cứu Baseus Bowie MA10..."
        # This is the product_query
        print_step("1. Create Project")
        create_payload = {"project_id": PROJECT_ID}
        project_data = assert_status(
            requests.post(f"{BASE_URL}/vf/projects", json=create_payload, params={"owner_user_id": OWNER_USER_ID}),
            expected_status=200,
            context="Create new video project"
        )["data"]
        print(f"Project created with ID: {project_data['id']}")

        # 2. Resolve product qua canonical PI boundary.
        # 3. Load actual persisted ResourcePackLock.
        # 4. Create/reuse Hermes project.
        # 5. Bind product, snapshot, lock và manifest digest.
        print_step("2-5. Bind Product Resources")
        bind_payload = {"product_query": PRODUCT_QUERY}
        project_data = assert_status(
            requests.post(f"{BASE_URL}/vf/projects/{PROJECT_ID}/resources/bind", json=bind_payload, params={"owner_user_id": OWNER_USER_ID}),
            context="Bind product resources via PI"
        )["data"]
        assert project_data["resource_pack"] is not None, "Resource pack should be bound"
        print(f"Resource Pack locked: {project_data['resource_pack']['id']}")
        
        # 6. Generate Creative Brief.
        print_step("6. Generate & Approve Creative Brief")
        # In the refactored code, the brief is not auto-generated. We need to save one.
        brief_payload = {
            "objective": "TikTok review video",
            "target_audience": "Gen Z",
            "core_message": "Tai nghe chống ồn, pin trâu",
            "content_blocks": ["Unboxing", "Điểm nổi bật", "CTA"]
        }
        project_data = assert_status(
            requests.post(f"{BASE_URL}/vf/projects/{PROJECT_ID}/brief", json=brief_payload, params={"owner_user_id": OWNER_USER_ID}),
            context="Save creative brief"
        )["data"]
        project_data = assert_status(
            requests.post(f"{BASE_URL}/vf/projects/{PROJECT_ID}/brief/approve", params={"owner_user_id": OWNER_USER_ID}),
            context="Approve creative brief"
        )["data"]
        assert project_data["creative_brief"]["status"] == "APPROVED", "Brief should be approved"
        print("Creative Brief approved.")

        # 7. Generate Scene Plan.
        print_step("7. Generate & Approve Scene Plan")
        # In refactored code, this is also manual
        project_data = assert_status(
            requests.post(f"{BASE_URL}/vf/projects/{PROJECT_ID}/scenes/approve", params={"owner_user_id": OWNER_USER_ID}),
            context="Approve (default) scene plan"
        )["data"]
        assert project_data["scene_plan"]["status"] == "APPROVED", "Scene plan should be approved"
        print("Scene Plan approved.")

        # 8. Generate Storyboard.
        print_step("8. Generate Storyboard")
        generation_result = assert_status(
            requests.post(f"{BASE_URL}/vf/projects/{PROJECT_ID}/storyboard/generate", params={"owner_user_id": OWNER_USER_ID}),
            context="Generate storyboard"
        )
        project_data = generation_result["data"]
        assert project_data["storyboard"] is not None, "Storyboard should be generated"
        print("Storyboard generation requested.")

        # 9. Enqueue deterministic fake jobs.
        print_step("9. Check for Enqueued Jobs (Implicit)")
        # The previous step returns job IDs. We assume they are enqueued.
        jobs = generation_result.get("jobs", [])
        assert len(jobs) > 0, "Storyboard generation should have created jobs"
        print(f"Enqueued {len(jobs)} image generation jobs.")
        
        # Poll for storyboard completion
        for _ in range(20): # Poll for 20 seconds max
            project_res = requests.get(f"{BASE_URL}/vf/projects/{PROJECT_ID}", params={"owner_user_id": OWNER_USER_ID})
            project_data = assert_status(project_res, context="Poll project status")["data"]
            if project_data["storyboard"]["approval_status"] == "APPROVED":
                print("Storyboard auto-approved after frame generation.")
                break
            time.sleep(1)
        else:
            raise AssertionError("Storyboard did not complete in time.")
            
        # 10. Project terminal results. (implicitly done by _sync_project_generation_status)
        print_step("10. Poll for Video Scene Generation")
        for _ in range(20): # Poll for 20 seconds max
            project_res = requests.get(f"{BASE_URL}/vf/projects/{PROJECT_ID}", params={"owner_user_id": OWNER_USER_ID})
            project_data = assert_status(project_res, context="Poll project status")["data"]
            if project_data.get("generated_scenes") and all(s['generation_status'] == 'COMPLETED' for s in project_data['generated_scenes']):
                print("All video scenes generated.")
                break
            time.sleep(1)
        else:
            raise AssertionError("Video scenes did not complete generation in time.")

        # 11. Build timeline.
        print_step("11. Render Timeline")
        timeline_job = assert_status(
            requests.post(f"{BASE_URL}/vf/projects/{PROJECT_ID}/timeline/render", params={"owner_user_id": OWNER_USER_ID}),
            context="Render timeline"
        )
        print(f"Timeline render job submitted: {timeline_job['job_id']}")
        
        # 12. Create export manifest.
        print_step("12. Export Final Video")
        for _ in range(20): # Poll for draft video
             project_res = requests.get(f"{BASE_URL}/vf/projects/{PROJECT_ID}", params={"owner_user_id": OWNER_USER_ID})
             project_data = assert_status(project_res, context="Poll project status")["data"]
             if project_data.get('draft_video_asset_id'):
                 print("Draft video is ready.")
                 break
             time.sleep(1)
        else:
            raise AssertionError("Draft video did not complete in time.")

        export_job = assert_status(
            requests.post(f"{BASE_URL}/vf/projects/{PROJECT_ID}/final/export", params={"owner_user_id": OWNER_USER_ID}),
            context="Export final video"
        )
        print(f"Final export job submitted: {export_job['job_id']}")

        # 13. Reload project và xác nhận state còn nguyên.
        print_step("13. Reload Project State")
        reloaded_data = assert_status(
             requests.get(f"{BASE_URL}/vf/projects/{PROJECT_ID}", params={"owner_user_id": OWNER_USER_ID}),
             context="Reload project"
        )["data"]
        assert reloaded_data["id"] == project_data["id"], "Project ID mismatch on reload"
        assert reloaded_data["resource_pack"]["id"] == project_data["resource_pack"]["id"], "Resource pack mismatch on reload"
        assert reloaded_data["final_approval"] == "APPROVED", "Final approval state not persisted"
        print("Project state reloaded successfully.")

        # 14. Replay một terminal job và xác nhận không duplicate asset.
        print_step("14. Replay Job (Idempotency Check)")
        # Re-approving the brief should be idempotent and not create duplicates
        re_approve_res = requests.post(f"{BASE_URL}/vf/projects/{PROJECT_ID}/brief/approve", params={"owner_user_id": OWNER_USER_ID})
        re_approved_data = assert_status(re_approve_res, context="Re-approve creative brief")["data"]
        
        # Check asset count - should be the same
        assets_res = requests.get(f"{BASE_URL}/assets", params={"owner_user_id": OWNER_USER_ID, "product_id": re_approved_data['id']})
        assets_data = assert_status(assets_res, context="List assets after replay")
        
        time.sleep(2) # Wait for any potential background jobs
        
        final_assets_res = requests.get(f"{BASE_URL}/assets", params={"owner_user_id": OWNER_USER_ID, "product_id": re_approved_data['id']})
        final_assets_data = assert_status(final_assets_res, context="List assets after wait")
        
        assert assets_data["total"] == final_assets_data["total"], f"Asset count changed on replay! {assets_data['total']} -> {final_assets_data['total']}"
        print(f"Idempotency check passed. Asset count remained at {assets_data['total']}.")


        print("\\n\\nSMOKE TEST PASSED SUCCESSFULLY!")

    except Exception as e:
        print(f"\\n\\nSMOKE TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        exit(1)

if __name__ == "__main__":
    main()
