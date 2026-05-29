import importlib.util
import pathlib
import sys

import pytest


def load_plugin_client():
    root = pathlib.Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location(
        "drawthings_grpc_plugin",
        root / "__init__.py",
        submodule_search_locations=[str(root)],
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.client if hasattr(module, "client") else __import__("drawthings_grpc_plugin.client", fromlist=["*"])


def test_alias_resolution_and_defaults(monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "hermes-home"))
    client = load_plugin_client()
    models = [
        {"name": "Qwen Image 2512", "file": "qwen_image_2512_q8p.ckpt", "version": "qwen_image"},
        {"name": "ERNIE Image Base 1.0", "file": "ernie_image_q8p.ckpt", "version": "ernie_image"},
        {"name": "ERNIE Image Turbo 1.0", "file": "ernie_image_turbo_q8p.ckpt", "version": "ernie_image"},
    ]
    loras = [
        {
            "name": "Qwen Image 2512 Lightning 4-Step v1.0",
            "file": "qwen_image_2512_lightning_4_step_v1.0_lora_f16.ckpt",
            "version": "qwen_image",
        },
        {
            "name": "Qwen Image 2512 Turbo 4-Step v1.0",
            "file": "qwen_image_2512_turbo_4_step_v1.0_lora_f16.ckpt",
            "version": "qwen_image",
        },
    ]

    assert client.resolve(models, "qwen-image-2512")["file"] == "qwen_image_2512_q8p.ckpt"
    assert client.resolve(models, "ernie-image")["file"] == "ernie_image_q8p.ckpt"
    assert client.resolve(models, "ernie-image-turbo")["file"] == "ernie_image_turbo_q8p.ckpt"
    assert client.resolve(loras, "qwen-lightning")["file"] == "qwen_image_2512_lightning_4_step_v1.0_lora_f16.ckpt"
    assert client.resolve(loras, "qwen-turbo-lora")["file"] == "qwen_image_2512_turbo_4_step_v1.0_lora_f16.ckpt"

    assert client.generation_defaults(models[0])["steps"] == 30
    assert client.generation_defaults(models[0])["cfg"] == 4.0
    assert client.generation_defaults(models[1])["steps"] == 30
    assert client.generation_defaults(models[1])["cfg"] == 4.0
    assert client.generation_defaults(models[2])["steps"] == 8
    assert client.generation_defaults(models[2])["cfg"] == 1.0
    assert client.generation_defaults(models[0], loras[0])["steps"] == 4
    assert client.generation_defaults(models[0], loras[0])["cfg"] == 1.0
    assert client.generation_defaults(models[0], loras[1])["steps"] == 4
    assert client.generation_defaults(models[0], loras[1])["cfg"] == 1.0
    assert client.plugin_config()["default_model"] == "qwen-image-2512"


def test_synthesizes_configured_loras_when_echo_omits_metadata(monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "hermes-home"))
    client = load_plugin_client()
    models = [{"name": "Qwen Image 2512", "file": "qwen_image_2512_q8p.ckpt", "version": "qwen_image"}]
    monkeypatch.setattr(
        client,
        "_existing_files",
        lambda files: {"wuli_qwen_image_2512_turbo_lora_4steps_v3.0_bf16_lora_f16.ckpt"},
    )

    loras = client._synthetic_loras_from_config(models)

    assert loras == [
        {
            "name": "Qwen Turbo V3",
            "file": "wuli_qwen_image_2512_turbo_lora_4steps_v3.0_bf16_lora_f16.ckpt",
            "version": "qwen_image",
            "synthetic": True,
            "source": "config+FilesExist",
        }
    ]
    assert client.resolve(loras, "qwen-turbo-v3")["file"] == "wuli_qwen_image_2512_turbo_lora_4steps_v3.0_bf16_lora_f16.ckpt"
    assert client.generation_defaults(models[0], loras[0])["steps"] == 4


def test_refuses_synthetic_lora_for_generation(monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "hermes-home"))
    client = load_plugin_client()
    monkeypatch.setattr(
        client,
        "inventory",
        lambda: client.Inventory(
            models=[{"name": "Qwen Image 2512", "file": "qwen_image_2512_q8p.ckpt", "version": "qwen_image"}],
            loras=[
                {
                    "name": "Qwen Lightning",
                    "file": "qwen_image_2512_lightning_4_step_v1.0_lora_f16.ckpt",
                    "version": "qwen_image",
                    "synthetic": True,
                    "source": "config+FilesExist",
                }
            ],
            controlnets=[],
            upscalers=[],
            textual_inversions=[],
        ),
    )

    with pytest.raises(ValueError, match="refusing to generate with synthetic LoRA"):
        client.generate_image({"prompt": "apple", "model": "qwen-image-2512", "lora": "qwen-lightning"})
