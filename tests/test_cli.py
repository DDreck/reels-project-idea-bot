from inspiration_pipeline import cli


def test_collect_dispatches(monkeypatch, config_files):
    cfg_path, _ = config_files
    called = {}
    monkeypatch.setattr(cli, "_run_collect",
                        lambda config, backlog: called.update(backlog=backlog) or 3)
    rc = cli.main(["collect", "--backlog", "--config", str(cfg_path)])
    assert rc == 0 and called["backlog"] is True


def test_process_dispatches(monkeypatch, config_files):
    cfg_path, _ = config_files
    called = {}
    monkeypatch.setattr(cli, "_run_process",
                        lambda config: called.setdefault("ran", True) or 2)
    rc = cli.main(["process", "--config", str(cfg_path)])
    assert rc == 0 and called["ran"] is True
