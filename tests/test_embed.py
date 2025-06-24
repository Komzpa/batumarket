from pathlib import Path
import sys
import types
import json

# stub openai
dummy_openai = types.ModuleType("openai")
class DummyEmbeddings:
    @staticmethod
    def create(*a, **k):
        # return an embedding for every input item
        n = len(k.get("input", [])) if isinstance(k.get("input"), list) else 1
        return types.SimpleNamespace(
            data=[types.SimpleNamespace(embedding=[1, 2, 3]) for _ in range(n)]
        )

dummy_openai.embeddings = DummyEmbeddings()
sys.modules["openai"] = dummy_openai

# config stub
dummy_cfg = types.ModuleType("config")
dummy_cfg.OPENAI_KEY = ""
sys.modules["config"] = dummy_cfg

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import embed


def test_embed_file(tmp_path, monkeypatch):
    monkeypatch.setattr(embed, "LOTS_DIR", tmp_path / "lots")
    monkeypatch.setattr(embed, "EMBED_DIR", tmp_path / "vecs")
    monkeypatch.setattr(embed, "openai", dummy_openai)

    path = tmp_path / "lots" / "chat" / "2024" / "05" / "1.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps([{"a": 1}, {"a": 2}]))

    embed.main([str(path)])

    out = tmp_path / "vecs" / "chat" / "2024" / "05" / "1.json"
    assert out.exists()
    data = json.loads(out.read_text())
    assert isinstance(data, list)
    assert len(data) == 2
    assert data[0]["id"] == "chat/2024/05/1-0"
    assert data[0]["vec"] == [1, 2, 3]
