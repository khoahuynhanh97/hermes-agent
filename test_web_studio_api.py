import pytest
import subprocess
import time
import requests
import os

SERVER_URL = "http://127.0.0.1:8000"

@pytest.fixture(scope="module")
def web_studio_server():
    process = subprocess.Popen(["python", "web_studio.py"], cwd="D:\\work\\hermes-agent")
    time.sleep(5)
    yield process
    process.terminate()
    process.wait()

def test_api_list_projects(web_studio_server):
    response = requests.get(f"{SERVER_URL}/api/projects")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert isinstance(data["data"], list)

def test_api_create_project(web_studio_server):
    project_name = f"Test Project {time.time()}"
    response = requests.post(f"{SERVER_URL}/api/projects", json={"name": project_name})
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "ok"
    assert data["data"]["name"] == project_name
