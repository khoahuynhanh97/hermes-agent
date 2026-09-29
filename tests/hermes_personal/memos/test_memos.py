from __future__ import annotations

import pytest

from hermes_personal.integrations.memos import MemoCapability
from hermes_personal.memos.models import PersonalMemo
from hermes_personal.memos.repository import MemoRepository
from hermes_personal.storage.sqlite import connect as sqlite_connect


@pytest.fixture
def db_conn(tmp_path):
    conn = sqlite_connect(tmp_path / "memos_test.db")
    conn.execute(
        "INSERT OR IGNORE INTO global_user_identity (owner_user_id, display_name, created_at) "
        "VALUES ('user1', 'User 1', '2026-08-24T00:00:00Z')"
    )
    conn.execute(
        "INSERT OR IGNORE INTO global_user_identity (owner_user_id, display_name, created_at) "
        "VALUES ('user2', 'User 2', '2026-08-24T00:00:00Z')"
    )
    conn.commit()
    yield conn
    conn.close()


def test_memo_crud_and_tag_classification(db_conn):
    repo = MemoRepository(db_conn)

    # 1. Create memo with tags and group
    memo1 = repo.create_memo(
        owner_user_id="user1",
        title="Ý tưởng video ngắn",
        content="Làm chuỗi video review tai nghe chống ồn dưới 1 triệu",
        group_name="ideas",
        tags=["#video", "#tiktok", "audio"],
        pinned=True,
    )
    assert memo1.memo_id.startswith("memo_")
    assert memo1.group_name == "ideas"
    assert "video" in memo1.tags
    assert "tiktok" in memo1.tags
    assert "audio" in memo1.tags
    assert memo1.pinned is True

    # 2. Create second memo in different group
    memo2 = repo.create_memo(
        owner_user_id="user1",
        title="Danh sách mua sắm",
        content="Mua micro thu âm không dây và chân tripod",
        group_name="shopping",
        tags=["equipment", "#audio"],
    )

    # 3. List memos by group
    ideas_memos = repo.list_memos(owner_user_id="user1", group_name="ideas")
    assert len(ideas_memos) == 1
    assert ideas_memos[0].memo_id == memo1.memo_id

    # 4. List memos by tag
    audio_memos = repo.list_memos(owner_user_id="user1", tag="audio")
    assert len(audio_memos) == 2

    # 5. List tags and groups count
    tags = repo.list_tags(owner_user_id="user1")
    tag_dict = dict(tags)
    assert tag_dict["audio"] == 2
    assert tag_dict["video"] == 1
    assert "shopping" not in tag_dict

    groups = repo.list_groups(owner_user_id="user1")
    group_dict = dict(groups)
    assert group_dict["ideas"] == 1
    assert group_dict["shopping"] == 1

    # 6. Full-text search (FTS5)
    search_res = repo.search_memos(owner_user_id="user1", query="tai nghe chống ồn")
    assert len(search_res) == 1
    assert search_res[0].memo_id == memo1.memo_id

    # 7. Update memo
    updated = repo.update_memo(
        memo_id=memo1.memo_id,
        owner_user_id="user1",
        content="Nội dung đã cập nhật: thêm 3 mẫu tai nghe Anker, Baseus, Edifier",
        pinned=False,
    )
    assert "Anker" in updated.content
    assert updated.pinned is False

    # 8. Delete memo
    deleted = repo.delete_memo(memo_id=memo2.memo_id, owner_user_id="user1")
    assert deleted is True
    assert repo.get_memo(memo2.memo_id) is None


def test_memo_owner_isolation(db_conn):
    repo = MemoRepository(db_conn)

    # User 1 memo
    m1 = repo.create_memo(
        owner_user_id="user1",
        title="User 1 Secret",
        content="Personal password hints",
        group_name="private",
    )

    # User 2 tries to search / list
    user2_list = repo.list_memos(owner_user_id="user2")
    assert len(user2_list) == 0

    user2_search = repo.search_memos(owner_user_id="user2", query="Secret")
    assert len(user2_search) == 0

    assert repo.get_memo(m1.memo_id, owner_user_id="user2") is None


def test_memo_capability_mcp_surface(db_conn):
    repo = MemoRepository(db_conn)
    cap = MemoCapability(repo, default_owner_user_id="user1")

    # Create via tool
    res = cap.create_memo(
        title="Nhắc nhở họp team",
        content="Họp review tiến độ lúc 10h sáng thứ 2",
        group_name="work",
        tags=["meeting", "team"],
    )
    assert res["status"] == "created"
    memo_id = res["memo"]["memo_id"]

    # Search via tool
    search = cap.search_memos(query="họp review")
    assert search["count"] == 1
    assert search["memos"][0]["memo_id"] == memo_id

    # Tag listing via tool
    tags = cap.list_tags()
    assert any(t["tag"] == "meeting" for t in tags["tags"])

    # Group listing via tool
    groups = cap.list_groups()
    assert any(g["group"] == "work" for g in groups["groups"])

    # Delete via tool
    del_res = cap.delete_memo(memo_id=memo_id)
    assert del_res["status"] == "deleted"
