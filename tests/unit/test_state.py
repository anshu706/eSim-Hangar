"""Unit tests for state tracking and install history."""

from pathlib import Path

from esim_tool_manager.state import StateManager


def test_state_manager_save_and_get(tmp_path: Path) -> None:
    mgr = StateManager(state_dir=tmp_path)
    assert mgr.get_record("ngspice") is None

    rec1 = mgr.save_record(
        tool_name="ngspice",
        version="42.0",
        install_method="direct_download",
        install_path="C:/Tools/Spice64",
    )
    assert rec1.tool_name == "ngspice"
    assert rec1.version == "42.0"
    assert rec1.previous_version is None

    loaded1 = mgr.get_record("ngspice")
    assert loaded1 is not None
    assert loaded1.version == "42.0"
    assert loaded1.install_path == "C:/Tools/Spice64"

    # Upgrading saves previous record
    rec2 = mgr.save_record(
        tool_name="ngspice",
        version="43.0",
        install_method="direct_download",
        install_path="C:/Tools/Spice64",
    )
    assert rec2.version == "43.0"
    assert rec2.previous_version == "42.0"

    loaded2 = mgr.get_record("ngspice")
    assert loaded2 is not None
    assert loaded2.previous_version == "42.0"


def test_state_manager_get_all_and_delete(tmp_path: Path) -> None:
    mgr = StateManager(state_dir=tmp_path)
    mgr.save_record("python", "3.11.9", "winget", "C:/Python")
    mgr.save_record("git", "2.40.0", "winget", "C:/Git")

    all_recs = mgr.get_all_records()
    assert len(all_recs) == 2
    assert "python" in all_recs
    assert "git" in all_recs

    assert mgr.delete_record("git") is True
    assert mgr.get_record("git") is None
    assert len(mgr.get_all_records()) == 1
