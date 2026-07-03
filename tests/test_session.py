"""Tests for Session persistence."""

import os
import tempfile

import pytest


class TestSessionSave:
    """Behavior 1: Session saves to a Markdown + YAML Frontmatter file."""

    def test_save_creates_file(self):
        """Save creates a .md file with frontmatter."""
        from agent_from_zero.session import Session

        session = Session(name="test-session")
        session.add_message({"role": "user", "content": "hello"})
        session.add_message({"role": "assistant", "content": "hi there"})

        with tempfile.TemporaryDirectory() as tmpdir:
            session.save(tmpdir)
            path = os.path.join(tmpdir, "test-session.md")
            assert os.path.isfile(path)

    def test_saved_file_has_frontmatter(self):
        """Saved file starts with YAML frontmatter containing session_id and name."""
        from agent_from_zero.session import Session

        session = Session(name="my-chat")
        session.add_message({"role": "user", "content": "hi"})

        with tempfile.TemporaryDirectory() as tmpdir:
            session.save(tmpdir)
            path = os.path.join(tmpdir, "my-chat.md")
            content = open(path, encoding="utf-8").read()
            assert content.startswith("---")
            assert "name: my-chat" in content
            assert "session_id:" in content
            assert "created_at:" in content

    def test_saved_file_has_messages(self):
        """Messages are written in the markdown body."""
        from agent_from_zero.session import Session

        session = Session(name="test")
        session.add_message({"role": "user", "content": "What is Python?"})
        session.add_message({"role": "assistant", "content": "Python is a programming language."})

        with tempfile.TemporaryDirectory() as tmpdir:
            session.save(tmpdir)
            path = os.path.join(tmpdir, "test.md")
            content = open(path, encoding="utf-8").read()
            assert "What is Python?" in content
            assert "programming language" in content


class TestSessionLoad:
    """Behavior 2: Session restores state from a saved file."""

    def test_load_restores_messages(self):
        """Loading a session restores all messages."""
        from agent_from_zero.session import Session

        # First, create and save
        session = Session(name="restore-test")
        session.add_message({"role": "system", "content": "You are helpful."})
        session.add_message({"role": "user", "content": "hello"})
        session.add_message({"role": "assistant", "content": "hi"})

        with tempfile.TemporaryDirectory() as tmpdir:
            session.save(tmpdir)
            # Now load
            loaded = Session.load("restore-test", tmpdir)
            msgs = loaded.get_messages()
            assert len(msgs) == 3
            assert msgs[1]["content"] == "hello"
            assert msgs[2]["content"] == "hi"

    def test_load_preserves_todo_state(self):
        """Session preserves todo items across save/load."""
        from agent_from_zero.session import Session

        session = Session(name="todo-session")
        session.todo_items = [
            {"item": "Buy milk", "done": False},
            {"item": "Write tests", "done": True},
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            session.save(tmpdir)
            loaded = Session.load("todo-session", tmpdir)
            assert len(loaded.todo_items) == 2
            assert loaded.todo_items[0]["item"] == "Buy milk"
            assert loaded.todo_items[1]["done"] is True


class TestSessionIsolation:
    """Behavior 3: Sessions are fully isolated from each other."""

    def test_two_sessions_independent(self):
        """Two sessions do not share messages."""
        from agent_from_zero.session import Session

        session_a = Session(name="alpha")
        session_a.add_message({"role": "user", "content": "Alpha message"})

        session_b = Session(name="beta")
        session_b.add_message({"role": "user", "content": "Beta message"})

        with tempfile.TemporaryDirectory() as tmpdir:
            session_a.save(tmpdir)
            session_b.save(tmpdir)

            # Reload both
            loaded_a = Session.load("alpha", tmpdir)
            loaded_b = Session.load("beta", tmpdir)

            msgs_a = loaded_a.get_messages()
            msgs_b = loaded_b.get_messages()

            assert any("Alpha message" in m["content"] for m in msgs_a)
            assert not any("Beta message" in m["content"] for m in msgs_a)
            assert any("Beta message" in m["content"] for m in msgs_b)
            assert not any("Alpha message" in m["content"] for m in msgs_b)


class TestListSessions:
    """Behavior 4: List available sessions."""

    def test_list_returns_session_names(self):
        """list_sessions() returns names of all saved sessions."""
        from agent_from_zero.session import Session, list_sessions

        with tempfile.TemporaryDirectory() as tmpdir:
            Session(name="one").save(tmpdir)
            Session(name="two").save(tmpdir)

            names = list_sessions(tmpdir)
            assert "one" in names
            assert "two" in names
            assert len(names) == 2

    def test_list_empty_when_no_sessions(self):
        """list_sessions() returns empty list when directory is empty."""
        from agent_from_zero.session import list_sessions

        with tempfile.TemporaryDirectory() as tmpdir:
            names = list_sessions(tmpdir)
            assert names == []


class TestSessionErrors:
    """Behavior 5: Corrupted files produce diagnostic errors."""

    def test_load_corrupted_file_raises(self):
        """Loading a file with missing frontmatter raises a clear error."""
        from agent_from_zero.session import Session

        with tempfile.TemporaryDirectory() as tmpdir:
            # Write a bad session file
            bad_path = os.path.join(tmpdir, "bad-session.md")
            with open(bad_path, "w", encoding="utf-8") as f:
                f.write("Just some random text\nNo frontmatter here\n")

            with pytest.raises(ValueError, match="frontmatter"):
                Session.load("bad-session", tmpdir)
