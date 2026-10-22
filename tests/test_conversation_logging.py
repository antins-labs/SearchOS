import json

from langchain_core.messages import HumanMessage

from searchos.harness.telemetry.conversation import (
    ConversationLogger,
    langchain_msg_to_conversation_msgs,
)
from searchos.harness.telemetry.trajectory import ConversationMessage


def test_snapshot_is_pretty_printed_and_keeps_unicode(tmp_path):
    logger = ConversationLogger(tmp_path / "conversation.json")
    logger.log(ConversationMessage(role="user", content="第一行\n第二行"))
    logger.flush()

    path = tmp_path / "conversations/snapshots/orchestrator.json"
    raw = path.read_text(encoding="utf-8")

    assert raw.startswith('{\n  "agent_name": "orchestrator",')
    assert '\n  "messages": [\n' in raw
    assert "第一行" in raw
    assert "\\u7b2c" not in raw
    assert raw.endswith("\n")
    assert json.loads(raw)["messages"][0]["content"] == "第一行\n第二行"


def test_structured_message_content_stays_json_instead_of_python_repr(tmp_path):
    blocks = [
        {"type": "text", "text": "查看这张图"},
        {"type": "image_url", "image_url": {"url": "data:image/png;base64,abc"}},
    ]

    converted = langchain_msg_to_conversation_msgs(HumanMessage(content=blocks))

    assert converted[0].content == blocks
    dumped = converted[0].model_dump()
    assert isinstance(dumped["content"], list)
    assert dumped["content"][0]["text"] == "查看这张图"

    logger = ConversationLogger(tmp_path / "conversation.json")
    logger.log(converted[0])
    logger.flush()
    snapshot = json.loads(
        (tmp_path / "conversations/snapshots/orchestrator.json").read_text(encoding="utf-8")
    )
    assert snapshot["messages"][0]["content"] == blocks
