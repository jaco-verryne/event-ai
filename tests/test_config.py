from eventai import config


def test_read_dotenv(tmp_path):
    env = tmp_path / ".env"
    env.write_text(
        "# comment\n"
        "\n"
        "GROQ_API_KEY=abc\n"
        "GROQ_MODEL = 'openai/gpt-oss-120b'\n"
        'LANGFUSE_HOST="https://cloud.langfuse.com"\n'
        "NOT A PAIR\n"
        "EMPTY=\n"
    )

    assert config.read_dotenv(env) == {
        "GROQ_API_KEY": "abc",
        "GROQ_MODEL": "openai/gpt-oss-120b",
        "LANGFUSE_HOST": "https://cloud.langfuse.com",
        "EMPTY": "",
    }


def test_read_dotenv_missing_file(tmp_path):
    assert config.read_dotenv(tmp_path / ".env") == {}


def test_load_dotenv_does_not_overwrite_environment(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("EVENTAI_TEST_A=from_file\nEVENTAI_TEST_B=from_file\n")
    monkeypatch.setenv("EVENTAI_TEST_A", "from_env")
    monkeypatch.delenv("EVENTAI_TEST_B", raising=False)

    config.load_dotenv(env)

    assert config.get("EVENTAI_TEST_A") == "from_env"
    assert config.get("EVENTAI_TEST_B") == "from_file"
    monkeypatch.delenv("EVENTAI_TEST_B")


def test_get_uses_environment_without_streamlit(monkeypatch):
    monkeypatch.delitem(config.sys.modules, "streamlit", raising=False)
    monkeypatch.setenv("EVENTAI_TEST_C", "x")
    monkeypatch.setenv("EVENTAI_TEST_EMPTY", "")

    assert config.get("EVENTAI_TEST_C") == "x"
    assert config.get("EVENTAI_TEST_EMPTY", "default") == "default"
    assert config.get("EVENTAI_TEST_MISSING") is None


def test_streamlit_secrets_win_over_environment(monkeypatch):
    fake_st = type("FakeStreamlit", (), {"secrets": {"EVENTAI_TEST_D": "from_secrets"}})
    monkeypatch.setitem(config.sys.modules, "streamlit", fake_st)
    monkeypatch.setenv("EVENTAI_TEST_D", "from_env")

    assert config.get("EVENTAI_TEST_D") == "from_secrets"
