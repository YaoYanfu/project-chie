from unittest.mock import Mock

from src.amadeus import server


def test_server_is_hard_bound_to_loopback(monkeypatch) -> None:
    fake_app = object()
    uvicorn_run = Mock()
    monkeypatch.setattr(server, "create_app", lambda: fake_app)
    monkeypatch.setattr(server, "assert_port_available", Mock())
    monkeypatch.setattr(server, "initialize_logging", Mock())
    monkeypatch.setattr(server.uvicorn, "run", uvicorn_run)

    server.main(["--port", "9876"])

    assert server.assert_port_available.call_args.kwargs["host"] == "127.0.0.1"
    assert uvicorn_run.call_args.kwargs["host"] == "127.0.0.1"
    assert uvicorn_run.call_args.kwargs["port"] == 9876
